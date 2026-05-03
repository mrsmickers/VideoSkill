"""
Upload a slug folder's frames to the personal Cloudflare R2 bucket 'videoskill',
returning a JSON map of filename -> public URL ready for embedding in Notion.

Usage:
    .venv/bin/python scripts/upload-frames-to-r2.py <slug-folder-path>

Example:
    .venv/bin/python scripts/upload-frames-to-r2.py \
        library/daniel-priestley/why-you-must-build-a-youtube-channel

Requirements:
    - boto3 (already in requirements.txt)
    - Two env vars: VIDEOSKILL_R2_ACCESS_KEY_ID and VIDEOSKILL_R2_SECRET_ACCESS_KEY
      (Simon: stash these in a `.env.local` file or 1Password and source them.)

Bucket setup (one-off, already done 2026-05-03):
    - Bucket: 'videoskill' on personal CF account (<MAINTAINER_DOMAIN>, ID <CF_ACCOUNT_ID_PREFIX>...)
    - Public domain: <R2_PUBLIC_DOMAIN>
    - Created via CF API; r2.dev managed-domain enabled.

Auth note: R2 access keys are derived from a CF API token named
'<R2_TOKEN_NAME>' (id <R2_ACCESS_KEY_ID>). The S3
secret_access_key is sha256(token_value). To re-derive, fetch the token value
from wherever it was stored and run sha256 over it.
"""
import json
import os
import sys
from pathlib import Path

import boto3


ACCOUNT_ID = "<CF_ACCOUNT_ID>"
BUCKET = "videoskill"
PUBLIC_DOMAIN = "<R2_PUBLIC_DOMAIN>"
S3_ENDPOINT = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"


def main(slug_folder_arg: str) -> int:
    access_key = os.environ.get("VIDEOSKILL_R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("VIDEOSKILL_R2_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        print(
            "ERROR: Set VIDEOSKILL_R2_ACCESS_KEY_ID and "
            "VIDEOSKILL_R2_SECRET_ACCESS_KEY in env first.",
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
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    urls = {}
    for jpg in sorted(frames_dir.glob("*.jpg")):
        key = f"{key_prefix}/frames/{jpg.name}"
        s3.upload_file(
            str(jpg),
            BUCKET,
            key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": "public, max-age=31536000",
            },
        )
        urls[jpg.name] = f"https://{PUBLIC_DOMAIN}/{key}"
        print(f"uploaded: {jpg.name}", file=sys.stderr)

    # Print the URL map as JSON to stdout so it's easy to consume.
    print(json.dumps(urls, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
