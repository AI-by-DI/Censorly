# apps/api/services/redaction_stream.py (yalnızca stream_blur_live fonksiyonunu değiştir)
from __future__ import annotations
import os, json, hashlib, tempfile, subprocess
from typing import Optional, Dict, List, Generator
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse
from sqlalchemy import select, and_, desc, or_

from data.schema import PreferenceProfile, VideoAsset, AnalysisJob
import logging
log = logging.getLogger("uvicorn.error")

CAT_KEYS = ["alcohol","blood","violence","phobic","obscene"]
DEFAULT_THRESH = 0.40
DEFAULT_BLUR = {"blur_k": 61, "box_thick": 4, "hold_gap_ms": 600, "grace_ms": 200}
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")
JOBS_PREFIX  = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs")
APP_ROOT     = os.getenv("APP_ROOT", "/app")

# --- mevcut yardımcılarını kullan ---
def _get_profile(db: Session, current_user_id: str, profile_id: str | None):
    if profile_id:
        prof = db.execute(
            select(PreferenceProfile)
            .where(or_(PreferenceProfile.id == profile_id, PreferenceProfile.user_id == profile_id))
            .order_by(desc(PreferenceProfile.updated_at))
            .limit(1)
        ).scalars().first()
        if prof and str(prof.user_id) != str(current_user_id):
            prof = None
        if prof:
            return prof
    return db.execute(
        select(PreferenceProfile)
        .where(PreferenceProfile.user_id == current_user_id)
        .order_by(desc(PreferenceProfile.updated_at))
        .limit(1)
    ).scalars().first()

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

def _hash(d: Dict) -> str:
    import json, hashlib
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]

def _blocked(pd: Dict) -> List[str]:
    amap = pd.get("allow_map", {}) or {}
    flags = pd["allow_flags"]
    out = []
    for k in CAT_KEYS:
        base = flags.get(f"allow_{k}", True)
        allow = amap.get(k, base)
        if allow is False:
            out.append(k)
    return out

def _thr_map(pd: Dict) -> Dict[str,float]:
    ex = pd.get("extras") or {}
    th = {k: float(v) for k,v in (ex.get("thresholds") or {}).items()}
    th.setdefault("default", DEFAULT_THRESH)
    return th

def _blur(pd: Dict) -> Dict[str,int]:
    ex = pd.get("extras") or {}
    merged = {**DEFAULT_BLUR, **{k:int(v) for k,v in (ex.get("blur_params") or {}).items()}}
    return merged

def _latest_done_job(db: Session, video_id: str) -> Optional[AnalysisJob]:
    from sqlalchemy import select, and_, desc
    q = (select(AnalysisJob)
         .where(and_(AnalysisJob.video_id==video_id, AnalysisJob.status=="done"))
         .order_by(desc(AnalysisJob.finished_at), desc(AnalysisJob.created_at))
         .limit(1))
    return db.execute(q).scalars().first()

def _jsonl_path_abs(job_id: str) -> str:
    # APP_ROOT + uploads/jobs/<job_id>/jsonl
    base = os.path.join(APP_ROOT, JOBS_PREFIX.strip("/"))
    return os.path.join(base, job_id, "jsonl")

def _build_jsonl_from_db(db: Session, job_id: str) -> str:
    # detection_events'ten JSONL temp üret
    from sqlalchemy import select
    from data.schema import DetectionEvent
    rows = db.execute(
        select(DetectionEvent).where(DetectionEvent.job_id==job_id).order_by(DetectionEvent.ts_ms.asc())
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
                "bbox":  r.bbox or None,
                "track_id": r.track_id,
            }, ensure_ascii=False) + "\n")
    log.warning(f"[stream] JSONL not found on disk → generating from DB: job_id={job_id}")
    return path

def stream_blur_live(db: Session, user_id: str, video_id: str, profile_id: Optional[str]):
    # 1) profil & ayarlar
    prof = _get_profile(db, current_user_id=user_id, profile_id=profile_id)
    if not prof:
        raise ValueError(f"Preference profile not found (user_id={user_id}, profile_id={profile_id})")
    pd   = profile_to_dict(prof)
    bh   = _hash(pd)
    cats = _blocked(pd)
    thr  = _thr_map(pd)
    blur = _blur(pd)
    log.info(f"[stream] user_id={user_id} video_id={video_id} profile_id={profile_id} profile_hash={bh}")
    log.info(f"[stream] blocked={cats} thresholds={thr} blur={blur}")

    # Sansür yoksa orijinali döndür
    vid = db.get(VideoAsset, video_id)
    if not vid:
        raise ValueError(f"Video not found (video_id={video_id}).")
    if not cats:
        return StreamingResponse(open(vid.storage_key, "rb"), media_type="video/mp4")

    # 2) job & jsonl
    job = _latest_done_job(db, video_id)
    if not job:
        raise ValueError(f"No completed analysis for this video (video_id={video_id}).")

    jsonl_arg = _jsonl_path_abs(str(job.id))
    if not os.path.exists(jsonl_arg):
        jsonl_arg = _build_jsonl_from_db(db, str(job.id))

    # 3) video kaynağı
    video_arg = vid.storage_key
    if not os.path.exists(video_arg):
        raise FileNotFoundError(f"Video file not found: {video_arg}")

    # 4) redact → TEMP DOSYA (stdout değil)
    min_map_str = ",".join([f"{k}:{float(v):.2f}" for k,v in thr.items()])

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    out_path = tmp.name

    cmd = [
        "python","-m","ai.inference.pipeline_redact",
        "--video", video_arg,
        "--jsonl", jsonl_arg,
        "--out", out_path,                 # ← stdout yerine dosya
        "--min_score_map", min_map_str,
        "--hold_gap_ms", str(blur["hold_gap_ms"]),
        "--grace_ms",    str(blur["grace_ms"]),
        "--mode", "blur",
        "--blur_k", str(blur["blur_k"]),
        "--box_thick", str(blur["box_thick"]),
        "--keep_audio",                      # doğru argüman
    ]
    log.info(f"[stream] cmd={' '.join(cmd)}")

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        err = (proc.stderr or b"").decode(errors="ignore")
        log.error("[stream] pipeline stderr: %s", err)
        try: os.unlink(out_path)
        except: pass
        raise ValueError("Redaction pipeline failed")

    # (opsiyonel) QuickTime/tarayıcı hızlı başlatma için faststart remux
    fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    remux = subprocess.run(
        ["ffmpeg", "-y", "-i", out_path, "-c", "copy", "-movflags", "+faststart", fixed_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try: os.unlink(out_path)
    except: pass
    if remux.returncode != 0 or not os.path.exists(fixed_path):
        # remux başarısızsa faststart’sız dosyayı stream etmeyi deneyelim
        fixed_path = fixed_path if os.path.exists(fixed_path) else None

    # 5) dosyayı stream et, bittiğinde temizle
    path_to_send = fixed_path or out_path
    f = open(path_to_send, "rb")

    def _iter() -> Generator[bytes, None, None]:
        try:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            try: f.close()
            except: pass
            try: os.unlink(path_to_send)
            except: pass

    headers = {
        "Content-Type": "video/mp4",
        "Cache-Control": "no-store",
        # "Content-Disposition": "inline"  # tarayıcıda oynat
    }
    return StreamingResponse(_iter(), headers=headers, media_type="video/mp4")