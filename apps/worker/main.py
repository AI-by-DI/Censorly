from __future__ import annotations
import os, time, json, pathlib, tempfile, subprocess, traceback
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.schema import SessionLocal, AnalysisJob, VideoAsset  # modeller
from apps.api.utils.minio_utils import (
    is_minio_url, parse_minio_url, fget_minio_to_temp
)

APP_ROOT = os.getenv("APP_ROOT", "/app")
JOBS_JSONL_PREFIX = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs").strip("/")
ANALYZE_BACKEND = os.getenv("ANALYZE_BACKEND", "dummy").lower()  # dummy | local

def jobs_jsonl_path(job_id: str) -> str:
    base = pathlib.Path(APP_ROOT) / JOBS_JSONL_PREFIX / str(job_id)
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "jsonl")

@contextmanager
def db_sess():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def resolve_to_local(storage_key: str) -> str:
    if storage_key and os.path.exists(storage_key):
        print(f"[worker] using local path: {storage_key}", flush=True)
        return storage_key
    if is_minio_url(storage_key):
        bucket, key = parse_minio_url(storage_key)
        suffix = os.path.splitext(key)[-1] or ".mp4"
        tmp = fget_minio_to_temp(bucket, key, suffix=suffix)
        print(f"[worker] downloaded from MinIO → {tmp}", flush=True)
        return tmp
    raise FileNotFoundError(f"Video not accessible: {storage_key}")

def write_dummy_jsonl(jsonl_path: str):
    evs = []
    for t in range(1000, 4000, 200):  # 1-4 sn violence
        evs.append({"ts_ms": t, "label": "violence", "score": 0.85, "bbox": [0.5,0.5,0.3,0.3], "track_id": 1})
    for t in range(5000, 7000, 250): # 5-7 sn alcohol
        evs.append({"ts_ms": t, "label": "alcohol", "score": 0.8, "bbox": [0.6,0.6,0.25,0.25], "track_id": 2})
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for e in evs:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"[worker] dummy jsonl written → {jsonl_path}", flush=True)

def run_local_analyzer(video_path: str, out_jsonl: str) -> bool:
    try:
        cmd = ["python", "-m", "ai.inference.pipeline_analyze", "--video", video_path, "--out_jsonl", out_jsonl]
        print("[worker] analyze cmd:", " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            print("[worker][analyze][stderr]\n", proc.stderr.decode(errors="ignore"), flush=True)
            return False
        ok = os.path.exists(out_jsonl)
        print(f"[worker] analyze ok={ok} jsonl={out_jsonl}", flush=True)
        return ok
    except Exception as e:
        print("[worker] analyze exception:", e, flush=True)
        traceback.print_exc()
        return False

def process_one(db: Session) -> bool:
    job = (db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.status == "queued")
        .order_by(AnalysisJob.created_at.asc())
        .limit(1)
    ).scalars().first())

    if not job:
        return False

    print(f"[worker] picked job={job.id} video={job.video_id}", flush=True)
    job.status = "running"
    job.started_at = datetime.utcnow()
    db.commit()

    va = db.get(VideoAsset, str(job.video_id))
    if not va or not va.storage_key:
        print("[worker] VideoAsset not found or storage_key empty", flush=True)
        job.status = "failed"
        db.commit()
        return True

    local_video = None
    try:
        local_video = resolve_to_local(va.storage_key)
        out_jsonl = jobs_jsonl_path(str(job.id))

        ok = False
        if ANALYZE_BACKEND == "local":
            ok = run_local_analyzer(local_video, out_jsonl)
        if ANALYZE_BACKEND == "dummy" or not ok:
            print("[worker] using dummy analyzer…", flush=True)
            write_dummy_jsonl(out_jsonl)
            ok = True

        if not ok:
            job.status = "failed"
            db.commit()
            print(f"[worker] job failed (analyze not ok) job={job.id}", flush=True)
            return True

        job.status = "done"
        job.finished_at = datetime.utcnow()
        db.commit()
        print(f"[worker] job done job={job.id}", flush=True)
        return True

    except Exception as e:
        print("[worker] process error:", e, flush=True)
        traceback.print_exc()
        job.status = "failed"
        db.commit()
        return True
    finally:
        if local_video and (not va.storage_key.startswith("/") or not os.path.samefile(local_video, va.storage_key)):
            try: os.remove(local_video)
            except: pass

def main():
    print(f"[worker] started (backend={ANALYZE_BACKEND})", flush=True)
    print(f"[worker] APP_ROOT={APP_ROOT}  JOBS_JSONL_PREFIX={JOBS_JSONL_PREFIX}", flush=True)
    while True:
        with db_sess() as db:
            did = process_one(db)
        if not did:
            time.sleep(2)

if __name__ == "__main__":
    main()
