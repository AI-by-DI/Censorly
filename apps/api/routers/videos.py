# apps/api/routers/videos.py
from __future__ import annotations
import os, uuid, mimetypes, hashlib, subprocess, json
from datetime import datetime
from typing import Optional, Iterable, Dict, Any, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, text
from urllib.parse import urlparse

from apps.api.core.db import get_db
from data.schema import VideoAsset, AnalysisJob, DetectionEvent
from apps.api.utils.minio_utils import (
    ensure_bucket, fput_local_to_minio, presigned_get,
    MINIO_DEFAULT_BUCKET
)

router = APIRouter(prefix="/videos", tags=["videos"])

ANALYZER_CMD   = os.getenv("ANALYZER_CMD", "python -m ai.inference.pipeline_analyze")
_DB_LABELS     = {"alcohol", "blood", "violence", "phobic", "obscene"}
_PHOBIC_CANON  = {"clown": "Clown", "spider": "Spider", "snake": "Snake"}

# ----------------- helpers -----------------
def _norm_label(label: str, extra: dict | None) -> tuple[str, dict]:
    extra = (extra or {}).copy()
    s = (label or "").strip()
    low = s.lower()

    if low.startswith("phobic/"):
        low = low.split("/", 1)[-1]
    if low in _PHOBIC_CANON:
        canon = _PHOBIC_CANON[low]
        extra.setdefault("raw_label", canon)
        return "phobic", extra
    if low in ("nudity", "obscene", "nudenet"):
        return "obscene", extra
    if s in _PHOBIC_CANON.values():
        extra.setdefault("raw_label", s)
        return "phobic", extra
    if low in _DB_LABELS:
        return low, extra
    return s, extra

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _ensure_dir(p: str):
    os.makedirs(os.path.dirname(p), exist_ok=True)

def _run_analyzer_sync(video_local_path: str, jsonl_out: str, job_id: str | None = None) -> None:
    _ensure_dir(jsonl_out)
    cmd = (
        f'{ANALYZER_CMD} '
        f'--local-path "{video_local_path}" '
        f'--out-jsonl-path "{jsonl_out}" '
        f'--generate-thresholds '
        + (f'--job-id "{job_id}" ' if job_id else '')
    ).strip()
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.exists(jsonl_out):
        stderr = (res.stderr or b"").decode(errors="ignore")
        raise RuntimeError(f"Analyzer failed. Last stderr: {stderr}")

_ALLOWED_LABELS: set[str] | None = {"alcohol", "blood", "violence", "phobic", "obscene"}

def _iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def _ingest_jsonl_to_db(db: Session, job_id: str, jsonl_path: str) -> int:
    rows: List[DetectionEvent] = []
    for obj in _iter_jsonl(jsonl_path):
        ts_ms = obj.get("ts_ms")
        label_raw = (obj.get("label") or obj.get("category") or "").strip()
        score = obj.get("score") or obj.get("confidence")
        bbox  = obj.get("bbox")
        track = obj.get("track_id")
        extra = {k: v for k, v in obj.items() if k not in {"ts_ms","label","category","score","confidence","bbox","track_id"}}
        if ts_ms is None or not label_raw:
            continue
        label_norm, extra = _norm_label(label_raw, extra)
        if not label_norm or (_ALLOWED_LABELS is not None and label_norm not in _ALLOWED_LABELS):
            continue
        rows.append(DetectionEvent(
            job_id=job_id,
            ts_ms=int(ts_ms),
            label=label_norm,
            score=float(score) if score is not None else None,
            bbox=bbox,
            track_id=track,
            extra=extra or {}
        ))
        if len(rows) >= 1000:
            db.add_all(rows); db.commit(); rows.clear()
    if rows:
        db.add_all(rows); db.commit()
    return db.query(DetectionEvent).filter(DetectionEvent.job_id == job_id).count()

def _presign_from_minio_url(minio_url: str | None, ttl_seconds: int = 3600) -> Optional[str]:
    if not minio_url or not minio_url.startswith("minio://"):
        return None
    u = urlparse(minio_url)
    bucket = u.netloc
    key = u.path.lstrip("/")
    if not bucket or not key:
        return None
    return presigned_get(bucket, key, ttl_seconds)

def _update_poster_fields(db: Session, video_id: str, key_uri: Optional[str], public_url: Optional[str]):
    """
    ORM map'li olsun/olmasın güvenli: ham SQL ile üç alanı birlikte günceller.
    - poster_key           : minio://bucket/path.ext
    - poster_storage_key   : minio://bucket/path.ext  (ayrı kolon varsa dolduralım)
    - poster_url           : presigned http(s) URL (isteğe bağlı)
    """
    db.execute(
        text("""
            UPDATE video_assets
               SET poster_key = COALESCE(:key, poster_key),
                   poster_storage_key = COALESCE(:key, poster_storage_key),
                   poster_url = COALESCE(:url, poster_url)
             WHERE id = :id
        """),
        {"key": key_uri, "url": public_url, "id": video_id}
    )
    db.commit()

def _read_poster_key(db: Session, v: VideoAsset) -> Optional[str]:
    # ORM'den dene
    try:
        val = getattr(v, "poster_key", None)
        if val:
            return val
    except Exception:
        pass
    # Raw SQL fallback
    row = db.execute(text("SELECT poster_key, poster_storage_key FROM video_assets WHERE id = :id"), {"id": str(v.id)}).first()
    if not row:
        return None
    return row[0] or row[1]

