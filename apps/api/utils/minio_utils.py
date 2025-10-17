# minio_utils.py
# -----------------------------------------------------------
# ⚠️ UYARI: Bu dosya backward compatibility içindir.
# Tüm fonksiyonlar artık apps.api.storage üzerinden çağrılır.
# -----------------------------------------------------------

from apps.api.storage import (
    build_minio,
    build_public_minio,
    ensure_bucket,
    put_file,
    presigned_get,
)

# İleri seviye fonksiyonlar da burada yönlendiriliyor
from apps.api.storage import (
    resolve_source_to_local,
    upload_redacted_and_presign,
)

__all__ = [
    "build_minio",
    "build_public_minio",
    "ensure_bucket",
    "put_file",
    "presigned_get",
    "resolve_source_to_local",
    "upload_redacted_and_presign",
]