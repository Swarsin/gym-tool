import os
import uuid
from typing import Optional, Dict
from urllib.parse import urlparse
import boto3
from botocore.config import Config

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "").strip("\"' \t\r\n")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "").strip("\"' \t\r\n")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip("\"' \t\r\n")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "workout-videos").strip("\"' \t\r\n")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").strip("\"' \t\r\n/ ")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm"}

def is_r2_configured() -> bool:
    return bool(
        R2_ACCOUNT_ID
        and R2_ACCESS_KEY_ID
        and R2_SECRET_ACCESS_KEY
        and R2_BUCKET_NAME
        and R2_PUBLIC_URL
    )

def get_r2_client():
    if not is_r2_configured():
        return None
    endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )

def generate_presigned_upload_url(
    original_filename: str,
    content_type: str = "video/mp4",
    folder: str = "uploads",
    expires_in: int = 3600
) -> Dict[str, str]:
    client = get_r2_client()
    if not client:
        raise RuntimeError("Cloudflare R2 is not configured on the server.")

    _, raw_ext = os.path.splitext(original_filename)
    ext = raw_ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".mp4"

    unique_key = f"{folder}/{uuid.uuid4().hex}{ext}"

    upload_url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": R2_BUCKET_NAME,
            "Key": unique_key,
            "ContentType": content_type or "video/mp4",
        },
        ExpiresIn=expires_in,
    )

    public_url = f"{R2_PUBLIC_URL}/{unique_key}"

    return {
        "upload_url": upload_url,
        "public_url": public_url,
        "storage_key": unique_key,
    }

def upload_file_to_r2(local_file_path: str, storage_key: str, content_type: str = "video/mp4") -> Optional[str]:
    client = get_r2_client()
    if not client or not os.path.exists(local_file_path):
        return None

    try:
        with open(local_file_path, "rb") as f:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=storage_key,
                Body=f,
                ContentType=content_type,
            )
        return f"{R2_PUBLIC_URL}/{storage_key}"
    except Exception as e:
        print(f"Error uploading file to R2: {e}")
        return None

def delete_r2_file(key_or_url: str) -> bool:
    client = get_r2_client()
    if not client or not key_or_url:
        return False

    key = key_or_url
    if key.startswith("http://") or key.startswith("https://"):
        parsed = urlparse(key)
        key = parsed.path.lstrip("/")

    try:
        client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        print(f"Successfully pruned R2 object: {key}")
        return True
    except Exception as e:
        print(f"Failed to delete R2 object {key}: {e}")
        return False
