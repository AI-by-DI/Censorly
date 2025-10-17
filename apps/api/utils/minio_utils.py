from __future__ import annotations
import os
import tempfile
import mimetypes
from typing import Tuple, Optional, Dict, Union
from urllib.parse import urlparse, urlsplit, urlunsplit
from datetime import timedelta, datetime
from minio import Minio

# ------------------------------
# ENV & Defaults
# ------------------------------

def _pick(*keys: str, default: Optional[str] = None) -> Optional[str]:
    """İlk dolu ENV değerini döndür."""
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return default

# İç ağa yönelik MinIO endpoint’i (container içinden erişim)
# Not: Bazı ortamlarda S3_ENDPOINT "http://minio:9000" gibi gelir.
# MinIO Python client endpoint parametresi "host:port" veya "http(s)://host:port" kabul eder.
MINIO_ENDPOINT: str = _pick("MINIO_ENDPOINT", "S3_ENDPOINT", default="minio:9000")

MINIO_ACCESS_KEY: str = _pick("MINIO_ACCESS_KEY", default="minio") or "minio"
MINIO_SECRET_KEY: str = _pick("MINIO_SECRET_KEY", default="minio12345") or "minio12345"

# secure bayrağı: true → https, false → http
MINIO_SECURE: bool = (str(_pick("MINIO_SECURE", default="false")).lower() == "true")

# Public servis ederken kullanılacak host (tarayıcıların göreceği URL)
# Öncelik: PUBLIC_S3_ENDPOINT > MINIO_PUBLIC_ENDPOINT
PUBLIC_S3_ENDPOINT: str = _pick("PUBLIC_S3_ENDPOINT", "MINIO_PUBLIC_ENDPOINT", default="")

# Bölge (çoğu kurulumda us-east-1)
MINIO_REGION: str = _pick("MINIO_REGION", default="us-east-1") or "us-east-1"

# Varsayılan bucket (uygulamanın kullandığı)
DEFAULT_BUCKET: str = _pick("S3_BUCKET", "MINIO_DEFAULT_BUCKET", default="censorly-media") or "censorly-media"


# ------------------------------
# MinIO Client Helpers
# ------------------------------

def get_minio() -> Minio:
    """
    İç ağdaki MinIO'ya bağlanan client (uygulama içi kullanım).
    """
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
        region=MINIO_REGION,
    )

def _client_for(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    """
    Belirli bir endpoint için yeni client üret (presign için farklı host kullanırken işe yarar).
    endpoint: "host:port" veya "http(s)://host:port"
    """
    return Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=MINIO_REGION,
    )


# ------------------------------
# URL helpers
# ------------------------------

def is_minio_url(s: str) -> bool:
    return isinstance(s, str) and s.startswith("minio://")

def parse_minio_url(s: str) -> Tuple[str, str]:
    """
    minio://bucket/path/to/object.mp4  ->  ("bucket", "path/to/object.mp4")
    """
    u = urlparse(s)
    bucket = u.netloc
    key = u.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid MinIO URL: {s}")
    return bucket, key

def _rewrite_host(url: str, public_base: str) -> str:
    """
    Gerekirse imzalı URL'nin host kısmını farklı bir host ile değiştir.
    Bu projede imzayı zaten public endpoint ile ürettiğimiz için normalde gerekmez.
    """
    if not public_base:
        return url
    pub = urlsplit(public_base)  # "http://host:port"
    if not pub.netloc:
        return url
    u = urlsplit(url)
    scheme = pub.scheme or u.scheme
    netloc = pub.netloc or pub.path or u.netloc
    return urlunsplit((scheme, netloc, u.path, u.query, u.fragment))


# ------------------------------
# Buckets / Objects
# ------------------------------

def ensure_bucket(bucket: str) -> None:
    cli = get_minio()
    if not cli.bucket_exists(bucket):
        cli.make_bucket(bucket)

