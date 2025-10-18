# ai/inference/pipeline_analyze.py
from __future__ import annotations
import os, json, uuid, pathlib, argparse, math
from typing import Optional, List, Dict, Any
import requests

from dotenv import load_dotenv
from minio import Minio
from ai.inference.ffmpeg_utils import iter_frames_with_timestamps
from ai.inference.yolo_wrapper import YOLODetector

BASE_DIR   = pathlib.Path(__file__).resolve().parents[2]
MODELS_DIR = BASE_DIR / "ai" / "models"
DATA_DIR   = BASE_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
OUT_DIR    = DATA_DIR / "outputs"

# API'nin kabul ettiği etiketler
ALLOWED_LABELS = {"alcohol", "blood", "violence", "phobic", "obscene"}

def ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def download_from_minio(bucket: str, key: str, local_path: str, endpoint: str, access: str, secret: str, secure: bool):
    # MinIO client endpoint'i şemasız ister (http/https belirtme), güvenliğini secure flag belirler
    ep = (endpoint or "").replace("http://", "").replace("https://", "")
    client = Minio(ep, access_key=access, secret_key=secret, secure=secure)
    client.fget_object(bucket, key, local_path)

def build_detectors(conf: float, iou: float, imgsz: int = 640):
    mapping = {
        "alcohol":  MODELS_DIR / "alcohol_best.pt",
        "blood":    MODELS_DIR / "blood_best.pt",
        "violence": MODELS_DIR / "violence_best.pt",
        "phobic":   MODELS_DIR / "phobic_3.pt",
        "obscene":  MODELS_DIR / "nudenet_640m.pt",
    }
    conf_by_label = {
        "violence": 0.4, "blood": 0.15,
         "alcohol": 0.25,"phobic":0.1
    }
    detectors = []
    for label, path in mapping.items():
        if not path.exists():  # model yoksa sessizce atla
            continue
        this_conf = conf_by_label.get(label, conf)
        if label == "obscene":
            detectors.append(
                YOLODetector(
                    label, str(path), conf=this_conf, iou=iou, imgsz=imgsz,
                    exclude_labels={
                        "FACE_FEMALE","FACE_MALE","FEMALE_GENITALIA_COVERED","BELLY_COVERED",
                        "FEET_COVERED","ANUS_COVERED","FEMALE_BREAST_COVERED","BUTTOCKS_COVERED",
                        "ARMPITS_COVERED",
                    }
                )
            )
        else:
            detectors.append(YOLODetector(label, str(path), conf=this_conf, iou=iou, imgsz=imgsz))
        print(f"[i] loaded {label} -> {path.name} (conf={this_conf})")
    if not detectors:
        raise RuntimeError("No detectors found in ai/models")
    return detectors

def canonicalize_label(detector_label: str, sub_label: Optional[str]) -> tuple[str, str]:
    """
    Döner: (canonical_label, raw_label)
    - canonical_label: API'nin kabul ettiği 5 etiketten biri
    - raw_label: modelin ürettiği gerçek alt etiket (None olabilir) — örn. clown/spider/snake
    """
    raw = sub_label or detector_label
    canon = raw if raw in ALLOWED_LABELS else detector_label
    if canon not in ALLOWED_LABELS:
        canon = detector_label
    return canon, raw

# -------- alt-sınıf bazlı minimum skor eşiği yardımcıları --------
def parse_min_conf_map(s: Optional[str]) -> Dict[str, float]:
    """
    Biçim örn:
      "phobic=0.10,phobic/clown=0.55,phobic/spider=0.25,phobic/snake=0.20,blood=0.15"
    Anahtarlar:
      "<label>"            → tüm etiket (örn: "phobic")
      "<label>/<sublabel>" → alt etiket (örn: "phobic/clown")
    """
    out: Dict[str, float] = {}
    if not s:
        return out
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip().lower()] = float(v.strip())
    return out

def resolve_min_conf(min_map: Dict[str, float],
                     label: str,
                     raw_label: Optional[str],
                     fallback: float) -> float:
    """
    Öncelik: label/raw > label > fallback
    label ve raw küçük harfe indirgenerek aranır.
    """
    lbl = (label or "").lower()
    raw = (raw_label or "").lower() if raw_label else None
    if raw:
        key = f"{lbl}/{raw}"
        if key in min_map:
            return min_map[key]
    if lbl in min_map:
        return min_map[lbl]
    return fallback

