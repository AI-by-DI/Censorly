# apps/api/routers/analyses.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from enum import Enum as PyEnum
from typing import Set

from apps.api.schemas.analysis import IngestPayload
from data.schema import SessionLocal, AnalysisJob, DetectionEvent  # SQLAlchemy ENUM'ları import ETME

router = APIRouter(prefix="/analysis", tags=["analysis"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Python tarafında doğrulama enum'u (API için) ---
class JobStatusPy(str, PyEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"

ALLOWED_LABELS: Set[str] = {"alcohol", "blood", "violence", "phobic", "obscene"}

@router.get("/jobs/{job_id}")
def job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": str(job.id),
        "video_id": str(job.video_id),
        "status": job.status,            # DB'de enum tipine karşılık gelen string
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
    }

@router.post("/jobs/{job_id}/start")
def job_start(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "running"              # SQLAlchemy Enum kolona string yaz
    job.started_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

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
            label=d.label,               # DB enum'a string olarak yaz
            score=d.score,
            bbox=d.bbox,
            track_id=d.track_id,
            extra=d.extra or {}
        ))
    if rows:
        db.add_all(rows)
        db.commit()
    return {"ok": True, "inserted": len(rows)}

@router.post("/jobs/{job_id}/finish")
def job_finish(job_id: str, status: JobStatusPy = JobStatusPy.done, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = status.value           # Python Enum → string
    job.finished_at = datetime.utcnow()
    db.commit()
    return {"ok": True}