def _guess_content_type(path: str, default: str = "application/octet-stream") -> str:
    ctype, _ = mimetypes.guess_type(path)
    return ctype or default

def fput_local_to_minio(
    local_path: str,
    bucket: str,
    object_name: str,
    content_type: Optional[str] = None,
) -> None:
    """
    Yerel dosyayı MinIO'ya yükler.
    """
    cli = get_minio()
    ensure_bucket(bucket)
    ct = content_type or _guess_content_type(local_path)
    cli.fput_object(bucket, object_name, local_path, content_type=ct)

def fget_minio_to_temp(bucket: str, object_name: str, suffix: str = "") -> str:
    """
    MinIO'dan geçici bir dosyaya indirir ve geçici dosya yolunu döndürür.
    """
    cli = get_minio()
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = tmp.name
    tmp.close()
    cli.fget_object(bucket, object_name, tmp_path)
    return tmp_path


# ------------------------------
# Presigned URLs
# ------------------------------

def presigned_get(bucket: str, object_name: str, expires: Union[int, timedelta] = 3600) -> str:
    """
    GET için imzalı URL üretir.
    expires: saniye (int) ya da datetime.timedelta
    Öncelik:
      1) PUBLIC_S3_ENDPOINT (örn: http://194.146.50.83:9100 veya http://localhost:9000)
      2) İç endpoint (MINIO_ENDPOINT)
    """
    exp_td = timedelta(seconds=expires) if isinstance(expires, int) else expires

    if PUBLIC_S3_ENDPOINT:
        u = urlsplit(PUBLIC_S3_ENDPOINT)  # örn: http://host:port
        if u.scheme and u.netloc:
            cli = _client_for(
                endpoint=u.netloc if u.netloc else u.path,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=(u.scheme == "https"),
            )
            return cli.presigned_get_object(bucket, object_name, expires=exp_td)

    # public endpoint verilmemişse iç endpoint ile presign üret
    cli = get_minio()
    return cli.presigned_get_object(bucket, object_name, expires=exp_td)


# ------------------------------
# High-level helpers
# ------------------------------

def resolve_source_to_local(storage_key: str, default_suffix: str = ".mp4") -> Tuple[str, Optional[str]]:
    """
    Kaynağı yerel path'e indirip döndürür.
    - Local path ise: (path, None)
    - MinIO URL ise:  (temp_path, temp_path)  # cleanup için aynı path döner
    """
    if storage_key and os.path.exists(storage_key):
        return storage_key, None

    if is_minio_url(storage_key):
        bucket, key = parse_minio_url(storage_key)
        _, ext = os.path.splitext(key)
        tmp = tempfile.NamedTemporaryFile(suffix=ext or default_suffix, delete=False)
        tmp_path = tmp.name
        tmp.close()
        get_minio().fget_object(bucket, key, tmp_path)
        return tmp_path, tmp_path

    raise FileNotFoundError(f"Video source not accessible: {storage_key}")

def upload_redacted_and_presign(
    local_path: Optional[str],
    src_storage_key: str,
    video_id: str,
    ttl_hours: int = 3,
    existing_object: Optional[Tuple[str, str]] = None,
) -> Dict[str, str]:
    """
    İki mod:
      1) existing_object=(bucket, object) → sadece presign üret ve dön.
      2) local_path verilmiş → dosyayı uygun bucket'a yükle, sonra presign dön.

    Bucket kararı:
      - Kaynak bir MinIO URL ise, aynı bucket kullanılır.
      - Değilse DEFAULT_BUCKET (ENV: S3_BUCKET veya MINIO_DEFAULT_BUCKET).

    Nesne yolu: redacted/<video_id>/<timestamp>.mp4
    """
    cli = get_minio()

    # 1) Sadece mevcut objeyi presign et
    if existing_object:
        bucket, object_name = existing_object
        # Objektin varlığını doğrula (yoksa MinIO exception fırlatır)
        cli.stat_object(bucket, object_name)
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
        bucket = DEFAULT_BUCKET

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