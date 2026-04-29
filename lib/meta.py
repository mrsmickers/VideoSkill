import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def write(
    *,
    folder: Path,
    url: str,
    title: str,
    channel: str,
    duration_seconds: int,
    ingest_date: datetime,
    source_hash: str,
) -> None:
    payload = {
        "url": url,
        "title": title,
        "channel": channel,
        "duration_seconds": duration_seconds,
        "ingest_date": ingest_date.isoformat(),
        "source_hash": source_hash,
    }
    (folder / "meta.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def read(folder: Path) -> Optional[dict]:
    p = folder / "meta.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def hash_url(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"sha1:{digest}"
