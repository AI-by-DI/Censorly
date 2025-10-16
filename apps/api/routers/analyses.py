# apps/api/routers/analyses.py
from __future__ import annotations
import os, json, pathlib
from datetime import datetime
from enum import Enum as PyEnum
from typing import Set, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from apps.api.schemas.analysis import IngestPayload
from data.schema import SessionLocal, AnalysisJob, DetectionEvent, VideoAsset  # DB ENUM'larını import etme!

router = APIRouter(prefix="/analysis", tags=["analysis"])

# --------- ortak DB session helper ---------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --------- yollar / env ---------
APP_ROOT = os.getenv("APP_ROOT", "/app")
JOBS_JSONL_PREFIX = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs").strip("/")

def _jsonl_path(job_id: str) -> str:
    base = pathlib.Path(APP_ROOT) / JOBS_JSONL_PREFIX / str(job_id)
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "jsonl")

# --- Python tarafı doğrulama enum'u (yalnız API seviyesi için) ---
class JobStatusPy(str, PyEnum):
    queued = "queued"
    running = "running"
    done    = "done"
    failed  = "failed"

# DB tarafındaki DetectionEvent.label seti (ana kategoriler)
ALLOWED_LABELS: Set[str] = {"alcohol", "blood", "violence", "phobic", "obscene"}

# ------------------------------------------------------------------
# Job oluştur: /analysis/jobs  (video_id ver, yeni job queued düşer)
# ------------------------------------------------------------------
@router.post("/jobs")
def create_job(
    video_id: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    va = db.get(VideoAsset, video_id)
    if not va:
        raise HTTPException(404, "Video not found")

    job = AnalysisJob(
        video_id=video_id,
        status="queued",
        created_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {
        "ok": True,
        "job": {
            "job_id": str(job.id),
            "video_id": str(job.video_id),
            "status": job.status,
            "created_at": job.created_at,
        }
    }

# ------------------------------------------------------------------
# Belirli job'ı getir
# ------------------------------------------------------------------
@router.get("/jobs/{job_id}")
def job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": str(job.id),
        "video_id": str(job.video_id),
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
    }

# ------------------------------------------------------------------
# Bir video için en son (updated_at/created_at) job'ı getir
# ------------------------------------------------------------------
@router.get("/videos/{video_id}/latest")
def latest_for_video(video_id: str, db: Session = Depends(get_db)):
    q = (
        select(AnalysisJob)
        .where(AnalysisJob.video_id == video_id)
        .order_by(desc(AnalysisJob.finished_at), desc(AnalysisJob.created_at))
        .limit(1)
    )
    job = db.execute(q).scalars().first()
    if not job:
        raise HTTPException(404, "No job for this video")
    return {
        "job_id": str(job.id),
        "video_id": str(job.video_id),
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
    }

# ------------------------------------------------------------------
# Job'ı running yap
# ------------------------------------------------------------------
@router.post("/jobs/{job_id}/start")
def job_start(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "running"
    job.started_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

# ------------------------------------------------------------------
# Detection ingest (JSONL eşdeğeri kayıt)
# ------------------------------------------------------------------
@router.post("/jobs/{job_id}/ingest")
def ingest(job_id: str, body: IngestPayload, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    rows = []
    for d in body.detections:
        if d.label not in ALLOWED_LABELS:
            raise HTTPException(400, f"invalid label: {d.label}")
        rows.append(DetectionEvent(
            job_id=job_id,
            ts_ms=d.ts_ms,
            label=d.label,        # DB enum kolona string yaz
            score=d.score,
            bbox=d.bbox,
            track_id=d.track_id,
            extra=d.extra or {}
        ))
    if rows:
        db.add_all(rows)
        db.commit()
    return {"ok": True, "inserted": len(rows)}

# ------------------------------------------------------------------
# Job'ı bitir (done/failed gibi)
# ------------------------------------------------------------------
@router.post("/jobs/{job_id}/finish")
def job_finish(job_id: str, status: JobStatusPy = JobStatusPy.done, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = status.value
    job.finished_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

# ------------------------------------------------------------------
# ACİL DURUM: JSONL'i hemen dummy üret (worker'a ihtiyaç yok)
# ------------------------------------------------------------------
@router.post("/jobs/{job_id}/force_dummy")
def force_dummy(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    va = db.get(VideoAsset, str(job.video_id))
    if not va:
        raise HTTPException(404, "Video not found for job")

    jsonl_path = _jsonl_path(job_id)

    events = []
    # örnek: 1-4 sn violence, 5-7 sn alcohol
    for t in range(1000, 4000, 200):
        events.append({"ts_ms": t, "label": "violence", "score": 0.85, "bbox": [0.5,0.5,0.3,0.3], "track_id": 1})
    for t in range(5000, 7000, 250):
        events.append({"ts_ms": t, "label": "alcohol", "score": 0.8, "bbox": [0.6,0.6,0.25,0.25], "track_id": 2})

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    job.status = "done"
    job.finished_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "jsonl": jsonl_path}
