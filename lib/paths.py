import os
import re
from pathlib import Path

from slugify import slugify

MAX_SLUG_LEN = 80
FALLBACK_SLUG = "untitled"


def slug_for_title(title: str) -> str:
    s = slugify(title or "", max_length=MAX_SLUG_LEN, word_boundary=True, save_order=True)
    # Collapse multiple hyphens
    s = re.sub(r"-{2,}", "-", s)
    # Remove hyphens between a letter and a single letter (e.g. "p-s" -> "ps")
    s = re.sub(r"([a-z])-([a-z])(-|$)", r"\1\2\3", s)
    s = s.strip("-")
    return s or FALLBACK_SLUG


def slug_folder(library_root: Path, subfolder: str, title: str) -> Path:
    base = slug_for_title(title)
    parent = library_root / subfolder
    candidate = parent / base
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = parent / f"{base}-{n}"
        if not candidate.exists():
            return candidate
        n += 1


def library_root() -> Path:
    home = os.environ.get("VIDEOSKILL_HOME")
    if home:
        return Path(home) / "library"
    return Path(__file__).resolve().parent.parent / "library"
