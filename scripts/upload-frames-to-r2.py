"""
Upload a slug folder's frames to a Cloudflare R2 bucket and emit a JSON map of
filename -> public URL ready for embedding in Notion (or anywhere else).

Usage:
    .venv/bin/python scripts/upload-frames-to-r2.py <slug-folder-path>

Example:
    .venv/bin/python scripts/upload-frames-to-r2.py \
        library/daniel-priestley/why-you-must-build-a-youtube-channel

Requires four env vars:
    VIDEOSKILL_R2_ACCOUNT_ID         Cloudflare account ID
    VIDEOSKILL_R2_BUCKET             R2 bucket name (e.g. "videoskill")
    VIDEOSKILL_R2_PUBLIC_DOMAIN      Public r2.dev (or custom) domain serving the bucket
                                     (e.g. "pub-XXXXXXXX.r2.dev")
    VIDEOSKILL_R2_ACCESS_KEY_ID      R2 access key ID
    VIDEOSKILL_R2_SECRET_ACCESS_KEY  R2 secret access key

R2 setup (one-off):
    1. Create a bucket in the Cloudflare dashboard.
    2. Enable the managed `r2.dev` public domain (or attach a custom domain).
    3. Create an R2 API token with read+write on that bucket; the token gives
       you the access key ID and secret access key.
"""
import json
import os
import sys
from pathlib import Path

import boto3


def main(slug_folder_arg: str) -> int:
    account_id = os.environ.get("VIDEOSKILL_R2_ACCOUNT_ID")
    bucket = os.environ.get("VIDEOSKILL_R2_BUCKET")
    public_domain = os.environ.get("VIDEOSKILL_R2_PUBLIC_DOMAIN")
    access_key = os.environ.get("VIDEOSKILL_R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("VIDEOSKILL_R2_SECRET_ACCESS_KEY")
    missing = [
        name for name, value in [
            ("VIDEOSKILL_R2_ACCOUNT_ID", account_id),
            ("VIDEOSKILL_R2_BUCKET", bucket),
            ("VIDEOSKILL_R2_PUBLIC_DOMAIN", public_domain),
            ("VIDEOSKILL_R2_ACCESS_KEY_ID", access_key),
            ("VIDEOSKILL_R2_SECRET_ACCESS_KEY", secret_key),
        ] if not value
    ]
    if missing:
        print(
            f"ERROR: missing env vars: {', '.join(missing)}. "
            f"See module docstring.",
            file=sys.stderr,
        )
        return 1

    slug_folder = Path(slug_folder_arg).resolve()
    frames_dir = slug_folder / "frames"
    if not frames_dir.is_dir():
        print(f"ERROR: no frames/ dir under {slug_folder}", file=sys.stderr)
        return 2

    # Derive the R2 key prefix from the slug folder's path under library/.
    # e.g. library/daniel-priestley/<slug>/frames/00-15-35.jpg
    #   ->  daniel-priestley/<slug>/frames/00-15-35.jpg
    parts = slug_folder.parts
    if "library" not in parts:
        print(
            f"ERROR: expected slug folder to be under a 'library/' directory: "
            f"{slug_folder}",
            file=sys.stderr,
        )
        return 3
    lib_idx = parts.index("library")
    key_prefix = "/".join(parts[lib_idx + 1 :])  # creator/slug

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    urls = {}
    for jpg in sorted(frames_dir.glob("*.jpg")):
        key = f"{key_prefix}/frames/{jpg.name}"
        s3.upload_file(
            str(jpg),
            bucket,
            key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": "public, max-age=31536000",
            },
        )
        urls[jpg.name] = f"https://{public_domain}/{key}"
        print(f"uploaded: {jpg.name}", file=sys.stderr)

    # Print the URL map as JSON to stdout so it's easy to consume.
    print(json.dumps(urls, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
