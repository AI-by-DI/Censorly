from __future__ import annotations
from typing import Optional, Dict, List
from datetime import datetime
import json, hashlib, os, subprocess, tempfile

from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session

from data.schema import (
    PreferenceProfile, VideoAsset, AnalysisJob, DetectionEvent, RedactionPlan
)

CAT_KEYS = ["alcohol", "blood", "violence", "phobic", "obscene"]
DEFAULT_THRESH = 0.40
DEFAULT_BLUR = {"blur_k": 61, "box_thick": 4, "hold_gap_ms": 600, "grace_ms": 200}

OUT_PREFIX = os.getenv("REDACT_OUT_PREFIX", "uploads/redacted").rstrip("/")
JOBS_JSONL_PREFIX = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs").strip("/")
APP_ROOT = os.getenv("APP_ROOT", "/app")

def make_stream_url(storage_key: str) -> str:
    if storage_key.startswith("minio://"):
        return storage_key
    return "/" + storage_key.lstrip("/")

def profile_to_dict(p: PreferenceProfile) -> dict:
    mode_val = p.mode.value if getattr(p.mode, "value", None) is not None else (p.mode or "blur")
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
        allow = amap.get(ck, flags.get(f"allow_{ck}", True))
        if allow is False:
            out.append(ck)
    return out

def thresholds_from_profile(profile_dict: Dict) -> Dict[str, float]:
    ex = profile_dict.get("extras") or {}
    th = ex.get("thresholds") or {}
    per = {k: float(v) for k, v in th.items()}
    per.setdefault("default", DEFAULT_THRESH)
    return per

def blur_params_from_profile(profile_dict: Dict) -> Dict:
    ex = profile_dict.get("extras") or {}
    blur = ex.get("blur_params") or {}
    return {**DEFAULT_BLUR, **{k:int(v) for k,v in blur.items()}}

def get_latest_done_job(db: Session, video_id: str) -> Optional[AnalysisJob]:
    q = (
        select(AnalysisJob)
        .where(and_(AnalysisJob.video_id == video_id, AnalysisJob.status == "done"))
        .order_by(desc(AnalysisJob.finished_at), desc(AnalysisJob.created_at))
        .limit(1)
    )
    return db.execute(q).scalars().first()

def _jsonl_abs(job_id: str) -> str:
    return os.path.join(APP_ROOT, JOBS_JSONL_PREFIX, job_id, "jsonl")

def _jsonl_from_db(db: Session, job_id: str) -> str:
    rows = db.execute(
        select(DetectionEvent)
        .where(DetectionEvent.job_id == job_id)
        .order_by(DetectionEvent.ts_ms.asc())
    ).scalars().all()
    tmp = tempfile.NamedTemporaryFile(prefix=f"jsonl_{job_id}_", delete=False)
    path = tmp.name
    tmp.close()
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts_ms": int(r.ts_ms),
                "label": getattr(r.label, "value", r.label),
                "score": float(r.score),
                "bbox":  getattr(r, "bbox", None) or None,
                "track_id": getattr(r, "track_id", None),
            }, ensure_ascii=False) + "\n")
    return path

