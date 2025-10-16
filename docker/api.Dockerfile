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

# Python bağımlılıkları
COPY requirements.txt .
RUN python -m pip install -r requirements.txt && \
    python -m pip install alembic==1.14.0

# (Ultralytics yüzünden opencv-python gelirse sök)
RUN python - <<'PY'
import subprocess, sys
try:
    import pkg_resources
    dists = {d.project_name.lower() for d in pkg_resources.working_set}
    if 'opencv-python' in dists:
        subprocess.check_call([sys.executable, '-m', 'pip', 'uninstall', '-y', 'opencv-python'])
except Exception as e:
    print("opencv-python uninstall step warn:", e)
PY

RUN python - <<'PY'
import importlib.util, subprocess, sys
spec = importlib.util.find_spec("cv2")
if spec is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "opencv-python-headless==4.8.1.78"])
else:
    import cv2
    print("cv2 already present:", cv2.__version__)
PY

# Projeyi kopyala ve PYTHONPATH ayarla
COPY . .
ENV PYTHONPATH=/app

# Opsiyonel: başlangıçta migrate etmek için bayrak
# APPLY_MIGRATIONS=1 yaparsan entrypoint alembic upgrade head çalıştırır
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