from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os, uuid, pathlib, shlex, subprocess

from data.schema import SessionLocal, VideoAsset, AnalysisJob

router = APIRouter(prefix="/uploads", tags=["uploads"])

BASE_DIR    = pathlib.Path(__file__).resolve().parents[4]
DATA_DIR    = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token-123")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-","_",".") else "_" for c in name)

@router.post("/video")
async def upload_video(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    run_id = uuid.uuid4().hex[:8]
    fname = f"{run_id}__{_safe(file.filename)}"
    local_path = UPLOADS_DIR / fname
    with open(local_path, "wb") as f:
        f.write(await file.read())

    va = VideoAsset(
        title=file.filename,
        source_url=None,
        storage_key=str(local_path),
        status="uploaded"
    )
    db.add(va)
    db.commit()
    db.refresh(va)

    job = AnalysisJob(
        video_id=va.id,
        status="queued",
        params={},
        model_versions={}
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    out_jsonl = OUTPUTS_DIR / f"inference_job{job.id}.jsonl"

    def run_pipeline():
        cmd = (
            f"python -m ai.inference.pipeline_analyze "
            f"--local-path {shlex.quote(str(local_path))} "
            f"--post-url {shlex.quote(API_BASE)} "
            f"--job-id {job.id} "
            f"--service-token {shlex.quote(SERVICE_TOKEN)} "
            f"--out-jsonl-path {shlex.quote(str(out_jsonl))} "
            f"--stride-ms 500 "
            f"--generate-thresholds"
        )
        res = subprocess.run(shlex.split(cmd), text=True, capture_output=True)
        print(f"[pipeline] CMD: {cmd}", flush=True)
        print(f"[pipeline] STDOUT:\n{res.stdout}", flush=True)
        print(f"[pipeline] STDERR:\n{res.stderr}", flush=True)

        if res.returncode != 0:
            # job'u failed işaretle
            with SessionLocal() as s:
                j = s.get(AnalysisJob, job.id)
                if j:
                    j.status = "failed"
                    s.commit()
            raise RuntimeError(f"pipeline exited {res.returncode}")
    background.add_task(run_pipeline)

    return {
        "ok": True,
        "job_id": str(job.id),
        "video_id": str(va.id),
        "jsonl_url": f"/uploads/jobs/{job.id}/jsonl",
        "status_url": f"/analysis/jobs/{job.id}"
    }

@router.get("/jobs/{job_id}/jsonl")
def get_jsonl(job_id: str):
    path = OUTPUTS_DIR / f"inference_job{job_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "JSONL not ready")
    return FileResponse(path, media_type="application/json", filename=path.name)