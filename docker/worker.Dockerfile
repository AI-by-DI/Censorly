FROM python:3.11-slim

# OpenCV/Ultralytics ve (gerekirse) psycopg2 için temel sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libglib2.0-0 libgl1 \
    gcc build-essential libpq-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip ayarları ve hız/kararlılık
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --prefer-binary -r requirements.txt

# Tüm repo (apps/worker dahil)
COPY . .

# Entry
CMD ["python", "apps/worker/main.py"]