import os, re
import boto3
from botocore.config import Config
import tiktoken

def s3_client():
    cfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=3,
        read_timeout=60,
    )
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=cfg,
    )

def get_pdf_bytes(storage_key: str) -> bytes:
    bucket = os.getenv("S3_BUCKET_NAME")
    cli = s3_client()
    obj = cli.get_object(Bucket=bucket, Key=storage_key)
    return obj["Body"].read()

# tokenization helpers
_ENC = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_ENC.encode(text or ""))

def sliding_windows(text: str, max_tokens=900, overlap=120):
    toks = _ENC.encode(text or "")
    i = 0
    while i < len(toks):
        window = toks[i:i + max_tokens]
        yield _ENC.decode(window)
        if i + max_tokens >= len(toks):
            break
        i += max_tokens - overlap

def normalize_spaces(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s or "")
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
