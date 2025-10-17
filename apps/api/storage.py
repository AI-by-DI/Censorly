# apps/api/storage.py
import os, os.path
import urllib3
from urllib3.util import Timeout, Retry
from minio import Minio

def build_minio():
    endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000").replace("http://","").replace("https://","")
    secure = os.getenv("S3_USE_SSL","false").lower() == "true"
    http_client = urllib3.PoolManager(
        timeout=Timeout(connect=5, read=900),   # büyük upload için geniş okuma süresi
        retries=Retry(total=5, backoff_factor=0.5, raise_on_redirect=True, raise_on_status=False),
    )
    return Minio(
        endpoint,
        access_key=os.getenv("S3_ACCESS_KEY"),
        secret_key=os.getenv("S3_SECRET_KEY"),
        secure=secure,
        http_client=http_client,
    )

def put_file(bucket: str, object_name: str, file_path: str, part_mb: int = 10):
    cli = build_minio()
    if not cli.bucket_exists(bucket):
        cli.make_bucket(bucket)
    size = os.path.getsize(file_path)
    with open(file_path, "rb") as fh:
        cli.put_object(bucket, object_name, fh, length=size, part_size=part_mb*1024*1024)