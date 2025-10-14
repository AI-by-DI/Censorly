# apps/api/services/video_service.py
from minio import Minio
import mimetypes, uuid, os

_minio = Minio(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=os.getenv("MINIO_SECURE","false").lower()=="true",
)
BUCKET = os.getenv("MINIO_BUCKET","videos")

def put_to_minio(local_path: str, prefix: str="uploads/") -> tuple[str,str,str]:
    obj_key = f"{prefix}{uuid.uuid4().hex}/{os.path.basename(local_path)}"
    ct = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    _minio.fput_object(BUCKET, obj_key, local_path, content_type=ct)
    return BUCKET, obj_key, ct
