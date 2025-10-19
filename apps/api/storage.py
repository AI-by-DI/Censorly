from __future__ import annotations

import io
import os
from datetime import timedelta
from urllib.parse import urlparse, urlsplit, urlunsplit

from minio import Minio
import urllib3

# Varsayılan bucket (DB’de yoksa/gelmezse)
MINIO_DEFAULT_BUCKET = os.getenv("S3_BUCKET", "videos")


def _endpoint_host(ep: str) -> str:
    """
    MinIO client endpoint için host:port döndür (path kabul edilmez).
    ep: http(s)://host:port[/optional-path] → "host:port"
    """
    u = urlparse(ep)
    host = u.netloc or u.path
    # netloc'a ek path kaçmışsa ayıkla
    return host.split("/")[0]


def build_minio() -> Minio:
    ep = os.getenv("S3_ENDPOINT", "http://minio:9000")
    ak = os.getenv("S3_ACCESS_KEY", "minio")
    sk = os.getenv("S3_SECRET_KEY", "minio12345")
    region = os.getenv("S3_REGION", "us-east-1")
    secure = ep.startswith("https://")
    host = (urlparse(ep).netloc or urlparse(ep).path).split("/")[0]
    return _minio_with_timeout(host, ak, sk, secure, region)

# --- compat: build_public_minio & presigned_get ---
from datetime import timedelta
from urllib.parse import urlparse

def _endpoint_host(ep: str) -> str:
    u = urlparse(ep)
    host = u.netloc or u.path
    return host.split("/")[0]

def build_public_minio() -> "Minio":
    """
    Presign için doğrudan PUBLIC_S3_PUBLIC_BASE host'u ile MinIO client kur.
    Ağ çağrısı yapılmaz; sadece imza üretir.
    """
    import os
    from urllib.parse import urlparse
    from minio import Minio

    base = os.getenv("PUBLIC_S3_PUBLIC_BASE") or os.getenv("PUBLIC_MINIO_BASE") or ""
    if not base:
        # geri-düş: S3_ENDPOINT host'unu kullan (ama normalde base zorunlu)
        base = os.getenv("S3_ENDPOINT", "http://minio:9000")

    u = urlparse(base)
    host = u.netloc or u.path
    secure = (u.scheme == "https")
    region = os.getenv("S3_REGION", "us-east-1")

    return Minio(host, access_key=os.getenv("S3_ACCESS_KEY","minio"),
                       secret_key=os.getenv("S3_SECRET_KEY","minio12345"),
                       secure=secure, region=region)

def presigned_get(bucket: str, key: str, expires: int) -> str:
    """
    İçeriden presign üret (S3_ENDPOINT ile) ve host kısmını
    PUBLIC_S3_PUBLIC_BASE varsa ona rewrite et.
    """
    import os
    cli = build_public_minio()
    url = cli.get_presigned_url("GET", bucket, key, expires=timedelta(seconds=expires))
    public_base = os.getenv("PUBLIC_S3_PUBLIC_BASE", "")
    if public_base:
        # host rewrite
        from urllib.parse import urlsplit, urlunsplit
        u = urlsplit(url)
        pb = urlsplit(public_base)
        scheme = pb.scheme or u.scheme
        netloc = pb.netloc or pb.path or u.netloc
        url = urlunsplit((scheme, netloc, u.path, u.query, u.fragment))
    return url

# --- compat: ensure_bucket ---
def ensure_bucket(bucket: str) -> None:
    """Bucket yoksa oluştur (idempotent)."""
    cli = build_minio()  # iç endpoint: S3_ENDPOINT (minio:9000)
    try:
        cli.make_bucket(bucket)
    except Exception:
        # zaten var / yarış durumu -> sessiz geç
        pass

# --- compat: put_file (basit) ---
def put_file(
    bucket: str,
    object_name: str,
    *,
    file_path: str,
    content_type: str | None = None,
    **kwargs,
) -> None:
    """Yerel dosyayı MinIO'ya yükler."""
    import os
    ensure_bucket(bucket)
    cli = build_minio()
    size = os.path.getsize(file_path)
    with open(file_path, "rb") as f:
        cli.put_object(
            bucket,
            object_name,
            data=f,
            length=size,
            content_type=content_type or "application/octet-stream",
        )

# --- HTTP timeout'lu MinIO client helper'ı ---
def _minio_with_timeout(host: str, ak: str, sk: str, secure: bool, region: str):
    """
    Tek noktadan MinIO client kur. Kısa connect ve makul read timeout ver.
    """
    http_client = urllib3.PoolManager(
        timeout=urllib3.util.Timeout(connect=3.0, read=30.0),
        maxsize=16,
        retries=False,
    )
    return Minio(
        host,
        access_key=ak,
        secret_key=sk,
        secure=secure,
        region=region,
        http_client=http_client,
    )
