from __future__ import annotations

import os, json, tempfile, subprocess, logging
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple, Generator
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from data.schema import PreferenceProfile, VideoAsset, AnalysisJob, DetectionEvent

log = logging.getLogger("api.redaction_stream")

# ------------ Sabitler / Eşikler ------------
CAT_KEYS = ["alcohol", "blood", "violence", "phobic", "obscene"]

DEFAULT_THRESH = 0.40
DEFAULT_BLUR = {"blur_k": 80, "box_thick": 4, "hold_gap_ms": 600, "grace_ms": 200}

JOBS_PREFIX  = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs").strip("/")
APP_ROOT     = os.getenv("APP_ROOT", "/app")

CATEGORY_LABELS: Dict[str, List[str]] = {
    "alcohol":  ["alcohol"],
    "blood":    ["blood"],
    "violence": ["violence"],
    "phobic":   ["Clown", "Spider", "Snake"],   # fallback
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

# phobic alt sınıflar için kanonik adlar
_PHOBIC_CANON = {"clown": "Clown", "spider": "Spider", "snake": "Snake"}
_PHOBIC_CANON_SET = set(_PHOBIC_CANON.values())

# ---------------- FFmpeg yardımcıları ----------------
def _ffprobe_duration(path: str) -> float:
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             path],
            capture_output=True, text=True
        )
        return float(p.stdout.strip() or 0.0)
    except Exception:
        return 0.0

def _has_audio(path: str) -> bool:
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1", path],
            capture_output=True, text=True
        )
        return "codec_type=audio" in (p.stdout or "")
    except Exception:
        p = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-f", "null", "-"],
                           capture_output=True, text=True)
        return "Audio:" in (p.stderr or "")

@dataclass
class Interval:
    start_ms: int
    end_ms: int

def _merge_intervals(ints: List[Interval], join_gap_ms: int) -> List[Interval]:
    if not ints: return []
    ints = sorted(ints, key=lambda x: x.start_ms)
    out = [ints[0]]
    for cur in ints[1:]:
        last = out[-1]
        if cur.start_ms <= last.end_ms + join_gap_ms:
            last.end_ms = max(last.end_ms, cur.end_ms)
        else:
            out.append(Interval(cur.start_ms, cur.end_ms))
    return out

