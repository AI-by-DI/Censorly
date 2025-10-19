import os
from urllib.parse import urlparse, urlunparse
import boto3
from botocore.client import Config

S3_ENDPOINT      = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY    = os.getenv("MINIO_ROOT_USER", "minio")
S3_SECRET_KEY    = os.getenv("MINIO_ROOT_PASSWORD", "minio12345")
S3_BUCKET        = os.getenv("S3_BUCKET", "videos")
PUBLIC_S3        = os.getenv("PUBLIC_S3_ENDPOINT", "https://censorly.site/s3")

_session = boto3.session.Session()
_s3 = _session.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

def presigned_get(key: str, expires: int = 86400) -> str:
    """
    key: bucket içi yol (ör: 'videos/posters/<uuid>.jpg' veya 'posters/<uuid>.jpg')
    """
    # Eğer key 'videos/...'(bucket adı tekrar) ile geliyorsa sadeleştir
    k = key
    if k.startswith(S3_BUCKET + "/"):
        k = k[len(S3_BUCKET)+1:]

    url = _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": k},
        ExpiresIn=expires,
    )
    # İç endpoint (minio:9000) → PUBLIC_S3 (https://censorly.site/s3)
    u = urlparse(url)
    p = urlparse(PUBLIC_S3)
    # MinIO presigned path-style: "/<bucket>/<key>"
    new_path = (p.path.rstrip("/") + "/" + S3_BUCKET + "/" + k).replace("//", "/")
    return urlunparse((p.scheme, p.netloc, new_path, "", u.query, ""))
