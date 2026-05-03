"""
Upload a slug folder's frames to Notion via the file_uploads API. Frames live
in your workspace's private file storage (not on a public URL), making this
the right choice for SOPs built from private/proprietary videos.

Usage:
    .venv/bin/python scripts/upload-frames-to-notion.py <slug-folder> [options]

Options:
    --page-id <id>          Notion page ID. If set, each uploaded frame is
                            also appended to that page as an image block.
                            If omitted, the script only uploads and prints
                            a {filename: file_upload_id} JSON map (so you
                            or Claude can attach them to specific blocks
                            via Notion's blocks API).
    --caption-prefix <str>  Optional. Prepended to each image's caption,
                            followed by the timestamp from the filename.

Example:
    # Upload + append all frames to a target page (private to your workspace):
    .venv/bin/python scripts/upload-frames-to-notion.py \
        library/daniel-priestley/why-you-must-build-a-youtube-channel \
        --page-id 3557f1850b11814dbbd9dea43002877a \
        --caption-prefix "Frame at "

    # Upload only — get back IDs to attach by hand:
    .venv/bin/python scripts/upload-frames-to-notion.py \
        library/daniel-priestley/why-you-must-build-a-youtube-channel

Requires one env var:
    VIDEOSKILL_NOTION_API_KEY  Notion internal-integration token (ntn_... or secret_...)

The integration must be added to the target page (or one of its ancestors)
via Notion's "Connections" panel — otherwise the API returns 404.

Privacy note: image blocks created this way are stored on Notion's private
S3 (prod-files-secure.s3...amazonaws.com) and are only accessible to
authenticated members of your workspace. Compare scripts/upload-frames-to-r2.py
which puts frames on a public URL.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
    }


def upload_one(token: str, jpg_path: Path) -> str:
    """Run the 2-step Notion file upload. Returns the file_upload_id."""
    create = requests.post(
        f"{NOTION_API}/file_uploads",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"filename": jpg_path.name, "content_type": "image/jpeg"},
        timeout=30,
    )
    create.raise_for_status()
    body = create.json()
    upload_id = body["id"]
    upload_url = body["upload_url"]

    with jpg_path.open("rb") as fh:
        send = requests.post(
            upload_url,
            headers=_headers(token),
            files={"file": (jpg_path.name, fh, "image/jpeg")},
            timeout=120,
        )
    send.raise_for_status()
    if send.json().get("status") != "uploaded":
        raise RuntimeError(f"upload did not finish for {jpg_path.name}: {send.json()}")
    return upload_id


def append_image_block(token: str, page_id: str, file_upload_id: str, caption: str = "") -> None:
    block: dict = {
        "object": "block",
        "type": "image",
        "image": {
            "type": "file_upload",
            "file_upload": {"id": file_upload_id},
        },
    }
    if caption:
        block["image"]["caption"] = [{"type": "text", "text": {"content": caption}}]

    resp = requests.patch(
        f"{NOTION_API}/blocks/{page_id}/children",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"children": [block]},
        timeout=30,
    )
    resp.raise_for_status()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="upload-frames-to-notion.py")
    ap.add_argument("slug_folder", help="Path to library/<creator>/<slug>/")
    ap.add_argument("--page-id", help="If set, append uploaded frames as image blocks to this Notion page.")
    ap.add_argument("--caption-prefix", default="", help="Prepend to each frame's caption.")
    args = ap.parse_args(argv)

    token = os.environ.get("VIDEOSKILL_NOTION_API_KEY")
    if not token:
        print(
            "ERROR: set VIDEOSKILL_NOTION_API_KEY (your Notion internal-integration token).",
            file=sys.stderr,
        )
        return 1

    frames_dir = Path(args.slug_folder).resolve() / "frames"
    if not frames_dir.is_dir():
        print(f"ERROR: no frames/ at {frames_dir}", file=sys.stderr)
        return 2

    jpgs = sorted(frames_dir.glob("*.jpg"))
    if not jpgs:
        print(f"ERROR: no *.jpg in {frames_dir}", file=sys.stderr)
        return 3

    upload_ids: dict[str, str] = {}
    for jpg in jpgs:
        upload_id = upload_one(token, jpg)
        upload_ids[jpg.name] = upload_id
        print(f"uploaded: {jpg.name} -> {upload_id}", file=sys.stderr)

        if args.page_id:
            caption = f"{args.caption_prefix}{jpg.stem}" if args.caption_prefix else ""
            append_image_block(token, args.page_id, upload_id, caption=caption)
            print(f"  appended to page {args.page_id}", file=sys.stderr)
            # Notion rate limit is ~3 req/sec; be polite.
            time.sleep(0.35)

    print(json.dumps(upload_ids, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
