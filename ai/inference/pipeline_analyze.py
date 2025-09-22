# ai/inference/pipeline_analyze.py
from __future__ import annotations
import os, json, uuid, pathlib
from dotenv import load_dotenv
from minio import Minio
from ai.inference.ffmpeg_utils import iter_frames_with_timestamps
from ai.inference.yolo_wrapper import YOLODetector

BASE_DIR = pathlib.Path(__file__).resolve().parents[2]  # CENSORLY/
MODELS_DIR = BASE_DIR / "ai" / "models"
DATA_DIR   = BASE_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
OUT_DIR    = DATA_DIR / "outputs"

def ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def download_from_minio(bucket: str, key: str, local_path: str, endpoint: str, access: str, secret: str, secure: bool):
    client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
    client.fget_object(bucket, key, local_path)

def build_detectors(conf: float, iou: float):
    # eldeki model dosyalarından hangisi varsa onu ekler
    mapping = {
        "alcohol":  MODELS_DIR / "alcohol_best.pt",
        "blood":    MODELS_DIR / "blood_best.pt",
        "violence": MODELS_DIR / "violence_best.pt",
        "phobic":   MODELS_DIR / "phobic_best.pt",
        # "obscene":  MODELS_DIR / "nudenet_640m.pt",  # Ayrı wrapper gerekir
    }
    detectors = []
    for label, path in mapping.items():
        if path.exists():
            detectors.append(YOLODetector(label, str(path), conf=conf, iou=iou))
    if not detectors:
        raise RuntimeError("No detectors found in ai/models. Please add weights.")
    return detectors

def run(minio_bucket: str, video_key: str, stride_ms: int, conf: float, iou: float,
        endpoint: str, access: str, secret: str, secure: bool):
    ensure_dirs()
    run_id = uuid.uuid4().hex[:8]
    local_video = VIDEOS_DIR / f"{run_id}.mp4"
    print(f"[i] Downloading s3://{minio_bucket}/{video_key} -> {local_video}")
    download_from_minio(minio_bucket, video_key, str(local_video), endpoint, access, secret, secure)

    detectors = build_detectors(conf=conf, iou=iou)
    out_jsonl = OUT_DIR / f"inference_{run_id}.jsonl"
    print(f"[i] Writing detections to: {out_jsonl}")

    n_frames = 0
    n_dets = 0
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for ts_ms, frame in iter_frames_with_timestamps(str(local_video), stride_ms=stride_ms):
            frame_events = []
            for det in detectors:
                preds = det.infer_one(frame)
                for p in preds:
                    entry = {
                        "ts_ms": ts_ms,
                        "label": det.label,
                        "score": p["score"],
                        "bbox":  p["bbox"],     # [cx,cy,w,h] normalized
                        "model": det.weights_name,
                        "extra": {}
                    }
                    frame_events.append(entry)
            # Toplu yaz
            for e in frame_events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            n_frames += 1
            n_dets   += len(frame_events)

    print(f"[✓] Done. frames={n_frames}, detections={n_dets}")
    print(f"[→] Preview: tail -n 5 {out_jsonl}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os, pathlib

    # configs/ai.env.sample dosyasını yükle
    BASE_DIR = pathlib.Path(__file__).resolve().parents[2]  # CENSORLY/
    ENV_PATH = BASE_DIR / "configs" / "ai.env.sample"
    load_dotenv(dotenv_path=ENV_PATH)

    # env’den al
    ENDPOINT = os.getenv("MINIO_ENDPOINT")
    ACCESS   = os.getenv("MINIO_ACCESS_KEY")
    SECRET   = os.getenv("MINIO_SECRET_KEY")
    SECURE   = os.getenv("MINIO_SECURE", "false").lower() == "true"
    BUCKET   = os.getenv("MINIO_BUCKET")
    KEY      = os.getenv("VIDEO_STORAGE_KEY")

    STRIDE_MS = int(os.getenv("FRAME_STRIDE_MS", "500"))
    CONF      = float(os.getenv("CONF_THRESHOLD", "0.5"))
    IOU       = float(os.getenv("IOU_THRESHOLD", "0.5"))

    run(BUCKET, KEY, STRIDE_MS, CONF, IOU, ENDPOINT, ACCESS, SECRET, SECURE)

