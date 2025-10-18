# apps/api/utils/minio_utils.py
# -----------------------------------------------------------
# Backward-compatibility helper.
# Eski kodun beklediği isimleri (fput_local_to_minio, MINIO_DEFAULT_BUCKET vs.)
# yeni storage katmanına köprüler.
# -----------------------------------------------------------
from __future__ import annotations
import os
import tempfile
import mimetypes
from typing import Tuple, Optional, Dict, Union
from urllib.parse import urlparse, urlsplit, urlunsplit
from datetime import timedelta, datetime

from minio import Minio

# Yeni storage katmanından modern fonksiyonlar:
from apps.api.storage import (
    build_minio,           # iç minio client
    build_public_minio,    # public host ile presign client
    ensure_bucket,
    put_file,              # yeni isim (eski: fput_local_to_minio)
    presigned_get,
    MINIO_DEFAULT_BUCKET as _DEFAULT_BUCKET_FROM_STORAGE,
)

# Eski kodların okuduğu isim: MINIO_DEFAULT_BUCKET
MINIO_DEFAULT_BUCKET = _DEFAULT_BUCKET_FROM_STORAGE

# ---- Client (eski API'yi kullanan bazı yardımcılar için) ----
def get_minio() -> Minio:
    return build_minio()

def _client_for(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    # Bu helper artık gerekli değil; presign için build_public_minio kullanılıyor.
    # Yine de backward adına koruyalım.
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

# ---- URL helpers (eski kodlar kullanıyor) ----
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
    Presign artık public endpoint ile üretildiğinden normalde gerekmez.
    """
    if not public_base:
        return url
    pub = urlsplit(public_base)
    if not pub.netloc:
        return url
    u = urlsplit(url)
    scheme = pub.scheme or u.scheme
    netloc = pub.netloc or pub.path or u.netloc
    return urlunsplit((scheme, netloc, u.path, u.query, u.fragment))

# ---- Buckets / Objects (geri uyumlu isim) ----
def fput_local_to_minio(
    local_path: str,
    bucket: str,
    object_name: str,
    content_type: Optional[str] = None,
) -> None:
    """
    Eski isim. Yeni storage.put_file üstüne ince bir sarmalayıcı.
    """
    ensure_bucket(bucket)
    put_file(bucket=bucket, object_name=object_name, file_path=local_path, content_type=content_type)

def fget_minio_to_temp(bucket: str, object_name: str, suffix: str = "") -> str:
    cli = get_minio()
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = tmp.name
    tmp.close()
    cli.fget_object(bucket, object_name, tmp_path)
    return tmp_path

# ---- Presigned (eskisi ile aynı imza) ----
# presigned_get doğrudan storage.presigned_get'e yönlendiriliyor (yukarıda import edildi)

# ---- High-level helpers (redactions.py bunları kullanıyor) ----
def _guess_content_type(path: str, default: str = "application/octet-stream") -> str:
    ctype, _ = mimetypes.guess_type(path)
    return ctype or default

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
        cli.stat_object(bucket, object_name)  # yoksa exception atar
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
    fput_local_to_minio(local_path, bucket, object_name, content_type=ct)

    url = presigned_get(bucket, object_name, ttl_hours * 3600)

    return {
        "bucket": bucket,
        "object": object_name,
        "url": url,
        "expires_in_seconds": str(ttl_hours * 3600),
    }