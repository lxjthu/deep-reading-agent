r"""Upload a release package to Aliyun OSS and print a temporary signed URL.

The script reads credentials from the standard ossutil config file by default:
  %USERPROFILE%\.ossutilconfig

Example:
  python scripts/upload_release_to_oss.py ^
    dist-repack\DeepReadingAgent-Web.zip ^
    --object releases/DeepReadingAgent-Web-2026-05-24.zip
"""

from __future__ import annotations

import argparse
import base64
import configparser
import email.utils
import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import requests


DEFAULT_BUCKET = "lxj-pdf-upload"
DEFAULT_EXPIRES_SECONDS = 24 * 3600
DEFAULT_CONFIG = Path.home() / ".ossutilconfig"


def _read_config(path: Path) -> tuple[str, str, str]:
    parser = configparser.ConfigParser()
    if not parser.read(path, encoding="utf-8"):
        raise SystemExit(f"OSS config not found: {path}")
    section = parser["Credentials"]
    endpoint = section["endpoint"].strip().rstrip("/")
    access_key_id = section["accessKeyID"].strip()
    access_key_secret = section["accessKeySecret"].strip()
    return endpoint, access_key_id, access_key_secret


def _bucket_url(endpoint: str, bucket: str, object_name: str) -> str:
    quoted_object = quote(object_name, safe="/")
    if endpoint.startswith("https://"):
        return endpoint.replace("https://", f"https://{bucket}.", 1) + "/" + quoted_object
    if endpoint.startswith("http://"):
        return endpoint.replace("http://", f"http://{bucket}.", 1) + "/" + quoted_object
    return f"https://{bucket}.{endpoint}/{quoted_object}"


def _signature(secret: str, string_to_sign: str) -> str:
    digest = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def upload(path: Path, *, bucket: str, object_name: str, config: Path, expires: int) -> str:
    endpoint, access_key_id, access_key_secret = _read_config(config)
    url = _bucket_url(endpoint, bucket, object_name)
    resource = f"/{bucket}/{object_name}"
    content_type = "application/zip"
    body = path.read_bytes()
    content_md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
    date = email.utils.formatdate(usegmt=True)

    string_to_sign = f"PUT\n{content_md5}\n{content_type}\n{date}\n{resource}"
    headers = {
        "Authorization": f"OSS {access_key_id}:{_signature(access_key_secret, string_to_sign)}",
        "Content-MD5": content_md5,
        "Content-Type": content_type,
        "Date": date,
    }

    print(f"Uploading {path} -> oss://{bucket}/{object_name} ({path.stat().st_size} bytes)")
    response = requests.put(url, data=body, headers=headers, timeout=600)
    response.raise_for_status()

    expires_at = int(time.time()) + expires
    get_string_to_sign = f"GET\n\n\n{expires_at}\n{resource}"
    query = urlencode(
        {
            "OSSAccessKeyId": access_key_id,
            "Expires": expires_at,
            "Signature": _signature(access_key_secret, get_string_to_sign),
        }
    )
    return f"{url}?{query}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--object", required=True, help="OSS object name, e.g. releases/app.zip")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--expires", type=int, default=DEFAULT_EXPIRES_SECONDS)
    args = parser.parse_args()

    signed_url = upload(
        args.zip_path,
        bucket=args.bucket,
        object_name=args.object,
        config=args.config,
        expires=args.expires,
    )
    print("Signed URL:")
    print(signed_url)


if __name__ == "__main__":
    main()