# ------------------------- LIST
@router.get("")
def list_videos(
    db: Session = Depends(get_db),
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="Filter by title substring"),
):
    # Ana sorgu
    stmt = select(VideoAsset).order_by(desc(VideoAsset.created_at), desc(VideoAsset.id))

    # 🔍 Arama filtresi — q varsa başlıkta arar (case-insensitive)
    if q:
        stmt = stmt.where(VideoAsset.title.ilike(f"%{q}%"))

    stmt = stmt.offset(offset).limit(limit)
    items = db.execute(stmt).scalars().all()

    out = []
    for v in items:
        poster_key = _read_poster_key(db, v)
        poster_url = _presign_from_minio_url(poster_key, ttl_seconds=60 * 60 * 24) if poster_key else None
        out.append({
            "id": str(v.id),
            "title": v.title or "Untitled",
            "poster_url": poster_url,
            "status": v.status,
        })
    return out


# ------------------------- DETAIL
@router.get("/{video_id}")
def video_detail(video_id: str, db: Session = Depends(get_db)):
    v = db.get(VideoAsset, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    poster_key = _read_poster_key(db, v)
    poster_url = _presign_from_minio_url(poster_key, ttl_seconds=60*60*24) if poster_key else None
    return {
        "id": str(v.id),
        "title": v.title or "Untitled",
        "storage_key": v.storage_key,
        "poster_url": poster_url,
        "size_bytes": v.size_bytes,
        "checksum_sha256": v.checksum_sha256,
        "status": v.status,
    }

# ------------------------- UPLOAD (video + poster)  — poster alanlarını AYNI ENDPOINT’TE günceller
@router.post("/upload")
async def upload_video(
    db: Session = Depends(get_db),

    file: UploadFile = File(..., description="Ana video dosyası (mp4)"),
    poster: UploadFile | None = File(None, description="Kapak görseli (jpg/png)"),

    title: Optional[str] = Query(None),
    source_url: Optional[str] = Query(None),
):
    tmp_video  = os.path.join("/tmp", f"{uuid.uuid4().hex}_{file.filename or 'video.mp4'}")
    tmp_poster = None

    try:
        ensure_bucket(MINIO_DEFAULT_BUCKET)

        # temp yaz
        with open(tmp_video, "wb") as f:
            f.write(await file.read())
        if poster is not None:
            tmp_poster = os.path.join("/tmp", f"{uuid.uuid4().hex}_{poster.filename or 'poster.jpg'}")
            with open(tmp_poster, "wb") as pf:
                pf.write(await poster.read())

        # id / object isimleri
        video_id  = str(uuid.uuid4())
        v_ext     = os.path.splitext(file.filename or "")[-1] or ".mp4"
        video_obj = f"videos/{video_id}{v_ext}"

        poster_obj = None
        if tmp_poster:
            p_ext = os.path.splitext(poster.filename or "")[-1] or ".jpg"
            poster_obj = f"posters/{video_id}{p_ext}"

        # poster → MinIO (varsa)
        poster_key_uri = None
        poster_public  = None
        if poster_obj:
            poster_mime = mimetypes.guess_type(poster.filename or "")[0] or "image/jpeg"
            fput_local_to_minio(tmp_poster, MINIO_DEFAULT_BUCKET, poster_obj, content_type=poster_mime)
            poster_key_uri = f"minio://{MINIO_DEFAULT_BUCKET}/{poster_obj}"
            poster_public  = presigned_get(MINIO_DEFAULT_BUCKET, poster_obj, 60 * 60 * 24)

        # video → MinIO
        size_bytes = os.path.getsize(tmp_video)
        checksum   = _sha256_file(tmp_video)
        v_mime     = mimetypes.guess_type(file.filename or "")[0] or "video/mp4"
        fput_local_to_minio(tmp_video, MINIO_DEFAULT_BUCKET, video_obj, content_type=v_mime)

        # VideoAsset INSERT
        va = VideoAsset(
            id=video_id,
            title=title or (file.filename or f"{video_id}{v_ext}"),
            source_url=source_url,
            storage_key=f"minio://{MINIO_DEFAULT_BUCKET}/{video_obj}",
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            status="uploaded",
        )
        db.add(va); db.commit(); db.refresh(va)

        # 🔴 CRITICAL: poster alanlarını BURADA DB’ye yaz (ham SQL, atomik)
        _update_poster_fields(db, video_id, poster_key_uri, poster_public)

        # FE için stream URL
        stream_url = presigned_get(MINIO_DEFAULT_BUCKET, video_obj, 60 * 60)

        # AnalysisJob → ingest
        job = AnalysisJob(
            video_id=video_id,
            status="running",
            started_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(job); db.commit(); db.refresh(job)

        jsonl_out = os.path.join("/tmp", f"{job.id}.jsonl")
        _run_analyzer_sync(tmp_video, jsonl_out, job_id=str(job.id))
        inserted = _ingest_jsonl_to_db(db, str(job.id), jsonl_out)
        job.status = "done"; job.finished_at = datetime.utcnow()
        db.commit()

        return JSONResponse({
            "id": video_id,
            "title": va.title,
            "poster_url": poster_public,      # FE burada hemen görür
            "stream_url": stream_url,
            "analysis_job_id": str(job.id),
            "detections_count": inserted,
            "status": va.status,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    finally:
        try: os.remove(tmp_video)
        except: pass
        if tmp_poster:
            try: os.remove(tmp_poster)
            except: pass

# ------------------------- STREAM
@router.get("/{video_id}/stream")
def stream_original(video_id: str, db: Session = Depends(get_db)):
    v = db.get(VideoAsset, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    storage_key: str = v.storage_key or ""
    if not storage_key.startswith("minio://"):
        raise HTTPException(status_code=400, detail="Video not stored in MinIO")
    u = urlparse(storage_key)
    url = presigned_get(u.netloc, u.path.lstrip("/"), 60 * 60)
    return {"video_id": video_id, "url": url}
