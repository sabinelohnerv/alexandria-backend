import boto3
from botocore.config import Config
from django.conf import settings

def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4"),
        use_ssl=settings.S3_USE_SSL,
    )

def presign_get_url(key: str, *, expires: int | None = None,
                    filename: str | None = None,
                    content_type: str | None = "application/pdf",
                    inline: bool = True) -> str:
    c = _client()
    params = {"Bucket": settings.S3_BUCKET_NAME, "Key": key}
    resp_headers = {}
    if content_type:
        resp_headers["ResponseContentType"] = content_type
    if filename:
        safe = filename.replace('"', "'")
        disp = "inline" if inline else "attachment"
        resp_headers["ResponseContentDisposition"] = f'{disp}; filename="{safe}"'
    return c.generate_presigned_url(
        "get_object",
        Params={**params, **resp_headers},
        ExpiresIn=expires or settings.MINIO_PRESIGN_EXPIRES,
    )
