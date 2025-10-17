# apps/api/storage.py
from __future__ import annotations

import os
import os.path
import mimetypes
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Tuple, Union

import urllib3
from urllib3.util import Timeout, Retry
from minio import Minio


# =========================
# ENV
# =========================
# İç ağdaki MinIO endpoint (compose içi erişim)
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")

# Public host için öncelik: MINIO_PUBLIC_ENDPOINT > PUBLIC_S3_ENDPOINT > (dev) http://localhost:9000
MINIO_PUBLIC_ENDPOINT = (
    os.getenv("MINIO_PUBLIC_ENDPOINT")
    or os.getenv("PUBLIC_S3_ENDPOINT")
    or "http://localhost:9000"
)

S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", os.getenv("MINIO_ACCESS_KEY", "minio"))
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", os.getenv("MINIO_SECRET_KEY", "minio12345"))
S3_USE_SSL    = os.getenv("S3_USE_SSL", "false").lower() == "true"
S3_REGION     = os.getenv("S3_REGION", os.getenv("MINIO_REGION", "us-east-1"))

# Varsayılan bucket (MinIO veya S3)
MINIO_DEFAULT_BUCKET = os.getenv("MINIO_DEFAULT_BUCKET", os.getenv("S3_BUCKET", "videos"))


# =========================
# Internal helpers
# =========================
def _mk_http_client(read_timeout_seconds: int = 900) -> urllib3.PoolManager:
    return urllib3.PoolManager(
        timeout=Timeout(connect=5, read=read_timeout_seconds),
        retries=Retry(total=5, backoff_factor=0.5, raise_on_redirect=True, raise_on_status=False),
    )

def _strip_scheme(url: str) -> str:
    return url.replace("http://", "").replace("https://", "")

def _guess_content_type(path: str, default: str = "application/octet-stream") -> str:
    ctype, _ = mimetypes.guess_type(path)
    return ctype or default

def is_minio_url(s: str) -> bool:
    return isinstance(s, str) and s.startswith("minio://")

def parse_minio_url(s: str) -> Tuple[str, str]:
    """
    minio://bucket/path/to/object.mp4 -> ("bucket", "path/to/object.mp4")
    """
    from urllib.parse import urlparse
    u = urlparse(s)
    bucket = u.netloc
    key = u.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid MinIO URL: {s}")
    return bucket, key


# =========================
# Clients
# =========================
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
    Public endpoint yoksa iç endpoint’e düşer.
    """
    if MINIO_PUBLIC_ENDPOINT:
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
    return build_minio()


# =========================
# Buckets / Objects
# =========================
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

def fget_minio_to_temp(bucket: str, object_name: str, suffix: str = "") -> str:
    cli = build_minio()
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = tmp.name
    tmp.close()
    cli.fget_object(bucket, object_name, tmp_path)
    return tmp_path


# =========================
# Presigned URL
# =========================
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


# =========================
# High-level helpers
# =========================
def resolve_source_to_local(storage_key: str, default_suffix: str = ".mp4") -> Tuple[str, Optional[str]]:
    """
    Kaynağı yerel path'e indirip döndürür.
    - Local path: (path, None)
    - MinIO URL : (temp_path, temp_path)  # cleanup için aynı path döner
    """
    if storage_key and os.path.exists(storage_key):
        return storage_key, None
    if is_minio_url(storage_key):
        bucket, key = parse_minio_url(storage_key)
        _, ext = os.path.splitext(key)
        tmp = tempfile.NamedTemporaryFile(suffix=ext or default_suffix, delete=False)
        tmp_path = tmp.name
        tmp.close()
        build_minio().fget_object(bucket, key, tmp_path)
        return tmp_path, tmp_path
    raise FileNotFoundError(f"Video source not accessible: {storage_key}")

def upload_redacted_and_presign(
    local_path: Optional[str],
    src_storage_key: str,
    video_id: str,
    ttl_hours: int = 3,
    existing_object: Optional[Tuple[str, str]] = None,
) -> dict:
    """
    İki mod:
      1) existing_object=(bucket, object) → sadece presign üret ve dön.
      2) local_path verilmiş → dosyayı uygun bucket'a yükle, sonra presign dön.

    Kaynak MinIO ise aynı bucket kullanılır; değilse MINIO_DEFAULT_BUCKET.
    Nesne yolu: redacted/<video_id>/<timestamp>.mp4
    """
    cli = build_minio()

    # 1) Sadece mevcut objeyi presign et
    if existing_object:
        bucket, object_name = existing_object
        cli.stat_object(bucket, object_name)  # yoksa exception
        url = presigned_get(bucket, object_name, ttl_hours * 3600)
        return {
            "bucket": bucket,
            "object": object_name,
            "url": url,
            "expires_in_seconds": str(ttl_hours * 3600),
        }

    # 2) Yeni dosyayı yükleyip presign et
    if not local_path or not os.path.exists(local_path):
        raise ValueError("local_path is required when existing_object is not provided.")

    if is_minio_url(src_storage_key):
        bucket, _ = parse_minio_url(src_storage_key)
    else:
        bucket = MINIO_DEFAULT_BUCKET

    ensure_bucket(bucket)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    _, ext = os.path.splitext(local_path)
    object_name = f"redacted/{video_id}/{ts}{ext or '.mp4'}"

    ct = _guess_content_type(local_path, "video/mp4")
    cli.fput_object(bucket, object_name, local_path, content_type=ct)

    url = presigned_get(bucket, object_name, ttl_hours * 3600)
    return {
        "bucket": bucket,
        "object": object_name,
        "url": url,
        "expires_in_seconds": str(ttl_hours * 3600),
    }