def _load_events_from_jsonl(jsonl_path: str) -> list[dict]:
    evs: list[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                evs.append(json.loads(line))
            except Exception:
                pass
    return evs

def _calc_skip_intervals(jsonl_path: str,
                         labels_skip: List[str],
                         min_score_map: Dict[str, float],
                         hold_gap_ms: int,
                         grace_ms: int,
                         min_skip_ms: int) -> List[Interval]:
    if not labels_skip:
        return []
    events = _load_events_from_jsonl(jsonl_path)
    wanted = set(labels_skip)
    ints: List[Interval] = []
    for e in events:
        lab = str(e.get("label") or "")
        if lab not in wanted:
            continue
        sc = float(e.get("score") or 0.0)
        thr = float(min_score_map.get(lab, min_score_map.get("default", DEFAULT_THRESH)))
        if sc < thr:
            continue
        ts = int(e.get("ts_ms") or 0)
        ints.append(Interval(max(0, ts - grace_ms), ts + grace_ms))
    merged = _merge_intervals(ints, hold_gap_ms)
    return [iv for iv in merged if (iv.end_ms - iv.start_ms) >= max(0, min_skip_ms)]

def _invert_to_keep(total_ms: int, skips: List[Interval]) -> List[Interval]:
    if total_ms <= 0: return []
    if not skips: return [Interval(0, total_ms)]
    out: List[Interval] = []
    cur = 0
    for s in skips:
        if s.start_ms > cur:
            out.append(Interval(cur, s.start_ms))
        cur = max(cur, s.end_ms)
    if cur < total_ms:
        out.append(Interval(cur, total_ms))
    return [iv for iv in out if iv.end_ms > iv.start_ms]

def _build_audio_filter_from_intervals(keep: List[Interval]) -> Tuple[str, List[str]]:
    if not keep:
        return ("anullsrc=r=48000:cl=stereo,atrim=0:0.1[aout]", [])
    parts, labels = [], []
    for i, iv in enumerate(keep):
        ss = iv.start_ms / 1000.0
        ee = iv.end_ms   / 1000.0
        parts.append(
            f"[1:a]atrim=start={ss:.3f}:end={ee:.3f},asetpts=N/SR/TB,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{i}]"
        )
        labels.append(f"[a{i}]")
    fc = ";".join(parts) + f";{''.join(labels)}concat=n={len(labels)}:v=0:a=1,aresample=async=1:first_pts=0[aout]"
    return (fc, [])

# ---------------- Profil okuma / normalizasyon ----------------
def _is_uuid_like(s: str) -> bool:
    try:
        UUID(str(s)); return True
    except Exception:
        return False

def _get_profile(db: Session, current_user_id: str, profile_id: Optional[str]):
    order_col = getattr(PreferenceProfile, "updated_at", None) or getattr(PreferenceProfile, "id")
    if not profile_id or str(profile_id).lower() in ("active", "default"):
        q = (select(PreferenceProfile)
             .where(PreferenceProfile.user_id == current_user_id)
             .order_by(desc(order_col)).limit(1))
        return db.execute(q).scalars().first()
    if _is_uuid_like(profile_id):
        q = (select(PreferenceProfile)
             .where(and_(PreferenceProfile.user_id==current_user_id,
                         PreferenceProfile.id==UUID(str(profile_id))))
             .limit(1))
        return db.execute(q).scalars().first()
    if hasattr(PreferenceProfile, "slug"):
        q = (select(PreferenceProfile)
             .where(and_(PreferenceProfile.user_id==current_user_id,
                         PreferenceProfile.slug==str(profile_id)))
             .limit(1))
        prof = db.execute(q).scalars().first()
        if prof: return prof
    if hasattr(PreferenceProfile, "name"):
        q = (select(PreferenceProfile)
             .where(and_(PreferenceProfile.user_id==current_user_id,
                         PreferenceProfile.name==str(profile_id)))
             .limit(1))
        prof = db.execute(q).scalars().first()
        if prof: return prof
    return None

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

# ---------------- JSONL / Job yardımcıları ----------------
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

            # 🔴 phobic alt sınıf kanonikleştirme (iç içe extra desteği)
            raw = _raw_from_extra(extra)
            canon = None
            if raw:
                s = str(raw).strip().lower()
                if s.startswith("phobic/"):
                    s = s.split("/", 1)[-1]
                canon = _PHOBIC_CANON.get(s)


            out_label = canon or lab

            f.write(json.dumps({
                "ts_ms": int(r.ts_ms),
                "label": str(out_label),
                "score": float(r.score),
                "bbox":  getattr(r, "bbox", None) or None,
                "track_id": getattr(r, "track_id", None),
            }, ensure_ascii=False) + "\n")
    log.warning(f"[stream] JSONL not found on disk → generating from DB: job_id={job_id}")
    return path

def _ensure_canon_labels_jsonl(jsonl_path: str) -> str:
    """
    Eldeki JSONL içinde label=phobic + raw_label/subtype Clown|Spider|Snake ise
    label alanını kanonik alt sınıfa çevirir. Değişiklik yaparsa temp dosya
    döner, aksi halde orijinal path'i geri verir.
    """
    try:
        changed = False
        out = tempfile.NamedTemporaryFile(prefix="jsonl_fix_", delete=False)
        out_path = out.name
        out.close()

        with open(jsonl_path, "r", encoding="utf-8") as inp, open(out_path, "w", encoding="utf-8") as out_f:
            for line in inp:
                try:
                    obj = json.loads(line)
                except Exception:
                    out_f.write(line)
                    continue

                lab = str(obj.get("label") or "")
                if lab.lower() == "phobic":
                    raw = obj.get("raw_label") or obj.get("rawLabel") or obj.get("subtype")
                    if raw:
                        s = str(raw).strip().lower()
                        if s.startswith("phobic/"):
                            s = s.split("/", 1)[-1]
                        canon = _PHOBIC_CANON.get(s)
                        if canon:
                            obj["label"] = canon
                            changed = True

                out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")

        if changed:
            return out_path
        else:
            try: os.unlink(out_path)
            except: pass
            return jsonl_path
    except Exception:
        # bir şey olursa orijinal path'le devam et
        return jsonl_path

def _raw_from_extra(extra: dict | None) -> Optional[str]:
    """
    DetectionEvent.extra alanında raw_label bilgisi bazen iç içe ({"extra": {...}}) gelebiliyor.
    Burada tüm olası konumları deneriz.
    """
    if not isinstance(extra, dict):
        return None

    # Düz seviye
    raw = extra.get("raw_label") or extra.get("rawLabel") or extra.get("subtype")
    if raw:
        return str(raw)

    # Bir kademe iç içe: {"extra": {...}} veya {"extras": {...}}
    for k in ("extra", "extras"):
        node = extra.get(k)
        if isinstance(node, dict):
            raw = node.get("raw_label") or node.get("rawLabel") or node.get("subtype")
            if raw:
                return str(raw)

    return None


# -------------- phobic alt sınıf çözümleme --------------
def _canon_phobic_name(s: Optional[str]) -> Optional[str]:
    if not s: return None
    s = str(s).strip().lower()
    if s.startswith("phobic/"):
        s = s.split("/", 1)[-1]
    return _PHOBIC_CANON.get(s)

def _canon_from_label_or_extra(label: str, extra: dict | None) -> Optional[str]:
    if str(label) in _PHOBIC_CANON_SET:
        return str(label)
    by_label = _canon_phobic_name(label)
    if by_label:
        return by_label
    if isinstance(extra, dict):
        raw = _raw_from_extra(extra)
        by_extra = _canon_phobic_name(raw)
        if by_extra:
            return by_extra

    return None

def _discover_phobic_sublabels(db: Session, job_id: str) -> List[str]:
    rows = db.execute(
        select(DetectionEvent)
        .where(DetectionEvent.job_id == job_id)
        .order_by(DetectionEvent.ts_ms.asc())
    ).scalars().all()
    found: List[str] = []
    for r in rows:
        lab = getattr(r.label, "value", r.label)
        extra = getattr(r, "extra", None) or getattr(r, "extras", None) or {}
        canon = _canon_from_label_or_extra(lab, extra)
        if canon:
            found.append(canon)
    return sorted(list(dict.fromkeys(found)))

# -------------- Etiket map'leri --------------
def _labels_from_mode_map(db: Session, job_id: str, mode_map: Dict[str,str]) -> Tuple[List[str], List[str], List[str]]:
    blur, red, skip = [], [], []

    def add_labels(key: str, mode: str):
        mode_l = (mode or "").strip().lower()
        if mode_l not in ("blur", "red", "skip"):
            return

        k_raw = (key or "").strip()
        k = k_raw.lower()

        # 🔧 phobic/alt-sınıf anahtarlarını normalize et (phobic/clown → Clown)
        if k.startswith("phobic/"):
            sub = k.split("/", 1)[-1]  # clown | spider | snake
            if sub in _PHOBIC_CANON:
                lbls = [_PHOBIC_CANON[sub]]  # 'Clown' / 'Spider' / 'Snake'
            else:
                lbls = CATEGORY_LABELS.get("phobic", [])
        elif k in ("nudity", "obscene"):
            lbls = CATEGORY_LABELS["nudity"]
        elif k == "phobic":
            found = _discover_phobic_sublabels(db, job_id)
            lbls = found if found else CATEGORY_LABELS["phobic"]
        elif k in _PHOBIC_CANON:  # 'clown' | 'spider' | 'snake'
            lbls = [_PHOBIC_CANON[k]]
        elif k in CATEGORY_LABELS:
            lbls = CATEGORY_LABELS[k]
        else:
            # serbest metin etiketleri olduğu gibi gönder
            lbls = [k_raw]

        if mode_l == "blur":
            blur.extend(lbls)
        elif mode_l == "red":
            red.extend(lbls)
        else:
            skip.extend(lbls)

    for k, v in (mode_map or {}).items():
        add_labels(k, v)

    mkuniq = lambda xs: sorted(list(dict.fromkeys(xs)))
    return mkuniq(blur), mkuniq(red), mkuniq(skip)

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

# -------------- Canlı stream (redactions.download ile aynı mantık) --------------
def stream_blur_live(db: Session, user_id: str, video_id: str, profile_id: str | None):
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
        if not (labels_blur or labels_red or labels_skip):
            return StreamingResponse(open(vid.storage_key, "rb"), media_type="video/mp4")
    else:
        return StreamingResponse(open(vid.storage_key, "rb"), media_type="video/mp4")

    video_arg = vid.storage_key
    if not os.path.exists(video_arg):
        raise FileNotFoundError(f"Video file not found: {video_arg}")

    min_map = _build_min_score_map(ex)
    min_map_str = ",".join([f"{k}:{float(v):.2f}" for k,v in min_map.items()])

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
        "--keep_audio",
        "--min_keyframes_map", "default:1",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        err = (proc.stderr or b"").decode(errors="ignore")
        log.error("[stream] redact failed: %s", err[-1000:])
        try: os.unlink(out_path)
        except: pass
        raise ValueError("Redaction pipeline failed")

    fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    if labels_skip:
        orig_ms = int(_ffprobe_duration(video_arg) * 1000)
        skips = _calc_skip_intervals(
            jsonl_arg,
            labels_skip=labels_skip,
            min_score_map=_build_min_score_map(ex),
            hold_gap_ms=int((ex.get("blur_params") or {}).get("hold_gap_ms", 600)),
            grace_ms=int((ex.get("blur_params") or {}).get("grace_ms", 200)),
            min_skip_ms=2000,
        )
        keep = _invert_to_keep(orig_ms, skips)
        fc, _ = _build_audio_filter_from_intervals(keep)
        remux = subprocess.run(
            ["ffmpeg","-y","-fflags","+genpts",
             "-i", out_path, "-i", video_arg,
             "-filter_complex", fc,
             "-map","0:v:0","-map","[aout]",
             "-c:v","libx264","-preset","veryfast","-crf","22","-pix_fmt","yuv420p",
             "-c:a","aac","-b:a","128k",
             "-shortest","-movflags","+faststart", fixed_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    else:
        if _has_audio(out_path):
            remux = subprocess.run(
                ["ffmpeg","-y","-fflags","+genpts","-i",out_path,
                 "-map","0:v:0","-map","0:a:0?",
                 "-c:v","libx264","-preset","veryfast","-crf","22","-pix_fmt","yuv420p",
                 "-c:a","aac","-b:a","128k","-movflags","+faststart", fixed_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        else:
            remux = subprocess.run(
                ["ffmpeg","-y","-fflags","+genpts",
                 "-i",out_path,"-i",video_arg,
                 "-map","0:v:0","-map","1:a:0?",
                 "-c:v","libx264","-preset","veryfast","-crf","22","-pix_fmt","yuv420p",
                 "-c:a","aac","-b:a","128k",
                 "-shortest","-movflags","+faststart", fixed_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

    try: os.unlink(out_path)
    except: pass

    path_to_send = fixed_path if (remux.returncode == 0 and os.path.exists(fixed_path)) else out_path
    f = open(path_to_send, "rb")

    def _iter() -> Generator[bytes, None, None]:
        try:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk: break
                yield chunk
        finally:
            try: f.close()
            except: pass
            try: os.unlink(path_to_send)
            except: pass

    headers = {"Content-Type": "video/mp4", "Cache-Control": "no-store"}
    return StreamingResponse(_iter(), headers=headers, media_type="video/mp4")

# -------------- public export --------------
__all__ = [
    "_get_profile", "profile_to_dict",
    "_latest_done_job", "_jsonl_path_abs", "_build_jsonl_from_db",
    "_build_min_score_map", "_labels_from_mode_map",
    "_ffprobe_duration", "_build_audio_filter_from_intervals",
    "_calc_skip_intervals", "_invert_to_keep",
    "_ensure_canon_labels_jsonl",        
    "stream_blur_live",
]

