from __future__ import annotations

import os, json, hashlib, tempfile, subprocess, logging
from typing import Optional, Dict, List, Generator, Tuple
from sqlalchemy import select, and_, desc, or_
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from data.schema import PreferenceProfile, VideoAsset, AnalysisJob, DetectionEvent

log = logging.getLogger("uvicorn.error")

CAT_KEYS = ["alcohol", "blood", "violence", "phobic", "obscene"]

DEFAULT_THRESH = 0.40
DEFAULT_BLUR = {"blur_k": 80, "box_thick": 4, "hold_gap_ms": 600, "grace_ms": 200}

JOBS_PREFIX  = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs").strip("/")
APP_ROOT     = os.getenv("APP_ROOT", "/app")

CATEGORY_LABELS: Dict[str, List[str]] = {
    "alcohol":  ["alcohol"],
    "blood":    ["blood"],
    "violence": ["violence"],
    "phobic":   ["Clown", "Spider", "Snake"],
    "obscene":  ["nudenet"],
    "nudity":   ["nudenet"],
}

BASE_LABEL_THRESHOLDS: Dict[str, float] = {
    "violence": 0.35,
    "nudenet":  0.45,
    "Clown":    0.10,
    "Spider":   0.20,
    "Snake":    0.20,
    "blood":    0.16,
    "alcohol":  0.25,
    "phobic":   0.10,
    "default":  0.30,
}

_PHOBIC_CANON = {"clown": "Clown", "spider": "Spider", "snake": "Snake"}

def _get_profile(db: Session, current_user_id: str, profile_id: Optional[str]):
    if profile_id:
        prof = (db.execute(
            select(PreferenceProfile)
            .where(or_(PreferenceProfile.id == profile_id,
                       PreferenceProfile.user_id == profile_id))
            .order_by(desc(PreferenceProfile.updated_at))
            .limit(1)
        ).scalars().first())
        if prof and str(prof.user_id) != str(current_user_id):
            prof = None
        if prof:
            return prof
    return (db.execute(
        select(PreferenceProfile)
        .where(PreferenceProfile.user_id == current_user_id)
        .order_by(desc(PreferenceProfile.updated_at))
        .limit(1)
    ).scalars().first())

def _allow_flag(v) -> bool:
    return True if v is None else bool(v)

def profile_to_dict(p: PreferenceProfile) -> dict:
    mode_val = p.mode.value if getattr(p.mode, "value", None) is not None else (p.mode or "blur")
    ex = p.extras or {}
    allow_map = getattr(p, "allow_map", None) or ex.get("allow_map", {}) or {}
    mode_map  = getattr(p, "mode_map",  None) or ex.get("mode_map",  {}) or {}
    return {
        "mode": mode_val,
        "allow_flags": {
            "allow_alcohol":  _allow_flag(getattr(p, "allow_alcohol",  None)),
            "allow_blood":    _allow_flag(getattr(p, "allow_blood",    None)),
            "allow_violence": _allow_flag(getattr(p, "allow_violence", None)),
            "allow_phobic":   _allow_flag(getattr(p, "allow_phobic",   None)),
            "allow_obscene":  _allow_flag(getattr(p, "allow_obscene",  None)),
        },
        "allow_map": allow_map,
        "mode_map":  mode_map,
        "extras":    ex,
    }

def _blocked_from_allow(pd: Dict) -> List[str]:
    amap = pd.get("allow_map", {}) or {}
    flags = pd["allow_flags"]
    out: List[str] = []
    for k in CAT_KEYS:
        base = flags.get(f"allow_{k}", True)
        allow = amap.get(k, base)
        if allow is False:
            out.append(k)
    return out

def _blur(pd: Dict) -> Dict[str,int]:
    ex = pd.get("extras") or {}
    merged = {**DEFAULT_BLUR, **{k:int(v) for k,v in (ex.get("blur_params") or {}).items()}}
    return merged

def _latest_done_job(db: Session, video_id: str) -> Optional[AnalysisJob]:
    q = (select(AnalysisJob)
         .where(and_(AnalysisJob.video_id==video_id, AnalysisJob.status=="done"))
         .order_by(desc(AnalysisJob.finished_at), desc(AnalysisJob.created_at))
         .limit(1))
    return db.execute(q).scalars().first()

def _jsonl_path_abs(job_id: str) -> str:
    base = os.path.join(APP_ROOT, JOBS_PREFIX)
    return os.path.join(base, job_id, "jsonl")