# ---------------------------------------------------------------

def post_json(url: str, payload: Dict[str, Any], token: Optional[str] = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    r.raise_for_status()
    return r.json()

def chunked(seq: List[Dict[str, Any]], n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def run(
    minio_bucket: str, video_key: str, stride_ms: int, conf: float, iou: float,
    endpoint: str, access: str, secret: str, secure: bool,
    local_path: Optional[str] = None, source_url: Optional[str] = None,
    post_url: Optional[str] = None, job_id: Optional[str] = None, service_token: Optional[str] = None,
    out_jsonl_path: Optional[str] = None, generate_thresholds: bool = False,
    batch_size: int = 200,
    min_conf_map_str: Optional[str] = None,   # ← EKLENDİ
):
    """
    - input seçim sırası: local_path > source_url > MinIO(download)
    - eğer post_url + job_id verilmişse: start -> ingest(batch) -> finish akışı yapılır
    - out_jsonl_path verilirse JSONL de yazılır (filtrelenmiş)
    """
    ensure_dirs()
    run_id = uuid.uuid4().hex[:8]

    # 1) Girdi videosunu hazırla
    if local_path:
        input_path = local_path
        print(f"[i] Using local file: {input_path}")
    elif source_url:
        input_path = source_url
        print(f"[i] Using remote URL: {input_path}")
    else:
        local_video = VIDEOS_DIR / f"{run_id}.mp4"
        print(f"[i] Downloading s3://{minio_bucket}/{video_key} -> {local_video}")
        download_from_minio(minio_bucket, video_key, str(local_video), endpoint, access, secret, secure)
        input_path = str(local_video)

    # 2) Detektörleri yükle
    detectors = build_detectors(conf=conf, iou=iou)

    # 2.5) Alt-etiket bazlı minimum skor haritası (Arg > ENV)
    if min_conf_map_str is None:
        min_conf_map_str = os.getenv("MIN_CONF_MAP")
    min_conf_map = parse_min_conf_map(min_conf_map_str)

    # Dedektör taban fallback’ları (build_detectors ile hizalı)
    _fallback_per_label = {"violence": 0.4, "blood": 0.15, "alcohol": 0.25, "phobic": 0.10,"obscene": 0.30,}

    # 3) Opsiyonel JSONL dosyası
    if out_jsonl_path:
        out_path = pathlib.Path(out_jsonl_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = OUT_DIR / f"inference_{run_id}.jsonl"
    jsonl_fp = open(out_path, "w", encoding="utf-8")
    print(f"[i] Writing detections to: {out_path}")

    # 4) API varsa START’ı bildir
    if post_url and job_id:
        try:
            post_json(f"{post_url}/analysis/jobs/{job_id}/start", {}, service_token)
            print(f"[i] job {job_id} -> running")
        except Exception as e:
            print(f"[warn] job start bildirimi başarısız: {e}")

    n_frames = 0
    n_dets_total = 0
    buffer: List[Dict[str, Any]] = []

    try:
        for ts_ms, frame in iter_frames_with_timestamps(input_path, stride_ms=stride_ms):
            frame_events: List[Dict[str, Any]] = []

            for det in detectors:
                preds = det.infer_one(frame)
                for p in preds:
                    canon_label, raw_label = canonicalize_label(det.label, p.get("sub_label"))
                    score = float(p["score"])

                    # Alt-etiket bazlı minimum eşik (yoksa label düzeyi, yoksa fallback)
                    min_needed = resolve_min_conf(
                        min_conf_map,
                        canon_label,
                        p.get("sub_label"),
                        fallback=_fallback_per_label.get(canon_label, conf)
                    )
                    if score < min_needed:
                        continue  # bu tahmini tamamen at

                    entry = {
                        "ts_ms": ts_ms,
                        "label": canon_label,            # sadece 5 etiketten biri
                        "score": score,
                        "bbox":  p["bbox"],
                        "track_id": p.get("track_id"),
                        "extra": {"raw_label": raw_label}  # ham alt etiketi sakla
                    }
                    frame_events.append(entry)

            # JSONL’e **filtrelenmişleri** yaz
            for e in frame_events:
                jsonl_fp.write(json.dumps(e, ensure_ascii=False) + "\n")

            # API buffer’ına ekle (sadece geçerli etiketleri)
            valid_events = [e for e in frame_events if e["label"] in ALLOWED_LABELS]
            buffer.extend(valid_events)

            # batch dolduysa /ingest
            if post_url and job_id and len(buffer) >= batch_size:
                try:
                    post_json(
                        f"{post_url}/analysis/jobs/{job_id}/ingest",
                        {"detections": buffer},
                        service_token
                    )
                    buffer.clear()
                except Exception as e:
                    print(f"[warn] ingest batch gönderilemedi: {e}")

            n_frames += 1
            n_dets_total += len(frame_events)

        # kalanları bas
        if post_url and job_id and buffer:
            try:
                post_json(
                    f"{post_url}/analysis/jobs/{job_id}/ingest",
                    {"detections": buffer},
                    service_token
                )
                buffer.clear()
            except Exception as e:
                print(f"[warn] son ingest gönderilemedi: {e}")

        # FINISH
        if post_url and job_id:
            try:
                post_json(f"{post_url}/analysis/jobs/{job_id}/finish", {"status": "done"}, service_token)
            except Exception as e:
                print(f"[warn] job finish bildirimi başarısız: {e}")

        print(f"[✓] Done. frames={n_frames}, detections_kept={n_dets_total}")
        print(f"[→] Preview: tail -n 5 {out_path}")

    except Exception as e:
        # hata durumunda job’u failed yap
        if post_url and job_id:
            try:
                post_json(f"{post_url}/analysis/jobs/{job_id}/finish", {"status": "failed"}, service_token)
            except Exception as e2:
                print(f"[warn] job fail bildirimi de başarısız: {e2}")
        raise
    finally:
        if jsonl_fp:
            jsonl_fp.close()

def _get_env(name, *alts, default=None):
    for k in (name,) + alts:
        v = os.getenv(k)
        if v:
            return v
    return default

if __name__ == "__main__":
    BASE_DIR = pathlib.Path(__file__).resolve().parents[2]
    ENV_PATH = BASE_DIR / "configs" / "ai.env.sample"
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)

    ap = argparse.ArgumentParser()
    ap.add_argument("--minio-bucket", type=str, default=_get_env("S3_BUCKET", "MINIO_BUCKET"))
    ap.add_argument("--video-key", type=str, default=os.getenv("VIDEO_STORAGE_KEY"))
    ap.add_argument("--stride-ms", type=int, default=int(os.getenv("FRAME_STRIDE_MS", "200")))
    ap.add_argument("--conf", type=float, default=float(os.getenv("CONF_THRESHOLD", "0.5")))
    ap.add_argument("--iou", type=float, default=float(os.getenv("IOU_THRESHOLD", "0.5")))
    ap.add_argument("--local-path", type=str, default=None)
    ap.add_argument("--source-url", type=str, default=None)

    # yeni argümanlar (uploads.py’nin gönderdiği)
    ap.add_argument("--post-url", type=str, default=None)
    ap.add_argument("--job-id", type=str, default=None)
    ap.add_argument("--service-token", type=str, default=None)
    ap.add_argument("--out-jsonl-path", type=str, default=None)
    ap.add_argument("--generate-thresholds", action="store_true")

    # alt-sınıf eşik haritası (ENV override edilebilir)
    ap.add_argument("--min-conf-map", type=str, default=os.getenv("MIN_CONF_MAP"))

    args = ap.parse_args()

    # S3_* öncelikli, yoksa MINIO_* fallback
    ENDPOINT = _get_env("S3_ENDPOINT", "MINIO_ENDPOINT", default="minio:9000")
    ACCESS   = _get_env("S3_ACCESS_KEY", "MINIO_ACCESS_KEY")
    SECRET   = _get_env("S3_SECRET_KEY", "MINIO_SECRET_KEY")
    SECURE   = (_get_env("S3_USE_SSL", "MINIO_SECURE", default="false") or "false").lower() == "true"

    run(
        args.minio_bucket, args.video_key, args.stride_ms, args.conf, args.iou,
        ENDPOINT, ACCESS, SECRET, SECURE,
        local_path=args.local_path, source_url=args.source_url,
        post_url=args.post_url, job_id=args.job_id, service_token=args.service_token,
        out_jsonl_path=args.out_jsonl_path, generate_thresholds=args.generate_thresholds,
        min_conf_map_str=args.min_conf_map,
    )
