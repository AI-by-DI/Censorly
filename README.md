# Censorly — AI‑Powered Visual Content Redaction (API + Demo)
**AI by DI - İlayda Akyüz, Didar Nur Bilgin**> **TL;DR:** Censorly detects **disturbing visuals** in films/series and **redacts them live** (blur / skip) **based on user preferences**. It is **API‑first**, integrates into existing platforms, and works **without producing permanent video copies**.
---

## 🌐 Live Deployment

- **App:** https://censorly.site
---

## Table of Contents
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Models & Coverage](#models--coverage)
- [Processing Pipeline](#processing-pipeline)
- [Quick Start (Docker Compose)](#quick-start-docker-compose)
- [Environment Variables](#environment-variables)
- [Database Schema (Overview)](#database-schema-overview)
- [API — Quick Examples](#api--quick-examples)
- [Preference Profiles & Threshold Maps](#preference-profiles--threshold-maps)
- [Temporal Stabilizer](#temporal-stabilizer)
- [Performance & Metrics](#performance--metrics)
- [Security, Privacy & Ethics](#security-privacy--ethics)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Contributing & Branching](#contributing--branching)
- [License & Acknowledgements](#license--acknowledgements)

---

## Key Features

- **Personalized filtering:** Users pick which categories to filter: *alcohol, blood, violence, obscene*, and phobic sub‑classes (*spider, clown, snake*). For each, choose **how** to filter: **blur** or **skip**.
- **Live redaction:** Redaction is applied **on the fly** during playback using precomputed detections — **no permanent copies** are produced.
- **API‑first integration:** A **B2B** service that plugs into OTT platforms. The web demo shows a reference integration.
- **Dynamic thresholds:** User profiles expose **low / medium / high** intensity levels with **label‑wise min‑score maps**.
- **Scalable architecture:** FastAPI + PostgreSQL + Redis + MinIO, orchestrated via **Docker Compose**.
- **Model blend:** Multiple YOLO‑based detectors (alcohol, violence, blood, phobic) + *NudeNet* for obscene content.
- **Temporal stabilization:** Reduces flicker using **temporal IoU** and duration merging.
- **Profile persistence:** Preferences are stored per user and can be adjusted in the UI.

---

## Architecture

```
+-----------------------+        +-------------------+        +--------------------+
|      Web (React)      |<------>|       API         |<------>|   PostgreSQL (DB)  |
|  - Censor mode UI     |  REST  |   FastAPI         |  ORM   |  - users           |
|  - Preference panel   |        | - Upload/Analyze  |        |  - profiles        |
+-----------^-----------+        | - Redaction       |        |  - videos          |
            |                    +---------^---------+        |  - detections      |
            | HLS/MP4 Stream               |                  +----------^---------+
            | (live redaction)             | Jobs                       |
            v                               v                           |
+-----------------------+        +-------------------+        +----------+---------+
|  Video Worker         |        |  Redis (Cache)    |        |   MinIO (Object)  |
|  - Frame analysis     |        |  - Rate limit     |        |  - video/poster   |
|  - YOLO/NudeNet       |        |  - KV cache       |        |  - temp objects   |
+-----------------------+        +-------------------+        +--------------------+
```

**Flow:** User uploads → API stores in MinIO → Analyze job → YOLO/NudeNet detections → DB.  
When the user opts into censored playback, the API applies **blur/skip** live using the stored detections.

---

## Tech Stack

- **Backend:** FastAPI (Python), Pydantic, Uvicorn/Gunicorn
- **ML/Processing:** PyTorch / Ultralytics YOLO, OpenCV, *NudeNet* (obscene)
- **Database:** PostgreSQL (SQLAlchemy)
- **Cache/RT:** Redis
- **Object Storage:** MinIO (S3‑compatible)
- **Frontend:** React + Vite (Tailwind, shadcn/ui), HLS player
- **Orchestration:** Docker & Docker Compose
- **Observability:** JSON logs (optional Prometheus/Grafana)

> Model training was conducted on **Google Colab Pro (A100)**.

---

## Models & Coverage

- **Alcohol (YOLO, Open Images ~2.7K images):** Precision ≈ 0.82 / Recall ≈ 0.77  
- **Violence (YOLO, OIDv4: gun/knife):** Precision ≈ 0.79 / Recall ≈ 0.55  
- **Blood (YOLO, Roboflow):** Precision ≈ 0.61 / Recall ≈ 0.47  
- **Phobic (YOLO, sub‑classes: spider, clown, snake):** Precision ≈ 0.82 / Recall ≈ 0.69 / mAP50 ≈ 0.76  
- **Obscene:** *NudeNet* integration

> Goal: **mask only the disturbing region/object**, not the whole scene — preserving cinematic context.

---

## Processing Pipeline

1. **Upload:** `POST /videos/upload` → video is stored in MinIO (temporary).
2. **Analyze:** API creates a job → Worker iterates over frames and runs **YOLO/NudeNet**.
3. **Persist:** Detections are stored with **timestamp, bbox, score, label**.
4. **Temporal smooth:** Close detections are merged using **temporal IoU** + duration thresholds.
5. **Policy:** User **profile + threshold map** decide what to redact.
6. **Redaction:** Playback is produced with **blur/skip** on the fly; **no permanent file**.
7. **Delivery:** Client receives HLS/MP4 output stream/URL.

---

## Quick Start (Docker Compose)

> This project is designed to be run via **Docker Compose** (no local venv required).

```bash
# 1) Clone
git clone <repo-url> censorly
cd censorly

# 2) Prepare environment
cp .env.sample .env
# Edit .env with your secrets and service endpoints

# 3) Build & start
docker compose up -d --build

# 4) Tail logs
docker compose logs -f api web worker
```

> Data is persisted via Compose **volumes** for PostgreSQL/MinIO. Adjust mounts as needed.

---

## Environment Variables

Example `.env`:

```env
# API
API_PORT=8000
API_SECRET_KEY=**

# DB
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=***
POSTGRES_USER=**
POSTGRES_PASSWORD=***

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=**
MINIO_SECRET_KEY=**
MINIO_BUCKET=videos
MINIO_PUBLIC_ENDPOINT=http://localhost:9000

# Models
MODELS_DIR=/models

# Web (Vite)
VITE_API_BASE=http://localhost:8000
```

---

## Database Schema (Overview)

Core tables:
- `users` — accounts (hashed password, email)
- `preference_profiles` — user‑bound **redaction policies** (per label: blur/skip/none + threshold)
- `video_assets` — uploaded videos (key, title, status, duration, poster, etc.)
- `analysis_jobs` — per‑video analysis jobs (status, timing, error)
- `detection_events` — per‑frame/segment detections (label, score, bbox, ts_ms)

Enums (examples):
- `content_label_enum` = {`alcohol`, `blood`, `violence`, `phobic`, `obscene`}
- `redact_mode_enum`  = {`blur`, `skip`, `none`}
- `job_status_enum`   = {`queued`, `running`, `done`, `failed`}
- `video_status_enum` = {`uploaded`, `analyzing`, `ready`, `error`}

**Indexes:** `detection_events(video_id, ts_ms)`, `detection_events(label)` are recommended.

---

## API — Quick Examples

> Swagger/OpenAPI: `GET /docs`

### Upload a video
```bash
curl -X POST "http://localhost:8000/videos/upload?title=sample" \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/video.mp4"
```

### Start analysis
```bash
curl -X POST "http://localhost:8000/analyses/start" \
  -H "Authorization: Bearer <token)" \
  -H "Content-Type: application/json" \
  -d '{"video_id":"<uuid>"}'
```

### Get censored stream URL
```bash
curl -X GET "http://localhost:8000/redactions/stream/<video_id>?profile_id=active"
```

### Update active profile
```bash
curl -X PUT "http://localhost:8000/preferences/active" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "alcohol":  {"mode":"blur", "threshold":"medium"},
        "blood":    {"mode":"skip", "threshold":"high"},
        "violence": {"mode":"skip", "threshold":"medium"},
        "phobic":   {"mode":"blur", "sub":{"spider":{"mode":"skip"}}}
      }'
```

> Auth uses JWT access/refresh tokens.

---

## Preference Profiles & Threshold Maps

- Each profile carries **mode** (*blur/skip/none*) and **threshold** (*low/medium/high*) per label.
- Intensity levels adjust this base using a multiplier or delta.


---

## Temporal Stabilizer

**Goal:** Prevent **flickering blur** caused by frame‑to‑frame jitter.  
**Method:** Merge detections across a sliding window using **IoU ≥ τ** and enforce a **minimum duration**.

Suggested parameters:
- `iou_merge_threshold = 0.5`
- `min_duration_ms = 200` (≈5 frames @ 25 fps)
- `max_gap_ms = 120` (bridge short gaps)

---

## Performance & Metrics

**Training/detection:** Precision, Recall, F1; mAP for detection quality; **temporal IoU** for stability.  
**E2E:** Avg. analysis time, per‑stream CPU/GPU, latency (p95).  
**Quality:** User scenarios and “User Agreement Rate” (% of user‑approved decisions).

**Optimization ideas:**
- Multi‑threaded/batched frame processing
- Model size/quantization (quality/capacity trade‑off)
- Cached segment analysis for popular assets
- GPU acceleration and I/O pipelining (ffmpeg → numpy → torch zero‑copy)

> Note: In code and docs we **do not use or suggest `fl_gamma`** for training, by project policy.

---

## Security, Privacy & Ethics

- **No permanent redacted copies** — everything is applied live.
- **Personal data minimization:** only necessary profile/session info is stored.
- **Object storage lifecycle:** MinIO objects are **temporary**; add lifecycle rules.
- **Transparency:** users can view & update what is filtered and how.
- **Consent:** behavior‑based suggestions (future work) will be opt‑in by default.

---

## Known Limitations

- Low‑light / fast‑motion scenes can reduce **recall** in blood/violence.
- Overlapping objects and tiny targets make stable blur boxes harder.
- Phobic subclasses may suffer from **class imbalance**.
- Obscene detection relies on a third‑party model (NudeNet); version changes need care.

---

## Roadmap

- [ ] Expand/balance datasets and retrain
- [ ] Inference optimization (CUDA Graphs, TensorRT/ONNX)
- [ ] Profile recommendations (clustering, culture/age presets)
- [ ] Behavior‑aware suggestions (“Skip this scene?”)
- [ ] Smart TV / Mobile SDKs
- [ ] Monitoring dashboard (Prometheus/Grafana + alerts)

---

## Contributing & Branching

- We currently maintain two primary branches: **`develop`** and **`main`**.  
- **History:** Work to date has been carried out **directly on `develop` and `main`** (no feature sub‑branches).  
- **Recommended going forward:** continue committing to `develop`, then open PRs to merge into `main` on a regular cadence. Update **README** and docs with each change.

Steps:
1. Open an issue (or self‑assign).
2. Commit to `develop` with clear messages.
3. Open PR → review → merge to `main` when stable.

---

## License & Acknowledgements

- **License:** Specify your project license (e.g., MIT/Apache‑2.0).
- **Thanks:** Ultralytics YOLO, NudeNet, and dataset providers; the open‑source community.

---

## Screenshots 
![WhatsApp Image 2025-10-19 at 01 29 18](https://github.com/user-attachments/assets/c2274c99-7c34-4cd2-9bff-2c705440d76a)
![WhatsApp Image 2025-10-19 at 01 31 20](https://github.com/user-attachments/assets/5343cf99-d358-4ce8-943f-ed32651a7061)
![WhatsApp Image 2025-10-19 at 01 41 39](https://github.com/user-attachments/assets/6bf96a37-b39f-4f8b-8338-c144c835ab5f)
![WhatsApp Image 2025-10-19 at 01 45 27](https://github.com/user-attachments/assets/32befe33-d607-4ad4-b8e6-b3cc4e083a30)


---

For questions and contributions, please use **Issues**. Happy hacking! 🚀
