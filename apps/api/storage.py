# apps/api/storage.py
from __future__ import annotations
import os
import os.path
from typing import Optional, Tuple, Union
from datetime import timedelta

import urllib3
from urllib3.util import Timeout, Retry
from minio import Minio


# ==== ENV ====
# İç ağdaki MinIO endpoint (compose içi erişim)
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")

# Dışarı servis ederken kullanılacak public host için öncelik:
# 1) MINIO_PUBLIC_ENDPOINT
# 2) PUBLIC_S3_ENDPOINT (eski değişken)
# 3) yoksa boş bırak (presign iç endpoint ile yapılır)
MINIO_PUBLIC_ENDPOINT = (
    os.getenv("MINIO_PUBLIC_ENDPOINT")
    or os.getenv("PUBLIC_S3_ENDPOINT")
    or ""
)

S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_USE_SSL    = os.getenv("S3_USE_SSL", "false").lower() == "true"
S3_REGION     = os.getenv("S3_REGION", os.getenv("MINIO_REGION", "us-east-1"))


# ==== Internal helpers ====
def _mk_http_client(read_timeout_seconds: int = 900) -> urllib3.PoolManager:
    return urllib3.PoolManager(
        timeout=Timeout(connect=5, read=read_timeout_seconds),
        retries=Retry(total=5, backoff_factor=0.5, raise_on_redirect=True, raise_on_status=False),
    )


def _strip_scheme(url: str) -> str:
    return url.replace("http://", "").replace("https://", "")


# ==== Clients ====
def build_minio() -> Minio:
    """
    İç ağdaki (compose) MinIO için client.
    """
    endpoint = _strip_scheme(S3_ENDPOINT)
    return Minio(
        endpoint,
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
        secure=S3_USE_SSL,
        http_client=_mk_http_client(),
        region=S3_REGION,
    )


def build_public_minio() -> Minio:
    """
    Public host üzerinden presign üretmek için client.
    MINIO_PUBLIC_ENDPOINT/PUBLIC_S3_ENDPOINT yoksa iç endpoint’e düşer.
    """
    if MINIO_PUBLIC_ENDPOINT:
        # Örn: http://194.146.50.83:9100  →  endpoint: 194.146.50.83:9100, secure: False
        secure = MINIO_PUBLIC_ENDPOINT.startswith("https://")
        endpoint = _strip_scheme(MINIO_PUBLIC_ENDPOINT)
        return Minio(
            endpoint,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            secure=secure,
            http_client=_mk_http_client(),
            region=S3_REGION,
        )
    # fallback: iç client
    return build_minio()


# ==== Buckets / Objects ====
def ensure_bucket(bucket: str) -> None:
    cli = build_minio()
    if not cli.bucket_exists(bucket):
        cli.make_bucket(bucket)


def put_file(bucket: str, object_name: str, file_path: str, part_mb: int = 10) -> None:
    """
    Büyük dosyalar için multipart upload (part_size=part_mb MiB).
    """
    cli = build_minio()
    if not cli.bucket_exists(bucket):
        cli.make_bucket(bucket)

    size = os.path.getsize(file_path)
    with open(file_path, "rb") as fh:
        cli.put_object(
            bucket,
            object_name,
            fh,
            length=size,
            part_size=part_mb * 1024 * 1024,
        )


# ==== Presigned URL (opsiyonel kullanım) ====
def presigned_get(
    bucket: str,
    object_name: str,
    expires: Union[int, timedelta] = 3600,
) -> str:
    """
    Public endpoint tanımlıysa presign’ı public host ile üretir (web’den direkt erişim için).
    Aksi halde iç endpoint üzerinden presign yapılır.
    """
    exp_td = timedelta(seconds=expires) if isinstance(expires, int) else expires
    cli = build_public_minio()
    return cli.presigned_get_object(bucket, object_name, expires=exp_td)