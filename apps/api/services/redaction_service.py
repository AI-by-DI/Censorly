# apps/api/services/redaction_service.py
from __future__ import annotations
from typing import Optional, Dict, List
from datetime import datetime
import json
import hashlib
import os
import subprocess

from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import Session

from data.schema import (
    User, PreferenceProfile, VideoAsset, AnalysisJob, DetectionEvent,
    RedactionPlan, Output
)

# ---- Konfig / yardımcılar ----

CAT_KEYS = ["alcohol", "blood", "violence", "phobic", "obscene"]

DEFAULT_THRESH = 0.40
DEFAULT_BLUR = {"blur_k": 61, "box_thick": 4, "hold_gap_ms": 600, "grace_ms": 200}

# Çıkış nereye yazılacak?
# - MinIO kullanıyorsan: OUT_PREFIX = "minio://<bucket-name>/redacted"
# - Yerel/statik ise:    OUT_PREFIX = "uploads/redacted"
OUT_PREFIX = os.getenv("REDacted_OUT_PREFIX", "uploads/redacted")

# JSONL nerede? (analiz sonrası)
# ör: /uploads/jobs/<job_id>/jsonl
JOBS_JSONL_PREFIX = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs")

# stream_url üretimi:
def make_stream_url(storage_key: str) -> str:
    # minio://... ise imzalı URL mantığın varsa burada uygulayabilirsin.
    if storage_key.startswith("minio://"):
        # TODO: minio presign entegrasyonun varsa buraya koy
        return storage_key  # şimdilik düz döndürüyoruz
    # aksi halde statik dosya servisinden path
    return "/" + storage_key.lstrip("/")

def profile_to_dict(p: PreferenceProfile) -> dict:
    # p.mode Enum da olabilir string de → güvenli okuma
    mode_val = p.mode.value if getattr(p.mode, "value", None) is not None else (p.mode or "blur")

    # ORM’de kolonlar yoksa extras içinden dene; o da yoksa {}
    ex = p.extras or {}
    allow_map = getattr(p, "allow_map", None) or ex.get("allow_map", {}) or {}
    mode_map  = getattr(p, "mode_map",  None) or ex.get("mode_map",  {}) or {}

    return {
        "mode": mode_val,
        "allow_flags": {
            "allow_alcohol":  bool(p.allow_alcohol),
            "allow_blood":    bool(p.allow_blood),
            "allow_violence": bool(p.allow_violence),
            "allow_phobic":   bool(p.allow_phobic),
            "allow_obscene":  bool(p.allow_obscene),
        },
        "allow_map": allow_map,
        "mode_map":  mode_map,
        "extras":    ex,
    }
    
def compute_profile_hash(d: Dict) -> str:
    blob = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]

def blocked_categories(profile_dict: Dict) -> List[str]:
    amap = profile_dict.get("allow_map", {}) or {}
    flags = profile_dict["allow_flags"]
    out: List[str] = []
    for ck in CAT_KEYS:
        flag_name = f"allow_{ck}"
        base_allow = flags.get(flag_name, True)
        override = amap.get(ck, None)
        allow = override if override is not None else base_allow
        if allow is False:
            out.append(ck)
    return out

def thresholds_from_profile(profile_dict: Dict) -> Dict[str, float]:
    ex = profile_dict.get("extras") or {}
    th = ex.get("thresholds") or {}  # {"blood":0.2,"alcohol":0.5}
    per = {k: float(v) for k, v in th.items()}
    per.setdefault("default", DEFAULT_THRESH)
    return per

def blur_params_from_profile(profile_dict: Dict) -> Dict:
    ex = profile_dict.get("extras") or {}
    blur = ex.get("blur_params") or {}
    merged = {**DEFAULT_BLUR, **{k:int(v) for k,v in blur.items()}}
    return merged

def get_latest_done_job(db: Session, video_id: str) -> Optional[AnalysisJob]:
    q = (
        select(AnalysisJob)
        .where(and_(AnalysisJob.video_id == video_id, AnalysisJob.status == "done"))
        .order_by(desc(AnalysisJob.finished_at), desc(AnalysisJob.created_at))
        .limit(1)
    )
    return db.execute(q).scalars().first()

# ---- Ana işlev ----

