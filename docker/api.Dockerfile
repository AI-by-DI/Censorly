FROM python:3.11-slim
WORKDIR /app

# Sistem bağımlılıkları
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg libglib2.0-0 libgl1 ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# pip davranışları
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

# Önce headless + numpy'ı sabitle (ultralytics opencv-python istese bile önceden headless hazır)
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir \
      numpy==1.26.4 \
      opencv-python-headless==4.9.0.80 && \
    # Kalan bağımlılıkları yükle
    python -m pip install --no-cache-dir -r requirements.txt --upgrade && \
    # Yanlışlıkla gelen opencv-python / contrib varsa temizle
    python -m pip uninstall -y opencv-python opencv-contrib-python || true && \
    # Build-time doğrulama (fail-fast)
    python - <<'PY'
import cv2, numpy
print("Build check -> cv2:", cv2.__version__, "| numpy:", numpy.__version__)
PY

# Projeyi kopyala ve PYTHONPATH ayarla
COPY . .
ENV PYTHONPATH=/app

# Opsiyonel: başlangıçta migrate etmek için bayrak
ENV APPLY_MIGRATIONS=0 \
    APP_MODULE="apps.api.main:app" \
    PORT=8000

# Basit entrypoint
RUN printf '%s\n' \
'#!/usr/bin/env bash' \
'set -e' \
'if [ "${APPLY_MIGRATIONS:-0}" = "1" ]; then' \
'  echo "[entrypoint] Running alembic upgrade head..."' \
'  alembic upgrade head || { echo "[entrypoint] Alembic failed"; exit 1; }' \
'fi' \
'echo "[entrypoint] Starting Uvicorn: ${APP_MODULE} on port ${PORT:-8000}"' \
'exec uvicorn "${APP_MODULE}" --host 0.0.0.0 --port "${PORT:-8000}"' \
> /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]