def render_or_get(db: Session, user_id: str, video_id: str, profile_id: Optional[str] = None) -> Dict:
    # 1) profil
    if profile_id:
        prof = db.get(PreferenceProfile, profile_id)
    else:
        prof = (db.execute(
            select(PreferenceProfile)
            .where(PreferenceProfile.user_id == user_id)
            .order_by(desc(PreferenceProfile.updated_at))
            .limit(1)
        ).scalars().first())
    if not prof:
        raise ValueError("Preference profile not found.")

    p_dict = profile_to_dict(prof)
    p_hash = compute_profile_hash(p_dict)
    blocked = blocked_categories(p_dict)

    # video
    vid = db.get(VideoAsset, video_id)
    if not vid:
        raise ValueError("Video not found.")

    # sansür yoksa orijinali dön
    if not blocked:
        return {
            "cached": True,
            "profile_hash": p_hash,
            "storage_key": vid.storage_key,
            "stream_url": make_stream_url(vid.storage_key),
            "plan_id": None,
            "output_id": None,
        }

    # 3) analiz job
    job = get_latest_done_job(db, video_id)
    if not job:
        raise ValueError("No completed analysis job for this video.")

    # 4) plan
    plan = (db.execute(
        select(RedactionPlan)
        .where(and_(RedactionPlan.video_id == video_id, RedactionPlan.profile_hash == p_hash))
        .limit(1)
    ).scalars().first())

    thr_map = thresholds_from_profile(p_dict)
    blur = blur_params_from_profile(p_dict)

    if not plan:
        rows = (db.execute(
            select(DetectionEvent)
            .where(DetectionEvent.job_id == job.id)
            .order_by(DetectionEvent.ts_ms)
        ).scalars().all())

        markers = []
        for r in rows:
            lab = getattr(r.label, "value", r.label)
            if lab not in blocked:
                continue
            mthr = float(thr_map.get(lab, thr_map["default"]))
            if float(r.score) >= mthr:
                markers.append({"t": int(r.ts_ms), "label": lab, "score": float(r.score)})

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

    # 5) çıktı üret (dosyaya)
    out_key = f"{OUT_PREFIX}/{video_id}/{p_hash}.mp4"
    if not out_key.startswith("minio://"):
        os.makedirs(os.path.dirname(out_key), exist_ok=True)

    # JSONL
    jsonl_path = _jsonl_abs(str(job.id))
    if not os.path.exists(jsonl_path):
        jsonl_path = _jsonl_from_db(db, str(job.id))

    # video kaynağı
    video_arg = vid.storage_key

    # min_score_map
    min_map = plan.plan.get("min_score_map", {"default": DEFAULT_THRESH})
    min_map_str = ",".join([f"{k}:{float(v):.2f}" for k, v in min_map.items()])

    # SADECE engellenen etiketleri işle
    labels_arg = ",".join(blocked) if blocked else ""

    blur_k = int(plan.plan.get("blur_params", {}).get("blur_k", DEFAULT_BLUR["blur_k"]))
    box_thick = int(plan.plan.get("blur_params", {}).get("box_thick", DEFAULT_BLUR["box_thick"]))
    hold_gap_ms = int(plan.plan.get("blur_params", {}).get("hold_gap_ms", DEFAULT_BLUR["hold_gap_ms"]))
    grace_ms = int(plan.plan.get("blur_params", {}).get("grace_ms", DEFAULT_BLUR["grace_ms"]))

    # opsiyonel dinamik eşik dosyası
    ex = p_dict.get("extras") or {}
    thresholds_json_path = ex.get("thresholds_json_path") or ""
    dyn_from_json = ex.get("dyn_from_json") or "blood,alcohol"

    cmd = [
        "python", "-m", "ai.inference.pipeline_redact",
        "--video", video_arg,
        "--jsonl", jsonl_path,
        "--out", out_key,
        "--labels", labels_arg,
        "--min_score_map", min_map_str,
        "--hold_gap_ms", str(hold_gap_ms),
        "--grace_ms", str(grace_ms),
        "--mode", "blur",
        "--blur_k", str(blur_k),
        "--box_thick", str(box_thick),
        "--keep_audio",
        "--min_keyframes_map", "default:1",
    ]
    if thresholds_json_path and os.path.exists(thresholds_json_path):
        cmd += ["--thresholds_json", thresholds_json_path, "--dyn_from_json", str(dyn_from_json)]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="ignore")
        raise RuntimeError(f"redact pipeline failed: {err[:600]}")

    return {
        "cached": False,
        "profile_hash": p_hash,
        "storage_key": out_key,
        "stream_url": make_stream_url(out_key),
        "plan_id": str(plan.id),
        "output_id": None,
    }
