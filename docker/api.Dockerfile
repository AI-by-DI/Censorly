FROM python:3.11-slim
WORKDIR /app

# Sistem bağımlılıkları
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg libglib2.0-0 libgl1 && \
    rm -rf /var/lib/apt/lists/*

# pip davranışları (cache kapalı, timeout biraz uzun)
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

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

# Projeyi kopyala ve PYTHONPATH ayarla
COPY . .
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]