def _build_jsonl_from_db(db: Session, job_id: str) -> str:
    rows = db.execute(
        select(DetectionEvent)
        .where(DetectionEvent.job_id==job_id)
        .order_by(DetectionEvent.ts_ms.asc())
    ).scalars().all()
    tmp = tempfile.NamedTemporaryFile(prefix=f"jsonl_{job_id}_", delete=False)
    path = tmp.name
    tmp.close()
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            lab = getattr(r.label, "value", r.label)
            extra = getattr(r, "extra", None) or getattr(r, "extras", None) or {}
            raw = None
            if isinstance(extra, dict):
                raw = extra.get("raw_label") or extra.get("rawLabel") or extra.get("subtype")
            f.write(json.dumps({
                "ts_ms": int(r.ts_ms),
                "label": str(lab),
                "score": float(r.score),
                "bbox":  getattr(r, "bbox", None) or None,
                "track_id": getattr(r, "track_id", None),
                "raw_label": raw or None,
            }, ensure_ascii=False) + "\n")
    log.warning(f"[stream] JSONL not found on disk → generating from DB: job_id={job_id}")
    return path

def _canon_phobic_name(s: str) -> Optional[str]:
    if not s: return None
    return _PHOBIC_CANON.get(str(s).strip().lower())

def _discover_phobic_sublabels(db: Session, job_id: str) -> List[str]:
    rows = db.execute(
        select(DetectionEvent)
        .where(DetectionEvent.job_id == job_id)
        .order_by(DetectionEvent.ts_ms.asc())
    ).scalars().all()
    found: List[str] = []
    for r in rows:
        lab = getattr(r.label, "value", r.label)
        if str(lab).lower() != "phobic":
            continue
        extra = getattr(r, "extra", None) or getattr(r, "extras", None) or {}
        raw = None
        if isinstance(extra, dict):
            raw = extra.get("raw_label") or extra.get("rawLabel") or extra.get("subtype")
        canon = _canon_phobic_name(raw)
        if canon:
            found.append(canon)
    uniq = sorted(list(dict.fromkeys(found)))
    return uniq

def _labels_from_mode_map(db: Session, job_id: str, mode_map: Dict[str,str]) -> Tuple[List[str], List[str], List[str]]:
    blur, red, skip = [], [], []

    def add_labels(key: str, mode: str):
        mode_l = (mode or "").strip().lower()
        if mode_l not in ("blur", "red", "skip"):
            return
        k = key.strip().lower()
        if k in ("nudity", "obscene"):
            lbls = CATEGORY_LABELS["nudity"]
        elif k == "phobic":
            found = _discover_phobic_sublabels(db, job_id)
            lbls = found if found else CATEGORY_LABELS["phobic"]
        elif k in _PHOBIC_CANON:
            lbls = [_PHOBIC_CANON[k]]
        elif k in CATEGORY_LABELS:
            lbls = CATEGORY_LABELS[k]
        else:
            lbls = [key]  # doğrudan label
        if mode_l == "blur": blur.extend(lbls)
        elif mode_l == "red": red.extend(lbls)
        else: skip.extend(lbls)

    for k, v in (mode_map or {}).items():
        add_labels(k, v)

    # uniq + sıralı
    mkuniq = lambda xs: sorted(list(dict.fromkeys(xs)))
    return mkuniq(blur), mkuniq(red), mkuniq(skip)

def _labels_from_allow(db: Session, job_id: str, pd: Dict) -> List[str]:
    cats = _blocked_from_allow(pd)
    labels: List[str] = []
    for cat in cats:
        if cat == "phobic":
            dyn = _discover_phobic_sublabels(db, job_id)
            labels.extend(dyn if dyn else CATEGORY_LABELS["phobic"])
        elif cat in CATEGORY_LABELS:
            labels.extend(CATEGORY_LABELS[cat])
        elif cat in _PHOBIC_CANON:
            labels.append(_PHOBIC_CANON[cat])
    return sorted(list(dict.fromkeys(labels)))

def _load_dynamic_on_thresholds(json_path: str, wanted: List[str]) -> Dict[str, float]:
    try:
        if not json_path or not os.path.exists(json_path):
            return {}
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        thr = (data.get("thresholds") or {})
        out: Dict[str,float] = {}
        for lab in wanted:
            node = thr.get(lab)
            if isinstance(node, dict) and "on" in node:
                out[lab] = float(node["on"])
        return out
    except Exception:
        return {}

