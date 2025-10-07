# ai/inference/pipeline_analyze.py
from __future__ import annotations
import os, json, uuid, pathlib, subprocess
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

# --- NEW: derive_dynamic_thresholds entegrasyonu ---
def generate_thresholds(jsonl_path: pathlib.Path, out_json_path: pathlib.Path, classes: str = "blood,alcohol") -> bool:
    """
    derive_dynamic_thresholds modülünü çağırıp JSON çıktı üretir.
    """
    try:
        cmd = [
            "python", "-m", "ai.inference.derive_dynamic_thresholds",
            "--jsonl", str(jsonl_path),
            "--out",   str(out_json_path),
            "--classes", classes
        ]
        print("[thr] running:", " ".join(cmd))
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            print("[thr][stderr]\n", proc.stderr)
            print("[thr] failed with code:", proc.returncode)
            return False
        # İstersen stdout’u bilgi amaçlı yaz
        try:
            print("[thr][stdout]\n", proc.stdout[:800])  # çok uzunsa kısalt
        except Exception:
            pass
        print(f"[thr][ok] thresholds saved -> {out_json_path}")
        return True
    except Exception as e:
        print("[thr] error:", e)
        return False

# pipeline_analyze.py (ilgili kısım)
def build_detectors(conf: float, iou: float, imgsz: int = 640):
    mapping = {
        "alcohol":  MODELS_DIR / "alcohol_best.pt",
        "blood":    MODELS_DIR / "blood_best.pt",
        "violence": MODELS_DIR / "violence_best(2).pt",
        "phobic":   MODELS_DIR / "phobic_3.pt",
        "obscene":  MODELS_DIR / "nudenet_640m.pt",
    }

    conf_by_label = {
        "violence": 0.4,
        "blood": 0.15,
        "phobic": 0.03,
        "alcohol":0.25,
        # diğerleri conf (default)
    }

    detectors = []
    for label, path in mapping.items():
        if not path.exists():
            continue
        this_conf = conf_by_label.get(label, conf)
        if label == "obscene":
            detectors.append(
                YOLODetector(label, str(path), conf=this_conf, iou=iou, imgsz=imgsz,
                             exclude_labels={"FACE_FEMALE","FACE_MALE","FEMALE_GENITALIA_COVERED","BELLY_COVERED","FEET_COVERED","ANUS_COVERED","FEMALE_BREAST_COVERED","BUTTOCKS_COVERED","ARMPITS_COVERED"})
            )
        else:
            detectors.append(
                YOLODetector(label, str(path), conf=this_conf, iou=iou, imgsz=imgsz)
            )
        print(f"[i] loaded {label} -> {path.name} (conf={this_conf})")

    if not detectors:
        raise RuntimeError("No detectors found in ai/models")
    return detectors

def run(minio_bucket: str, video_key: str, stride_ms: int, conf: float, iou: float,
        endpoint: str, access: str, secret: str, secure: bool,
        generate_thr: bool = True):
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
                        "label": p.get("sub_label", det.label),
                        "score": p["score"],
                        "bbox":  p["bbox"],     # [cx,cy,w,h] normalized
                        "model": det.weights_name,
                        "extra": {}
                    }
                    frame_events.append(entry)
            for e in frame_events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            n_frames += 1
            n_dets   += len(frame_events)

    print(f"[✓] Done. frames={n_frames}, detections={n_dets}")
    print(f"[→] Preview: tail -n 5 {out_jsonl}")

    # --- NEW: analizden hemen sonra blood & alcohol için thresholds üret ---
    thresholds_json = OUT_DIR / f"thresholds_{run_id}.json"
    if generate_thr:
        ok = generate_thresholds(out_jsonl, thresholds_json, classes="blood,alcohol")
        if ok:
            # Kullanıcıya hazır redact komutu ipucu:
            print("\n[tip] PowerShell için redact örneği (backtick satır devamlama ile):")
        else:
            print("[thr][warn] thresholds üretimi başarısız oldu.")
    else:
        print("[thr][skip] GENERATE_THRESHOLDS=false — thresholds üretimi atlandı.")

    return {
        "run_id": run_id,
        "video_path": str(local_video),
        "inference_jsonl": str(out_jsonl),
        "thresholds_json": str(thresholds_json) if generate_thr else None
    }

if __name__ == "__main__":
    # configs/ai.env.sample dosyasını yükle
    ENV_PATH = BASE_DIR / "configs" / "ai.env.sample"
    load_dotenv(dotenv_path=ENV_PATH)

    # env’den al
    ENDPOINT = os.getenv("MINIO_ENDPOINT")
    ACCESS   = os.getenv("MINIO_ACCESS_KEY")
    SECRET   = os.getenv("MINIO_SECRET_KEY")
    SECURE   = os.getenv("MINIO_SECURE", "false").lower() == "true"
    BUCKET   = os.getenv("MINIO_BUCKET")
    KEY      = os.getenv("VIDEO_STORAGE_KEY")

    STRIDE_MS = int(os.getenv("FRAME_STRIDE_MS", "200"))
    CONF      = float(os.getenv("CONF_THRESHOLD", "0.5"))
    IOU       = float(os.getenv("IOU_THRESHOLD", "0.5"))

    # thresholds otomatik üretim kontrolü (default: true)
    GENERATE_THRESHOLDS = os.getenv("GENERATE_THRESHOLDS", "true").lower() == "true"

    run(BUCKET, KEY, STRIDE_MS, CONF, IOU, ENDPOINT, ACCESS, SECRET, SECURE, generate_thr=GENERATE_THRESHOLDS)