def render_or_get(db: Session, user_id: str, video_id: str, profile_id: Optional[str] = None) -> Dict:
    # 1) profil
    if profile_id:
        prof = db.get(PreferenceProfile, profile_id)
    else:
        q = (
            select(PreferenceProfile)
            .where(PreferenceProfile.user_id == user_id)
            .order_by(desc(PreferenceProfile.updated_at))
            .limit(1)
        )
        prof = db.execute(q).scalars().first()
    if not prof:
        raise ValueError("Preference profile not found.")

    p_dict = profile_to_dict(prof)
    p_hash = compute_profile_hash(p_dict)
    blocked = blocked_categories(p_dict)
    if not blocked:
        # Hiçbir şey sansürlenmiyor → orijinal video
        vid = db.get(VideoAsset, video_id)
        if not vid:
            raise ValueError("Video not found.")
        return {
            "cached": True,
            "profile_hash": p_hash,
            "storage_key": vid.storage_key,
            "stream_url": make_stream_url(vid.storage_key),
            "plan_id": None,
            "output_id": None,
        }

    # 2) outputs cache
    q_out = (
        select(Output)
        .where(and_(Output.video_id == video_id, Output.profile_hash == p_hash, Output.format == "mp4"))
        .limit(1)
    )
    out_row = db.execute(q_out).scalars().first()
    if out_row:
        return {
            "cached": True,
            "profile_hash": p_hash,
            "storage_key": out_row.storage_key,
            "stream_url": make_stream_url(out_row.storage_key),
            "plan_id": None,
            "output_id": str(out_row.id),
        }

    # 3) analiz job
    job = get_latest_done_job(db, video_id)
    if not job:
        raise ValueError("No completed analysis job for this video.")

    # 4) plan (var mı?)
    q_plan = (
        select(RedactionPlan)
        .where(and_(RedactionPlan.video_id == video_id, RedactionPlan.profile_hash == p_hash))
        .limit(1)
    )
    plan = db.execute(q_plan).scalars().first()

    thr_map = thresholds_from_profile(p_dict)  # {"default":0.4,"blood":0.2,...}
    blur = blur_params_from_profile(p_dict)

    if not plan:
        # detection_events → filtrele
        q_ev = (
            select(DetectionEvent)
            .where(
                and_(
                    DetectionEvent.job_id == job.id,
                    DetectionEvent.label.in_(blocked),
                    DetectionEvent.score >= 0.0,  # eşiği uygulama tarafında uygulayacağız
                )
            )
            .order_by(DetectionEvent.ts_ms)
        )
        rows = db.execute(q_ev).scalars().all()

        # eşiğe göre işaretler
        markers = []
        for r in rows:
            mthr = float(thr_map.get(r.label, thr_map["default"]))
            if float(r.score) >= mthr:
                markers.append({"t": int(r.ts_ms), "label": r.label, "score": float(r.score)})

        plan = RedactionPlan(
            video_id=video_id,
            profile_id=prof.id,
            profile_hash=p_hash,
            plan={
                "mode": "blur",
                "blocked": blocked,
                "min_score_map": thr_map,
                "blur_params": blur,
                "job_id": str(job.id),
                "markers": markers,
            },
            created_at=datetime.utcnow(),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

    # 5) çıktı üret
    out_key = f"{OUT_PREFIX.rstrip('/')}/{video_id}/{p_hash}.mp4"
    os.makedirs(os.path.dirname(out_key), exist_ok=True) if not out_key.startswith("minio://") else None

    # min_score_map stringle
    min_map = plan.plan.get("min_score_map", {"default": DEFAULT_THRESH})
    min_map_str = ",".join([f"{k}:{float(v):.2f}" for k, v in min_map.items()])

    blur_k = int(plan.plan.get("blur_params", {}).get("blur_k", DEFAULT_BLUR["blur_k"]))
    box_thick = int(plan.plan.get("blur_params", {}).get("box_thick", DEFAULT_BLUR["box_thick"]))
    hold_gap_ms = int(plan.plan.get("blur_params", {}).get("hold_gap_ms", DEFAULT_BLUR["hold_gap_ms"]))
    grace_ms = int(plan.plan.get("blur_params", {}).get("grace_ms", DEFAULT_BLUR["grace_ms"]))

    jsonl_path = f"{JOBS_JSONL_PREFIX.rstrip('/')}/{job.id}/jsonl"
    # Eğer JSONL MinIO’da ise burada minio:// prefix kullan
    if os.path.exists(jsonl_path) or not jsonl_path.startswith("minio://"):
        jsonl_arg = jsonl_path
    else:
        jsonl_arg = f"minio://{jsonl_path}"

    # video kaynağı: VideoAsset.storage_key’i kullan
    vid = db.get(VideoAsset, video_id)
    if not vid:
        raise ValueError("Video not found.")

    video_arg = vid.storage_key if vid.storage_key.startswith("minio://") else os.path.join("", vid.storage_key)

    cmd = [
        "python", "-m", "ai.inference.pipeline_redact",
        "--video", video_arg,
        "--jsonl", jsonl_arg,
        "--out", out_key,
        "--min_score_map", min_map_str,
        "--hold_gap_ms", str(hold_gap_ms),
        "--grace_ms", str(grace_ms),
        "--mode", "blur",
        "--blur_k", str(blur_k),
        "--box_thick", str(box_thick),
        "--keep_audio"
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"redact pipeline failed: {e}")

    new_out = Output(
        video_id=video_id,
        profile_hash=p_hash,
        format="mp4",
        storage_key=out_key,
        size_bytes=None,
        created_at=datetime.utcnow(),
    )
    db.add(new_out)
    db.commit()
    db.refresh(new_out)

    return {
        "cached": False,
        "profile_hash": p_hash,
        "storage_key": out_key,
        "stream_url": make_stream_url(out_key),
        "plan_id": str(plan.id),
        "output_id": str(new_out.id),
    }