def _build_min_score_map(profile_extras: Dict) -> Dict[str, float]:
    min_map: Dict[str, float] = dict(BASE_LABEL_THRESHOLDS)
    json_path  = (profile_extras or {}).get("thresholds_json_path") or ""
    dyn_from   = (profile_extras or {}).get("dyn_from_json") or "blood,alcohol"
    wanted_dyn = [s.strip() for s in dyn_from.split(",") if s.strip()]
    dyn_vals   = _load_dynamic_on_thresholds(json_path, wanted_dyn)
    for k, v in dyn_vals.items():
        min_map[k] = float(v)
    user_thr = (profile_extras or {}).get("thresholds") or {}
    for k, v in user_thr.items():
        try: min_map[str(k)] = float(v)
        except Exception: pass
    if "default" not in min_map:
        min_map["default"] = DEFAULT_THRESH
    if not any(k.lower() == "alcohol" for k in min_map.keys()):
        min_map["alcohol"] = 0.25
    return min_map

def stream_blur_live(db: Session, user_id: str, video_id: str, profile_id: Optional[str]):
    prof = _get_profile(db, current_user_id=user_id, profile_id=profile_id)
    if not prof:
        raise ValueError(f"Preference profile not found (user_id={user_id}, profile_id={profile_id})")

    pd   = profile_to_dict(prof)
    blur = _blur(pd)
    ex   = pd.get("extras") or {}

    vid = db.get(VideoAsset, video_id)
    if not vid:
        raise FileNotFoundError(f"Video not found: {video_id}")

    job = _latest_done_job(db, video_id)
    if not job:
        raise ValueError(f"No completed analysis for this video (video_id={video_id}).")

    jsonl_arg = _jsonl_path_abs(str(job.id))
    if not os.path.exists(jsonl_arg):
        jsonl_arg = _build_jsonl_from_db(db, str(job.id))

    mode_map = pd.get("mode_map") or {}

    if mode_map:
        labels_blur, labels_red, labels_skip = _labels_from_mode_map(db, str(job.id), mode_map)
        log.info(f"[profile] mode_map={mode_map}")
        log.info(f"[profile] labels_blur={labels_blur} labels_red={labels_red} labels_skip={labels_skip}")
        if not (labels_blur or labels_red or labels_skip):
            return StreamingResponse(open(vid.storage_key, "rb"), media_type="video/mp4")
    else:
        # mode_map yoksa → filtresiz (orijinal)
        return StreamingResponse(open(vid.storage_key, "rb"), media_type="video/mp4")

    video_arg = vid.storage_key
    if not os.path.exists(video_arg):
        raise FileNotFoundError(f"Video file not found: {video_arg}")

    min_map = _build_min_score_map(ex)
    min_map_str = ",".join([f"{k}:{float(v):.2f}" for k,v in min_map.items()])

    # --- pipeline çağrısı: yeni parametrelerle
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False); tmp.close()
    out_path = tmp.name

    cmd = [
        "python","-m","ai.inference.pipeline_redact",
        "--video", video_arg,
        "--jsonl", jsonl_arg,
        "--out", out_path,
        "--labels_blur", ",".join(labels_blur),
        "--labels_red",  ",".join(labels_red),
        "--labels_skip", ",".join(labels_skip),
        "--min_skip_ms", "2000",
        "--min_score_map", min_map_str,
        "--hold_gap_ms", str(blur["hold_gap_ms"]),
        "--grace_ms",    str(blur["grace_ms"]),
        "--blur_k", str(blur["blur_k"]),
        "--box_thick", str(blur["box_thick"]),
        "--keep_audio",  # skip varsa pipeline içinde devre dışı bırakılıyor
        "--min_keyframes_map", "default:1",
    ]
    log.info(f"[stream] cmd={' '.join(cmd)}")
    log.info(f"[stream] min_score_map={min_map}")

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        err = (proc.stderr or b"").decode(errors="ignore")
        out = (proc.stdout  or b"").decode(errors="ignore")
        log.error("[stream] pipeline stderr:\n%s", err)
        log.error("[stream] pipeline stdout:\n%s", out)
        try: os.unlink(out_path)
        except: pass
        raise ValueError("Redaction pipeline failed")

    fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    remux = subprocess.run(
        ["ffmpeg", "-y", "-i", out_path, "-c", "copy", "-movflags", "+faststart", fixed_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try: os.unlink(out_path)
    except: pass
    if remux.returncode != 0 or not os.path.exists(fixed_path):
        fixed_path = fixed_path if os.path.exists(fixed_path) else None

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

    headers = {"Content-Type": "video/mp4", "Cache-Control": "no-store"}
    return StreamingResponse(_iter(), headers=headers, media_type="video/mp4")


__all__ = [
    "_get_profile", "profile_to_dict",
    "_latest_done_job", "_jsonl_path_abs", "_build_jsonl_from_db",
    "_build_min_score_map", "_labels_from_mode_map",
    "stream_blur_live",
]
