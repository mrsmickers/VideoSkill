#!/usr/bin/env python3
"""Minimal Notion client for publishing VideoSkill SOP pages.

Pure stdlib (urllib) — no venv, no SDKs. Commands:

  create <parent_id> "<title>" [--icon E]     -> prints page_id=... url=...
  append <page_id> <md_file>                  -> Markdown -> Notion blocks
  image  <page_id> <jpg_file> [--caption C]   -> file-upload + attach (Notion-hosted)
  read   <page_id>                            -> plain-text dump (verification)

API key: VIDEOSKILL_NOTION_API_KEY env var, else ~/.config/notion/api_key.

Markdown subset: #/##/### headings, - bullets, 1. numbered, - [ ]/- [x] to-dos,
> quotes, --- dividers, paragraphs; inline **bold**, *italic*, `code`, [t](url).
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import re
import sys
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

API = "https://api.notion.com/v1"
CORE_VERSION = "2022-06-28"
UPLOAD_VERSION = "2026-03-11"  # file_uploads endpoints require the newer version
MAX_BLOCKS_PER_REQUEST = 100
MAX_RICH_TEXT_CHARS = 2000

INLINE_RE = re.compile(
    r"(\*\*(?P<bold>.+?)\*\*"
    r"|(?<!\*)\*(?P<italic>[^*]+)\*(?!\*)"
    r"|`(?P<code>[^`]+)`"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)\s]+)\))"
)


def load_api_key() -> str:
    import os
    key = os.environ.get("VIDEOSKILL_NOTION_API_KEY", "").strip()
    if not key:
        path = Path.home() / ".config" / "notion" / "api_key"
        if path.exists():
            key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit(
            "No Notion API key. Set VIDEOSKILL_NOTION_API_KEY or write it to "
            "~/.config/notion/api_key"
        )
    return key


def _request(method: str, path: str, payload: dict | None = None,
             body: bytes | None = None, content_type: str | None = None,
             version: str = CORE_VERSION) -> dict:
    headers = {
        "Authorization": f"Bearer {load_api_key()}",
        "Notion-Version": version,
    }
    data = body
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type
    request = Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        detail = ""
        if hasattr(e, "read"):
            try:
                detail = " — " + e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
        raise SystemExit(f"Notion API {method} {path} failed: {e}{detail}")


# --- Markdown -> blocks ---------------------------------------------------------

def _rich_text(text: str, annotations: dict | None = None,
               link: str | None = None) -> list[dict]:
    """One or more rich_text segments (split at the 2000-char API limit)."""
    out = []
    for i in range(0, len(text), MAX_RICH_TEXT_CHARS):
        seg: dict = {"type": "text", "text": {"content": text[i:i + MAX_RICH_TEXT_CHARS]}}
        if link:
            seg["text"]["link"] = {"url": link}
        if annotations:
            seg["annotations"] = annotations
        out.append(seg)
    return out


def parse_inline(text: str) -> list[dict]:
    """Parse **bold**, *italic*, `code`, [t](url) into rich_text segments."""
    out: list[dict] = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            out.extend(_rich_text(text[pos:m.start()]))
        if m.group("bold") is not None:
            out.extend(_rich_text(m.group("bold"), {"bold": True}))
        elif m.group("italic") is not None:
            out.extend(_rich_text(m.group("italic"), {"italic": True}))
        elif m.group("code") is not None:
            out.extend(_rich_text(m.group("code"), {"code": True}))
        else:
            out.extend(_rich_text(m.group("ltext"), link=m.group("lurl")))
        pos = m.end()
    if pos < len(text):
        out.extend(_rich_text(text[pos:]))
    return out or _rich_text("")


def _block(block_type: str, text: str) -> dict:
    return {"object": "block", "type": block_type, block_type: {"rich_text": parse_inline(text)}}


def md_to_blocks(md: str) -> list[dict]:
    blocks: list[dict] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif line.startswith("### "):
            blocks.append(_block("heading_3", line[4:]))
        elif line.startswith("## "):
            blocks.append(_block("heading_2", line[3:]))
        elif line.startswith("# "):
            blocks.append(_block("heading_1", line[2:]))
        elif re.match(r"^- \[[ xX]\] ", stripped):
            checked = stripped[3].lower() == "x"
            block = _block("to_do", stripped[6:])
            block["to_do"]["checked"] = checked
            blocks.append(block)
        elif stripped.startswith(("- ", "* ")):
            blocks.append(_block("bulleted_list_item", stripped[2:]))
        elif re.match(r"^\d+\. ", stripped):
            blocks.append(_block("numbered_list_item", re.sub(r"^\d+\. ", "", stripped)))
        elif stripped.startswith("> "):
            blocks.append(_block("quote", stripped[2:]))
        else:
            blocks.append(_block("paragraph", stripped))
    return blocks


# --- commands -------------------------------------------------------------------

def cmd_create(parent_id: str, title: str, icon: str | None) -> None:
    payload: dict = {
        "parent": {"page_id": parent_id},
        "properties": {"title": {"title": _rich_text(title)}},
    }
    if icon:
        payload["icon"] = {"type": "emoji", "emoji": icon}
    page = _request("POST", "/pages", payload)
    print(f"page_id={page['id']}")
    print(f"url={page.get('url', '')}")


def append_blocks(page_id: str, blocks: list[dict]) -> None:
    for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
        _request("PATCH", f"/blocks/{page_id}/children",
                 {"children": blocks[i:i + MAX_BLOCKS_PER_REQUEST]})


def cmd_append(page_id: str, md_file: str) -> None:
    blocks = md_to_blocks(Path(md_file).read_text(encoding="utf-8"))
    append_blocks(page_id, blocks)
    print(f"appended {len(blocks)} blocks")


def _multipart(file_path: Path) -> tuple[bytes, str]:
    boundary = f"----VideoSkillSOP{uuid.uuid4().hex}"
    mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    buf = io.BytesIO()
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode()
    )
    buf.write(f"Content-Type: {mimetype}\r\n\r\n".encode())
    buf.write(file_path.read_bytes())
    buf.write(f"\r\n--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def cmd_image(page_id: str, file: str, caption: str | None) -> None:
    path = Path(file)
    if not path.exists():
        raise SystemExit(f"No such file: {path}")
    upload = _request("POST", "/file_uploads",
                      {"filename": path.name, "content_type": "image/jpeg"},
                      version=UPLOAD_VERSION)
    body, boundary = _multipart(path)
    _request("POST", f"/file_uploads/{upload['id']}/send", body=body,
             content_type=f"multipart/form-data; boundary={boundary}",
             version=UPLOAD_VERSION)
    image_block: dict = {
        "object": "block",
        "type": "image",
        "image": {"type": "file_upload", "file_upload": {"id": upload["id"]}},
    }
    if caption:
        image_block["image"]["caption"] = _rich_text(caption)
    _request("PATCH", f"/blocks/{page_id}/children", {"children": [image_block]},
             version=UPLOAD_VERSION)
    print(f"attached {path.name} (file_upload {upload['id']})")


def cmd_read(page_id: str) -> None:
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = _request("GET", path)
        for block in data.get("results", []):
            block_type = block.get("type", "?")
            content = block.get(block_type) or {}
            text = "".join(
                rt.get("plain_text") or rt.get("text", {}).get("content", "")
                for rt in content.get("rich_text", [])
            )
            print(f"{block_type}: {text}" if text else block_type)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="notion_sop.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create")
    c.add_argument("parent_id")
    c.add_argument("title")
    c.add_argument("--icon", default="📹")

    a = sub.add_parser("append")
    a.add_argument("page_id")
    a.add_argument("md_file")

    i = sub.add_parser("image")
    i.add_argument("page_id")
    i.add_argument("file")
    i.add_argument("--caption", default=None)

    r = sub.add_parser("read")
    r.add_argument("page_id")

    args = parser.parse_args(argv)
    if args.cmd == "create":
        cmd_create(args.parent_id, args.title, args.icon)
    elif args.cmd == "append":
        cmd_append(args.page_id, args.md_file)
    elif args.cmd == "image":
        cmd_image(args.page_id, args.file, args.caption)
    elif args.cmd == "read":
        cmd_read(args.page_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
