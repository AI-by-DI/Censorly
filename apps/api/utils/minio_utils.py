from __future__ import annotations
import os
import tempfile
import mimetypes
from typing import Tuple, Optional, Dict, Union
from urllib.parse import urlparse, urlsplit, urlunsplit
from datetime import timedelta, datetime
from minio import Minio

# ---- ENV ----
MINIO_ENDPOINT         = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY       = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY       = os.getenv("MINIO_SECRET_KEY", "minio12345")
MINIO_SECURE           = str(os.getenv("MINIO_SECURE", "false")).lower() == "true"
MINIO_DEFAULT_BUCKET   = os.getenv("MINIO_DEFAULT_BUCKET", "videos")
# Dışarı servis ederken kullanılacak public host (örn: http://localhost:9000)
MINIO_PUBLIC_ENDPOINT  = os.getenv("MINIO_PUBLIC_ENDPOINT", "http://localhost:9000")
MINIO_REGION           = os.getenv("MINIO_REGION", "us-east-1")

# ---- Client ----
def get_minio() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
        region=MINIO_REGION,
    )

def _client_for(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    return Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=MINIO_REGION,
    )

# ---- URL helpers ----
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
    İmzalanmış URL'yi farklı bir host ile yeniden yazmak istersen kullan.
    Bu projede presign'ı zaten public endpoint ile ürettiğimiz için gerek kalmıyor.
    """
    if not public_base:
        return url
    pub = urlsplit(public_base)
    if not pub.netloc:  # "http://host:port" beklenir
        return url
    u = urlsplit(url)
    scheme = pub.scheme or u.scheme
    netloc = pub.netloc or pub.path or u.netloc
    return urlunsplit((scheme, netloc, u.path, u.query, u.fragment))

# ---- Buckets / Objects ----
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
    cli = get_minio()
    ensure_bucket(bucket)
    ct = content_type or _guess_content_type(local_path)
    cli.fput_object(bucket, object_name, local_path, content_type=ct)

def fget_minio_to_temp(bucket: str, object_name: str, suffix: str = "") -> str:
    cli = get_minio()
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = tmp.name
    tmp.close()
    cli.fget_object(bucket, object_name, tmp_path)
    return tmp_path

# ---- Presigned ----
def presigned_get(bucket: str, object_name: str, expires: Union[int, timedelta] = 3600) -> str:
    """
    expires: saniye (int) ya da datetime.timedelta
    Public endpoint verilmişse, presign'ı o host ile üret.
    """
    exp_td = timedelta(seconds=expires) if isinstance(expires, int) else expires

    if MINIO_PUBLIC_ENDPOINT:
        u = urlsplit(MINIO_PUBLIC_ENDPOINT)  # örn: http://localhost:9000
        if u.scheme and u.netloc:
            cli = _client_for(
                endpoint=u.netloc,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=(u.scheme == "https"),
            )
        else:
            cli = get_minio()
        return cli.presigned_get_object(bucket, object_name, expires=exp_td)

    # public endpoint yoksa iç endpointten üret
    cli = get_minio()
    return cli.presigned_get_object(bucket, object_name, expires=exp_td)

# ---- High-level helpers ----
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

    Kaynak MinIO ise aynı bucket kullanılır; değilse MINIO_DEFAULT_BUCKET.
    Nesne yolu: redacted/<video_id>/<timestamp>.mp4
    """
    cli = get_minio()

    # 1) Sadece mevcut objeyi presign et
    if existing_object:
        bucket, object_name = existing_object
        # object gerçekten var mı kontrol et (yoksa MinIO exception atar)
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
