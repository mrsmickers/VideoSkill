# VideoSkill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For Simon:** Per your CLAUDE.md, the executor MUST pause at every `git commit` step and ask before committing. Do not auto-commit.

**Goal:** Build a personal YouTube-expert library at `~/Projects/VideoSkill/` with mechanical Python helpers (download / transcribe / extract frames) and a Claude-driven cognitive layer (summarise / extract methodology / pick frame timestamps), so a fresh Claude Code chat in the project folder can answer questions across the library.

**Architecture:** Two-phase ingestion. `ingest.py prepare <url> --to <subfolder>` does mechanical work up to a transcript. The calling Claude session then reads the transcript and writes `summary.md` + `extracted.md`, picking frame timestamps. `ingest.py finalize <slug-folder> --frames "..."` extracts frames, writes `meta.json`, regenerates the top-level `CLAUDE.md` index, and deletes the temp video/audio files. The library lives at `library/<creator-or-topic>/<slug>/`.

**Tech Stack:**
- Python 3 (Homebrew)
- `yt-dlp` (Homebrew, invoked via subprocess)
- `ffmpeg` (Homebrew, invoked via subprocess)
- `groq` Python SDK (Whisper-large-v3 transcription)
- `python-slugify` (filename safety)
- `pytest` for tests
- `bws` (Bitwarden Secrets Manager CLI) for the Groq API key
- Local git for code; `library/` is gitignored (copyright-sensitive)

---

## Task 1: Project scaffolding

**Files:**
- Create: `~/Projects/VideoSkill/.gitignore`
- Create: `~/Projects/VideoSkill/requirements.txt`
- Create: `~/Projects/VideoSkill/README.md`
- Create: `~/Projects/VideoSkill/lib/__init__.py`
- Create: `~/Projects/VideoSkill/tests/__init__.py`
- Create: `~/Projects/VideoSkill/library/.gitkeep`
- Create: `~/Projects/VideoSkill/.logs/.gitkeep`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p ~/Projects/VideoSkill/{lib,tests,tests/fixtures,library,.logs}
touch ~/Projects/VideoSkill/library/.gitkeep ~/Projects/VideoSkill/.logs/.gitkeep
touch ~/Projects/VideoSkill/lib/__init__.py ~/Projects/VideoSkill/tests/__init__.py
ls -la ~/Projects/VideoSkill/
```

Expected: `lib`, `tests`, `library`, `.logs`, `docs` directories visible.

- [ ] **Step 2: Write `.gitignore`**

Create `~/Projects/VideoSkill/.gitignore` with:

```gitignore
# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/

# Project-specific
library/
!library/.gitkeep
.logs/
!.logs/.gitkeep

# Temp files inside slug folders (in case library/ is ever ungitignored)
**/.source.*
**/.audio.*
**/.work-state.json

# OS
.DS_Store
```

- [ ] **Step 3: Write `requirements.txt`**

Create `~/Projects/VideoSkill/requirements.txt` with:

```
groq>=0.11.0
python-slugify>=8.0.4
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 4: Create venv and install dependencies**

```bash
cd ~/Projects/VideoSkill && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt
```

Expected output ends with `Successfully installed groq-... python-slugify-... pytest-... pytest-mock-...`.

- [ ] **Step 5: Verify the venv**

```bash
~/Projects/VideoSkill/.venv/bin/python -c "import groq, slugify, pytest; print('groq:', groq.__version__); print('slugify ok'); print('pytest:', pytest.__version__)"
```

Expected: three lines printed, no errors.

- [ ] **Step 6: Write `README.md`**

Create `~/Projects/VideoSkill/README.md` with the content below. (Quadruple-backtick fence used here so the inner triple-backtick `bash` block survives.)

````markdown
# VideoSkill

Personal library of expert YouTube content, ingested into searchable folders.

See `docs/superpowers/specs/2026-04-29-videoskill-design.md` for the design.

## Quick start

```bash
# 1. Load secrets
source ./load-secrets.sh

# 2. Activate venv
source .venv/bin/activate

# 3. Open Claude Code in this folder, then ask it to ingest URLs
claude
```

## Layout

- `ingest.py` — two-phase CLI (`prepare`, `finalize`)
- `lib/` — Python helpers (download, transcribe, frames, meta, index)
- `library/<creator-or-topic>/<slug>/` — ingested content (gitignored)
- `CLAUDE.md` — auto-generated library index, loaded by Claude Code on chat open
````

- [ ] **Step 7: Initialise git, stage, do NOT commit yet**

```bash
cd ~/Projects/VideoSkill && git init -b main && git add -A && git status --short
```

Expected: list of tracked files (`.gitignore`, `requirements.txt`, `README.md`, `docs/...`, etc.) with `A ` prefix. **Stop here. Do not commit.** Ask Simon before running `git commit`.

- [ ] **Step 8: Pause for Simon's commit approval**

Ask: *"Initial scaffold staged. Run `git commit -m 'chore: project scaffold'` now?"*

If yes, run:

```bash
cd ~/Projects/VideoSkill && git commit -m "chore: project scaffold

- Create lib/, tests/, library/, .logs/ directories
- requirements.txt: groq, python-slugify, pytest, pytest-mock
- .gitignore for venv, library/, .logs/, OS files
- Initial README"
```

If Simon defers: leave staged, move to next task. (Same applies to every subsequent commit step.)

---

## Task 2: bws wrapper script

**Files:**
- Create: `~/Projects/VideoSkill/load-secrets.sh`

- [ ] **Step 1: Verify `bws` CLI installed**

```bash
which bws && bws --version
```

If `which` returns nothing, stop and tell Simon: *"`bws` CLI not on PATH. Install with `brew install bitwarden-secrets-manager` then re-run setup with the access token configured."*

- [ ] **Step 2: Verify `Grok_API_Key` exists in bws**

```bash
bws secret list --output json | jq -r '.[] | select(.key=="Grok_API_Key") | .key + " (id=" + .id + ")"'
```

Expected: one line like `Grok_API_Key (id=<uuid>)`.

If empty: stop and ask Simon: *"No bws secret named `Grok_API_Key` found. Could you check the secret name? You can list all secrets with `bws secret list`."*

- [ ] **Step 3: Write `load-secrets.sh`**

Create `~/Projects/VideoSkill/load-secrets.sh` with:

```bash
#!/usr/bin/env bash
# Source this script (don't execute it) to populate the env with secrets fetched from bws.
# Usage:  source ./load-secrets.sh

set -euo pipefail

if ! command -v bws >/dev/null 2>&1; then
  echo "ERROR: bws CLI not on PATH. brew install bitwarden-secrets-manager" >&2
  return 1 2>/dev/null || exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq not on PATH. brew install jq" >&2
  return 1 2>/dev/null || exit 1
fi

# Note: bws stores the Groq key under the (mis)spelled name 'Grok_API_Key'. Preserved as-is.
_groq_value=$(bws secret list --output json | jq -r '.[] | select(.key=="Grok_API_Key") | .value' | head -n 1)

if [ -z "${_groq_value:-}" ]; then
  echo "ERROR: secret 'Grok_API_Key' not found in bws" >&2
  unset _groq_value
  return 1 2>/dev/null || exit 1
fi

export GROQ_API_KEY="$_groq_value"
unset _groq_value

echo "GROQ_API_KEY loaded from bws (Grok_API_Key)."
```

- [ ] **Step 4: Make executable**

```bash
chmod +x ~/Projects/VideoSkill/load-secrets.sh
```

- [ ] **Step 5: Test in a fresh subshell**

```bash
( cd ~/Projects/VideoSkill && source ./load-secrets.sh && [ -n "${GROQ_API_KEY:-}" ] && echo "OK: key length=${#GROQ_API_KEY}" )
```

Expected: `GROQ_API_KEY loaded from bws (Grok_API_Key).` followed by `OK: key length=N` where N is plausibly between 30 and 100.

If it errors about jq, install: `brew install jq` and retry.

- [ ] **Step 6: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add load-secrets.sh && git status --short
```

Ask: *"`load-secrets.sh` ready. Commit?"*

If yes:

```bash
git commit -m "feat: bws wrapper for GROQ_API_KEY"
```

---

## Task 3: lib/paths.py — slug & folder logic (TDD)

**Files:**
- Create: `~/Projects/VideoSkill/lib/paths.py`
- Create: `~/Projects/VideoSkill/tests/test_paths.py`

- [ ] **Step 1: Write failing tests for `slug_for_title`**

Create `~/Projects/VideoSkill/tests/test_paths.py` with:

```python
from pathlib import Path

import pytest

from lib import paths


class TestSlugForTitle:
    def test_basic_lowercase_hyphenated(self):
        assert paths.slug_for_title("Key Person of Influence") == "key-person-of-influence"

    def test_strips_special_characters(self):
        assert paths.slug_for_title("KPOI: The 5 P's!") == "kpoi-the-5-ps"

    def test_collapses_whitespace(self):
        assert paths.slug_for_title("  Many   Spaces  ") == "many-spaces"

    def test_truncates_long_titles(self):
        long = "a " * 200
        result = paths.slug_for_title(long)
        assert len(result) <= 80
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_falls_back(self):
        assert paths.slug_for_title("") == "untitled"

    def test_only_punctuation_falls_back(self):
        assert paths.slug_for_title("!!!") == "untitled"


class TestSlugFolder:
    def test_builds_under_library(self, tmp_path):
        result = paths.slug_folder(library_root=tmp_path, subfolder="daniel-priestly", title="KPOI Talk")
        assert result == tmp_path / "daniel-priestly" / "kpoi-talk"

    def test_uniquifies_existing_slug(self, tmp_path):
        existing = tmp_path / "daniel-priestly" / "kpoi-talk"
        existing.mkdir(parents=True)
        result = paths.slug_folder(library_root=tmp_path, subfolder="daniel-priestly", title="KPOI Talk")
        assert result == tmp_path / "daniel-priestly" / "kpoi-talk-2"

    def test_uniquifies_repeatedly(self, tmp_path):
        (tmp_path / "x" / "talk").mkdir(parents=True)
        (tmp_path / "x" / "talk-2").mkdir(parents=True)
        result = paths.slug_folder(library_root=tmp_path, subfolder="x", title="Talk")
        assert result == tmp_path / "x" / "talk-3"


class TestLibraryRoot:
    def test_returns_library_dir_under_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VIDEOSKILL_HOME", str(tmp_path))
        assert paths.library_root() == tmp_path / "library"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_paths.py -v
```

Expected: import error or collection error because `lib.paths` doesn't exist yet, or all tests fail with `AttributeError`.

- [ ] **Step 3: Implement `lib/paths.py`**

Create `~/Projects/VideoSkill/lib/paths.py` with:

```python
import os
import re
from pathlib import Path

from slugify import slugify

MAX_SLUG_LEN = 80
FALLBACK_SLUG = "untitled"


def slug_for_title(title: str) -> str:
    s = slugify(title or "", max_length=MAX_SLUG_LEN, word_boundary=True, save_order=True)
    s = re.sub(r"-{2,}", "-", s).strip("-")
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_paths.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 5: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add lib/paths.py tests/test_paths.py && git status --short
```

Ask: *"paths module + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(lib): paths module — slug & folder logic"
```

---

## Task 4: lib/meta.py — meta.json read/write (TDD)

**Files:**
- Create: `~/Projects/VideoSkill/lib/meta.py`
- Create: `~/Projects/VideoSkill/tests/test_meta.py`

- [ ] **Step 1: Write failing tests**

Create `~/Projects/VideoSkill/tests/test_meta.py` with:

```python
import json
from datetime import datetime, timezone

import pytest

from lib import meta


def test_write_meta_creates_file_with_required_fields(tmp_path):
    folder = tmp_path / "slug"
    folder.mkdir()

    meta.write(
        folder=folder,
        url="https://youtu.be/abc123",
        title="Key Person of Influence",
        channel="Daniel Priestly",
        duration_seconds=1834,
        ingest_date=datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
        source_hash="sha1:deadbeef",
    )

    out = json.loads((folder / "meta.json").read_text())
    assert out == {
        "url": "https://youtu.be/abc123",
        "title": "Key Person of Influence",
        "channel": "Daniel Priestly",
        "duration_seconds": 1834,
        "ingest_date": "2026-04-29T12:00:00+00:00",
        "source_hash": "sha1:deadbeef",
    }


def test_read_returns_parsed_dict(tmp_path):
    folder = tmp_path / "slug"
    folder.mkdir()
    (folder / "meta.json").write_text(json.dumps({"url": "u", "title": "t"}))
    assert meta.read(folder) == {"url": "u", "title": "t"}


def test_read_returns_none_when_missing(tmp_path):
    assert meta.read(tmp_path / "nope") is None


def test_hash_url_is_deterministic_and_short():
    h1 = meta.hash_url("https://youtu.be/abc123")
    h2 = meta.hash_url("https://youtu.be/abc123")
    h3 = meta.hash_url("https://youtu.be/different")
    assert h1 == h2
    assert h1 != h3
    assert h1.startswith("sha1:")
    assert len(h1) == len("sha1:") + 12  # 12 hex chars for compactness
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_meta.py -v
```

Expected: import error (`lib.meta` does not exist).

- [ ] **Step 3: Implement `lib/meta.py`**

Create `~/Projects/VideoSkill/lib/meta.py` with:

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_meta.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add lib/meta.py tests/test_meta.py && git status --short
```

Ask: *"meta module + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(lib): meta.json read/write helpers"
```

---

## Task 5: lib/download.py — yt-dlp wrapper

**Files:**
- Create: `~/Projects/VideoSkill/lib/download.py`
- Create: `~/Projects/VideoSkill/tests/test_download.py`
- Create: `~/Projects/VideoSkill/tests/fixtures/yt_dlp_info.json`

**Note on testing:** `download.py` shells out to `yt-dlp`. Tests mock `subprocess.run` and check the command construction; output parsing uses a fixture JSON modelled on real yt-dlp `--write-info-json` output.

- [ ] **Step 1: Create yt-dlp info fixture**

Create `~/Projects/VideoSkill/tests/fixtures/yt_dlp_info.json` with:

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Key Person of Influence — Daniel Priestly",
  "uploader": "Daniel Priestly",
  "channel": "Daniel Priestly",
  "duration": 1834,
  "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "ext": "mp4"
}
```

- [ ] **Step 2: Write failing tests**

Create `~/Projects/VideoSkill/tests/test_download.py` with:

```python
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib import download

FIXTURE = Path(__file__).parent / "fixtures" / "yt_dlp_info.json"


def test_download_invokes_yt_dlp_with_expected_args(tmp_path, mocker):
    fake_info = json.loads(FIXTURE.read_text())
    info_path = tmp_path / "video.info.json"
    info_path.write_text(json.dumps(fake_info))
    video_path = tmp_path / "video.mp4"
    video_path.touch()

    def fake_run(cmd, *args, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    run_mock = mocker.patch("lib.download.subprocess.run", side_effect=fake_run)

    result = download.download_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        out_dir=tmp_path,
        out_basename="video",
    )

    cmd = run_mock.call_args.args[0]
    assert cmd[0] == "yt-dlp"
    assert "--no-playlist" in cmd
    assert "--write-info-json" in cmd
    assert "--merge-output-format" in cmd and "mp4" in cmd
    assert "https://youtu.be/dQw4w9WgXcQ" in cmd

    assert result["video_path"] == video_path
    assert result["info"]["title"] == "Key Person of Influence — Daniel Priestly"
    assert result["info"]["channel"] == "Daniel Priestly"
    assert result["info"]["duration"] == 1834


def test_download_raises_on_yt_dlp_failure(tmp_path, mocker):
    mocker.patch(
        "lib.download.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "yt-dlp", stderr="ERROR: video unavailable"),
    )
    with pytest.raises(download.DownloadError, match="video unavailable"):
        download.download_video(url="https://x", out_dir=tmp_path, out_basename="v")
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_download.py -v
```

Expected: import error (`lib.download` does not exist).

- [ ] **Step 4: Implement `lib/download.py`**

Create `~/Projects/VideoSkill/lib/download.py` with:

```python
import json
import subprocess
from pathlib import Path
from typing import TypedDict


class DownloadError(RuntimeError):
    pass


class DownloadResult(TypedDict):
    video_path: Path
    info_path: Path
    info: dict


def download_video(*, url: str, out_dir: Path, out_basename: str) -> DownloadResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / f"{out_basename}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--write-info-json",
        "--merge-output-format", "mp4",
        "--restrict-filenames",
        "-o", out_template,
        url,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise DownloadError(f"yt-dlp failed: {e.stderr or e.stdout}") from e

    video_path = out_dir / f"{out_basename}.mp4"
    info_path = out_dir / f"{out_basename}.info.json"

    if not info_path.exists():
        raise DownloadError(f"yt-dlp did not produce info JSON at {info_path}")
    if not video_path.exists():
        # yt-dlp may produce other extensions if merging fails; surface the situation.
        candidates = list(out_dir.glob(f"{out_basename}.*"))
        raise DownloadError(f"expected {video_path}, got {[c.name for c in candidates]}")

    info = json.loads(info_path.read_text())
    return {"video_path": video_path, "info_path": info_path, "info": info}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_download.py -v
```

Expected: 2 tests pass.

- [ ] **Step 6: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add lib/download.py tests/test_download.py tests/fixtures/yt_dlp_info.json && git status --short
```

Ask: *"download module + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(lib): yt-dlp download wrapper"
```

---

## Task 6: lib/transcribe.py — Groq whisper wrapper

**Files:**
- Create: `~/Projects/VideoSkill/lib/transcribe.py`
- Create: `~/Projects/VideoSkill/tests/test_transcribe.py`

**Note on audio compression:** Groq has a 25 MB upload limit for whisper. To stay well under that for 1–2 hour videos, audio is compressed to **24 kbps mono mp3** before upload (≈ 11 MB/hour). Anything longer than ~3 hours would need chunking — flagged in the spec's deferred decisions.

- [ ] **Step 1: Write failing tests**

Create `~/Projects/VideoSkill/tests/test_transcribe.py` with:

```python
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lib import transcribe


def test_extract_audio_invokes_ffmpeg_with_expected_args(tmp_path, mocker):
    video = tmp_path / "v.mp4"
    video.touch()
    audio = tmp_path / ".audio.mp3"

    run_mock = mocker.patch("lib.transcribe.subprocess.run", return_value=MagicMock(returncode=0))

    transcribe.extract_audio(video_path=video, audio_path=audio)

    cmd = run_mock.call_args.args[0]
    assert cmd[:2] == ["ffmpeg", "-y"]
    assert "-i" in cmd and str(video) in cmd
    assert "-vn" in cmd  # no video
    assert "-ac" in cmd and "1" in cmd  # mono
    assert "-ar" in cmd and "16000" in cmd  # 16 kHz
    assert "-c:a" in cmd and "libmp3lame" in cmd
    assert "-b:a" in cmd and "24k" in cmd
    assert str(audio) in cmd


def test_format_transcript_emits_timestamped_markdown():
    segments = [
        SimpleNamespace(start=0.0, end=3.5, text="Hello and welcome."),
        SimpleNamespace(start=3.5, end=10.2, text="Today we'll talk about KPOI."),
        SimpleNamespace(start=70.0, end=75.0, text="Step one."),
    ]
    md = transcribe.format_transcript(segments)
    assert "[00:00]" in md
    assert "[00:03] Today we'll talk about KPOI." in md
    assert "[01:10] Step one." in md


def test_transcribe_audio_uses_groq_client(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake-audio-bytes")

    fake_response = SimpleNamespace(
        segments=[
            SimpleNamespace(start=0.0, end=1.0, text="Hi."),
        ]
    )
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_response
    mocker.patch("lib.transcribe.Groq", return_value=fake_client)

    segments = transcribe.transcribe_audio(audio_path=audio)

    args = fake_client.audio.transcriptions.create.call_args
    assert args.kwargs["model"] == "whisper-large-v3"
    assert args.kwargs["response_format"] == "verbose_json"
    assert args.kwargs["timestamp_granularities"] == ["segment"]
    assert segments == fake_response.segments
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_transcribe.py -v
```

Expected: import error.

- [ ] **Step 3: Implement `lib/transcribe.py`**

Create `~/Projects/VideoSkill/lib/transcribe.py` with:

```python
import subprocess
from pathlib import Path
from typing import Iterable

from groq import Groq


class TranscribeError(RuntimeError):
    pass


def extract_audio(*, video_path: Path, audio_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "libmp3lame",
        "-b:a", "24k",
        str(audio_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise TranscribeError(f"ffmpeg audio extract failed: {e.stderr or e.stdout}") from e


def transcribe_audio(*, audio_path: Path) -> list:
    client = Groq()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            file=(audio_path.name, f.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    return list(response.segments)


def format_transcript(segments: Iterable) -> str:
    lines = []
    for seg in segments:
        start = int(seg.start)
        mm, ss = divmod(start, 60)
        text = (seg.text or "").strip()
        lines.append(f"[{mm:02d}:{ss:02d}] {text}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_transcribe.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add lib/transcribe.py tests/test_transcribe.py && git status --short
```

Ask: *"transcribe module + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(lib): Groq whisper transcribe wrapper"
```

---

## Task 7: lib/frames.py — ffmpeg frame extraction

**Files:**
- Create: `~/Projects/VideoSkill/lib/frames.py`
- Create: `~/Projects/VideoSkill/tests/test_frames.py`

- [ ] **Step 1: Write failing tests**

Create `~/Projects/VideoSkill/tests/test_frames.py` with:

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib import frames


def test_parse_timestamp_handles_mm_ss():
    assert frames.parse_timestamp("00:30") == 30
    assert frames.parse_timestamp("02:15") == 135
    assert frames.parse_timestamp("00:00") == 0


def test_parse_timestamp_handles_h_mm_ss():
    assert frames.parse_timestamp("1:02:15") == 3735


def test_parse_timestamp_rejects_garbage():
    with pytest.raises(ValueError):
        frames.parse_timestamp("not-a-time")


def test_format_frame_filename_zero_pads():
    assert frames.format_frame_filename(30) == "00-00-30.jpg"
    assert frames.format_frame_filename(3735) == "01-02-15.jpg"


def test_extract_frames_invokes_ffmpeg_per_timestamp(tmp_path, mocker):
    video = tmp_path / "v.mp4"
    video.touch()
    out = tmp_path / "frames"

    run_mock = mocker.patch("lib.frames.subprocess.run", return_value=MagicMock(returncode=0))

    written = frames.extract_frames(
        video_path=video,
        timestamps=["00:30", "02:15"],
        out_dir=out,
    )

    assert run_mock.call_count == 2
    cmd = run_mock.call_args_list[0].args[0]
    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd
    assert "30" in cmd  # parsed seconds
    assert "-frames:v" in cmd and "1" in cmd
    assert "-q:v" in cmd and "2" in cmd
    assert str(out / "00-00-30.jpg") in cmd

    assert written == [out / "00-00-30.jpg", out / "00-02-15.jpg"]
    assert out.exists()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_frames.py -v
```

Expected: import error.

- [ ] **Step 3: Implement `lib/frames.py`**

Create `~/Projects/VideoSkill/lib/frames.py` with:

```python
import subprocess
from pathlib import Path
from typing import Sequence


class FrameExtractError(RuntimeError):
    pass


def parse_timestamp(value: str) -> int:
    parts = value.strip().split(":")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"invalid timestamp: {value!r}")
    if len(parts) == 2:
        m, s = (int(x) for x in parts)
        return m * 60 + s
    if len(parts) == 3:
        h, m, s = (int(x) for x in parts)
        return h * 3600 + m * 60 + s
    raise ValueError(f"invalid timestamp: {value!r}")


def format_frame_filename(total_seconds: int) -> str:
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}-{m:02d}-{s:02d}.jpg"


def extract_frames(
    *,
    video_path: Path,
    timestamps: Sequence[str],
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for raw in timestamps:
        seconds = parse_timestamp(raw)
        out_path = out_dir / format_frame_filename(seconds)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seconds),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise FrameExtractError(
                f"ffmpeg frame at {raw} failed: {e.stderr or e.stdout}"
            ) from e
        written.append(out_path)
    return written
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_frames.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add lib/frames.py tests/test_frames.py && git status --short
```

Ask: *"frames module + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(lib): ffmpeg frame extraction"
```

---

## Task 8: lib/index.py — CLAUDE.md regeneration (TDD)

**Files:**
- Create: `~/Projects/VideoSkill/lib/index.py`
- Create: `~/Projects/VideoSkill/tests/test_index.py`

The index has a static "header" (instructions for Claude) and an auto-generated "library" section listing every video. Regeneration replaces only the auto-generated section, keeping any user-edited prose in the header.

- [ ] **Step 1: Write failing tests**

Create `~/Projects/VideoSkill/tests/test_index.py` with:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from lib import index


def _write_video(library_root: Path, sub: str, slug: str, *, title: str, channel: str = "X"):
    folder = library_root / sub / slug
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({
        "url": f"https://youtu.be/{slug}",
        "title": title,
        "channel": channel,
        "duration_seconds": 600,
        "ingest_date": "2026-04-29T12:00:00+00:00",
        "source_hash": "sha1:x",
    }))
    (folder / "summary.md").write_text(f"# {title}\n\n200-word overview here.\n")


def test_scan_library_groups_by_subfolder(tmp_path):
    _write_video(tmp_path, "daniel-priestly", "kpoi", title="KPOI", channel="Daniel Priestly")
    _write_video(tmp_path, "daniel-priestly", "linkedin", title="LinkedIn", channel="Daniel Priestly")
    _write_video(tmp_path, "ppc", "audit", title="PPC Audit", channel="Some Expert")

    grouped = index.scan_library(tmp_path)

    assert set(grouped.keys()) == {"daniel-priestly", "ppc"}
    assert {v["slug"] for v in grouped["daniel-priestly"]} == {"kpoi", "linkedin"}
    assert grouped["ppc"][0]["title"] == "PPC Audit"


def test_render_index_section_lists_videos(tmp_path):
    _write_video(tmp_path, "daniel-priestly", "kpoi", title="KPOI Talk", channel="Daniel Priestly")
    grouped = index.scan_library(tmp_path)

    section = index.render_index_section(grouped)
    assert "## Library" in section
    assert "### daniel-priestly" in section
    assert "kpoi" in section
    assert "KPOI Talk" in section


def test_regenerate_replaces_only_marked_section(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    _write_video(library, "x", "v1", title="V1")

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# VideoSkill library\n"
        "\n"
        "Header prose, user-edited.\n"
        "\n"
        "<!-- BEGIN AUTO-INDEX -->\n"
        "old content\n"
        "<!-- END AUTO-INDEX -->\n"
        "\n"
        "Footer prose.\n"
    )

    index.regenerate(claude_md_path=claude_md, library_root=library)

    text = claude_md.read_text()
    assert "Header prose, user-edited." in text
    assert "Footer prose." in text
    assert "old content" not in text
    assert "### x" in text
    assert "v1" in text
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_index.py -v
```

Expected: import error.

- [ ] **Step 3: Implement `lib/index.py`**

Create `~/Projects/VideoSkill/lib/index.py` with:

```python
import json
import re
from pathlib import Path

BEGIN_MARKER = "<!-- BEGIN AUTO-INDEX -->"
END_MARKER = "<!-- END AUTO-INDEX -->"


def scan_library(library_root: Path) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    if not library_root.exists():
        return grouped
    for sub in sorted(p for p in library_root.iterdir() if p.is_dir()):
        videos = []
        for slug_dir in sorted(p for p in sub.iterdir() if p.is_dir()):
            meta_path = slug_dir / "meta.json"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text())
            videos.append({
                "slug": slug_dir.name,
                "subfolder": sub.name,
                "title": meta.get("title", slug_dir.name),
                "channel": meta.get("channel", ""),
                "url": meta.get("url", ""),
                "ingest_date": meta.get("ingest_date", ""),
            })
        if videos:
            grouped[sub.name] = videos
    return grouped


def render_index_section(grouped: dict[str, list[dict]]) -> str:
    if not grouped:
        return "## Library\n\n*Empty. Run an ingest to populate.*\n"
    lines = ["## Library", ""]
    for sub, videos in grouped.items():
        lines.append(f"### {sub}")
        lines.append("")
        for v in videos:
            lines.append(f"- `{sub}/{v['slug']}/` — {v['title']}")
        lines.append("")
    return "\n".join(lines)


def regenerate(*, claude_md_path: Path, library_root: Path) -> None:
    grouped = scan_library(library_root)
    section = render_index_section(grouped)

    if not claude_md_path.exists():
        claude_md_path.write_text(_default_template(section))
        return

    text = claude_md_path.read_text()
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )
    replacement = f"{BEGIN_MARKER}\n{section}\n{END_MARKER}"
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        text = text.rstrip() + f"\n\n{replacement}\n"
    claude_md_path.write_text(text)


def _default_template(section: str) -> str:
    return (
        "# VideoSkill library\n"
        "\n"
        "Library of expert video content. Each video lives in `library/<creator-or-topic>/<slug>/`\n"
        "with `meta.json`, `transcript.md`, `summary.md`, `extracted.md`, and `frames/`.\n"
        "\n"
        "When the user asks about a creator's content, scan their subfolder's `summary.md`\n"
        "and `extracted.md` files first; only open transcripts for exact quotes.\n"
        "\n"
        f"{BEGIN_MARKER}\n{section}\n{END_MARKER}\n"
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_index.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add lib/index.py tests/test_index.py && git status --short
```

Ask: *"index module + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(lib): CLAUDE.md index regeneration"
```

---

## Task 9: ingest.py prepare subcommand

**Files:**
- Create: `~/Projects/VideoSkill/ingest.py`
- Create: `~/Projects/VideoSkill/tests/test_ingest_prepare.py`

The `prepare` subcommand: given a YouTube URL and a target subfolder, create the slug folder, download the video into `<slug>/.source.mp4`, extract audio to `<slug>/.audio.mp3`, transcribe it via Groq, write `<slug>/transcript.md`. Idempotent — exits early if `meta.json` already exists for the URL hash.

- [ ] **Step 1: Write failing test**

Create `~/Projects/VideoSkill/tests/test_ingest_prepare.py` with:

```python
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ingest as ingest_cli


def test_prepare_downloads_transcribes_writes_transcript(tmp_path, mocker, capsys):
    library = tmp_path / "library"

    fake_info = {
        "title": "KPOI Talk",
        "channel": "Daniel Priestly",
        "duration": 1800,
        "webpage_url": "https://youtu.be/abc",
    }

    def fake_download(*, url, out_dir, out_basename):
        video = out_dir / f"{out_basename}.mp4"
        video.write_bytes(b"fake-mp4")
        info_path = out_dir / f"{out_basename}.info.json"
        info_path.write_text(json.dumps(fake_info))
        return {"video_path": video, "info_path": info_path, "info": fake_info}

    mocker.patch("ingest.download.download_video", side_effect=fake_download)
    mocker.patch("ingest.transcribe.extract_audio", side_effect=lambda *, video_path, audio_path: audio_path.write_bytes(b"fake-mp3"))
    mocker.patch(
        "ingest.transcribe.transcribe_audio",
        return_value=[
            SimpleNamespace(start=0.0, end=2.0, text="Hello."),
            SimpleNamespace(start=120.0, end=125.0, text="Now the next bit."),
        ],
    )

    rc = ingest_cli.run(["prepare", "https://youtu.be/abc", "--to", "daniel-priestly", "--library", str(library)])

    assert rc == 0
    slug_folder = library / "daniel-priestly" / "kpoi-talk"
    assert (slug_folder / "transcript.md").exists()
    assert (slug_folder / ".source.mp4").exists()
    assert (slug_folder / ".audio.mp3").exists()

    transcript = (slug_folder / "transcript.md").read_text()
    assert "[00:00] Hello." in transcript
    assert "[02:00] Now the next bit." in transcript

    state = json.loads((slug_folder / ".work-state.json").read_text())
    assert state["url"] == "https://youtu.be/abc"
    assert state["title"] == "KPOI Talk"
    assert state["channel"] == "Daniel Priestly"

    out = capsys.readouterr().out
    assert f"slug_folder={slug_folder}" in out


def test_prepare_skips_when_already_ingested(tmp_path, mocker, capsys):
    library = tmp_path / "library"
    slug = library / "daniel-priestly" / "kpoi-talk"
    slug.mkdir(parents=True)
    (slug / "meta.json").write_text(json.dumps({"url": "https://youtu.be/abc", "title": "KPOI Talk"}))

    download_mock = mocker.patch("ingest.download.download_video")

    rc = ingest_cli.run(["prepare", "https://youtu.be/abc", "--to", "daniel-priestly", "--library", str(library)])

    assert rc == 0
    download_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "already ingested" in out.lower()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_ingest_prepare.py -v
```

Expected: import error (`ingest` does not exist).

- [ ] **Step 3: Implement `ingest.py` (prepare only)**

Create `~/Projects/VideoSkill/ingest.py` with:

```python
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib import download, frames, index, meta, paths, transcribe


def _cmd_prepare(args: argparse.Namespace) -> int:
    library_root = Path(args.library).resolve()
    url = args.url
    subfolder = args.to

    # Idempotence: check if any existing slug folder under this subfolder has matching url in meta.json.
    sub_dir = library_root / subfolder
    if sub_dir.exists():
        for existing in sub_dir.iterdir():
            mp = existing / "meta.json"
            if mp.exists():
                existing_meta = json.loads(mp.read_text())
                if existing_meta.get("url") == url:
                    print(f"already ingested: {existing}")
                    print(f"slug_folder={existing}")
                    return 0

    # Initial download into a temp basename; the final slug uses the title from yt-dlp info.
    sub_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = sub_dir / ".staging"
    tmp_dir.mkdir(exist_ok=True)
    tmp_basename = "incoming"

    try:
        dl = download.download_video(url=url, out_dir=tmp_dir, out_basename=tmp_basename)
    except download.DownloadError as e:
        print(f"ERROR: download failed: {e}", file=sys.stderr)
        return 2

    info = dl["info"]
    title = info.get("title", "untitled")
    channel = info.get("channel") or info.get("uploader") or ""
    duration = int(info.get("duration") or 0)

    slug_folder = paths.slug_folder(library_root=library_root, subfolder=subfolder, title=title)
    slug_folder.mkdir(parents=True, exist_ok=True)

    # Move source files into slug folder with hidden names.
    source_video = slug_folder / ".source.mp4"
    source_audio = slug_folder / ".audio.mp3"
    dl["video_path"].rename(source_video)

    try:
        transcribe.extract_audio(video_path=source_video, audio_path=source_audio)
    except transcribe.TranscribeError as e:
        print(f"ERROR: audio extract failed: {e}", file=sys.stderr)
        return 3

    try:
        segments = transcribe.transcribe_audio(audio_path=source_audio)
    except Exception as e:
        print(f"ERROR: transcription failed: {e}", file=sys.stderr)
        return 4

    transcript_md = transcribe.format_transcript(segments)
    (slug_folder / "transcript.md").write_text(transcript_md)

    # Persist work state for the finalize step.
    state = {
        "url": url,
        "title": title,
        "channel": channel,
        "duration_seconds": duration,
        "subfolder": subfolder,
        "source_video": str(source_video),
        "source_audio": str(source_audio),
    }
    (slug_folder / ".work-state.json").write_text(json.dumps(state, indent=2))

    # Cleanup staging.
    for p in tmp_dir.glob("*"):
        p.unlink()
    tmp_dir.rmdir()

    print(f"slug_folder={slug_folder}")
    print(f"transcript={slug_folder / 'transcript.md'}")
    print("Now: read the transcript, write summary.md and extracted.md, then call:")
    print(f"  python ingest.py finalize {slug_folder} --frames \"<comma-separated mm:ss list>\"")
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    # Implemented in Task 10.
    raise NotImplementedError("finalize subcommand pending Task 10")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="download, transcribe, write transcript.md")
    p.add_argument("url")
    p.add_argument("--to", required=True, help="subfolder name under library/")
    p.add_argument("--library", default=str(Path(__file__).parent / "library"))
    p.set_defaults(func=_cmd_prepare)

    f = sub.add_parser("finalize", help="extract frames, write meta.json, regenerate index, cleanup")
    f.add_argument("slug_folder")
    f.add_argument("--frames", default="", help="comma-separated mm:ss timestamps")
    f.set_defaults(func=_cmd_finalize)

    return parser


def run(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_ingest_prepare.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add ingest.py tests/test_ingest_prepare.py && git status --short
```

Ask: *"prepare subcommand + tests ready. Commit?"*

If yes:

```bash
git commit -m "feat(ingest): prepare subcommand (download → transcribe)"
```

---

## Task 10: ingest.py finalize subcommand

**Files:**
- Modify: `~/Projects/VideoSkill/ingest.py` — implement `_cmd_finalize`
- Create: `~/Projects/VideoSkill/tests/test_ingest_finalize.py`

`finalize` reads `.work-state.json`, extracts frames from `.source.mp4` at the supplied timestamps, writes `meta.json`, deletes `.source.mp4` / `.audio.mp3` / `.work-state.json`, and regenerates the top-level `CLAUDE.md` index.

- [ ] **Step 1: Write failing test**

Create `~/Projects/VideoSkill/tests/test_ingest_finalize.py` with:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import ingest as ingest_cli


def _seed_prepared_slug(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    slug = library / "daniel-priestly" / "kpoi-talk"
    slug.mkdir(parents=True)
    (slug / ".source.mp4").write_bytes(b"x")
    (slug / ".audio.mp3").write_bytes(b"x")
    (slug / "transcript.md").write_text("[00:00] hello\n")
    (slug / "summary.md").write_text("# KPOI Talk\nOverview...\n")
    (slug / "extracted.md").write_text("# Frameworks\n- 5 Ps\n")
    (slug / ".work-state.json").write_text(json.dumps({
        "url": "https://youtu.be/abc",
        "title": "KPOI Talk",
        "channel": "Daniel Priestly",
        "duration_seconds": 1800,
        "subfolder": "daniel-priestly",
        "source_video": str(slug / ".source.mp4"),
        "source_audio": str(slug / ".audio.mp3"),
    }))
    (tmp_path / "CLAUDE.md").write_text(
        "# Library\n\n<!-- BEGIN AUTO-INDEX -->\nold\n<!-- END AUTO-INDEX -->\n"
    )
    return slug


def test_finalize_extracts_frames_writes_meta_cleans_up(tmp_path, mocker):
    slug = _seed_prepared_slug(tmp_path)

    def fake_extract(*, video_path, timestamps, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for ts in timestamps:
            p = out_dir / f"frame-{ts.replace(':', '-')}.jpg"
            p.write_bytes(b"jpg")
            written.append(p)
        return written

    mocker.patch("ingest.frames.extract_frames", side_effect=fake_extract)

    rc = ingest_cli.run([
        "finalize",
        str(slug),
        "--frames", "00:30,02:15",
        "--claude-md", str(tmp_path / "CLAUDE.md"),
        "--library", str(tmp_path / "library"),
    ])
    assert rc == 0

    # meta.json written with right fields
    meta_data = json.loads((slug / "meta.json").read_text())
    assert meta_data["url"] == "https://youtu.be/abc"
    assert meta_data["title"] == "KPOI Talk"
    assert meta_data["channel"] == "Daniel Priestly"
    assert meta_data["duration_seconds"] == 1800

    # frames extracted
    assert (slug / "frames").exists()
    assert any(p.suffix == ".jpg" for p in (slug / "frames").iterdir())

    # cleanup happened
    assert not (slug / ".source.mp4").exists()
    assert not (slug / ".audio.mp3").exists()
    assert not (slug / ".work-state.json").exists()

    # CLAUDE.md regenerated
    claude_text = (tmp_path / "CLAUDE.md").read_text()
    assert "old" not in claude_text
    assert "kpoi-talk" in claude_text


def test_finalize_errors_when_state_missing(tmp_path):
    slug = tmp_path / "library" / "x" / "y"
    slug.mkdir(parents=True)
    rc = ingest_cli.run([
        "finalize", str(slug),
        "--claude-md", str(tmp_path / "CLAUDE.md"),
        "--library", str(tmp_path / "library"),
    ])
    assert rc != 0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_ingest_finalize.py -v
```

Expected: `NotImplementedError` raised by the placeholder `_cmd_finalize`.

- [ ] **Step 3: Implement `_cmd_finalize` and add new args**

Edit `~/Projects/VideoSkill/ingest.py`. Replace the `_cmd_finalize` function with:

```python
def _cmd_finalize(args: argparse.Namespace) -> int:
    slug_folder = Path(args.slug_folder).resolve()
    state_path = slug_folder / ".work-state.json"
    if not state_path.exists():
        print(f"ERROR: no .work-state.json at {state_path} — was prepare run?", file=sys.stderr)
        return 5

    state = json.loads(state_path.read_text())
    source_video = Path(state["source_video"])
    source_audio = Path(state["source_audio"])

    raw = (args.frames or "").strip()
    timestamps = [t.strip() for t in raw.split(",") if t.strip()] if raw else []

    if timestamps:
        try:
            frames.extract_frames(
                video_path=source_video,
                timestamps=timestamps,
                out_dir=slug_folder / "frames",
            )
        except (frames.FrameExtractError, ValueError) as e:
            print(f"ERROR: frame extraction failed: {e}", file=sys.stderr)
            return 6

    meta.write(
        folder=slug_folder,
        url=state["url"],
        title=state["title"],
        channel=state["channel"],
        duration_seconds=int(state["duration_seconds"]),
        ingest_date=datetime.now(timezone.utc),
        source_hash=meta.hash_url(state["url"]),
    )

    # Cleanup.
    for p in (source_video, source_audio, state_path):
        if p.exists():
            p.unlink()

    # Regenerate CLAUDE.md.
    library_root = Path(args.library).resolve()
    claude_md = Path(args.claude_md).resolve()
    index.regenerate(claude_md_path=claude_md, library_root=library_root)

    print(f"finalized: {slug_folder}")
    return 0
```

Then update the parser block to add `--claude-md` and `--library` to the `finalize` subparser. Find:

```python
    f = sub.add_parser("finalize", help="extract frames, write meta.json, regenerate index, cleanup")
    f.add_argument("slug_folder")
    f.add_argument("--frames", default="", help="comma-separated mm:ss timestamps")
    f.set_defaults(func=_cmd_finalize)
```

Replace with:

```python
    f = sub.add_parser("finalize", help="extract frames, write meta.json, regenerate index, cleanup")
    f.add_argument("slug_folder")
    f.add_argument("--frames", default="", help="comma-separated mm:ss timestamps")
    f.add_argument("--library", default=str(Path(__file__).parent / "library"))
    f.add_argument("--claude-md", default=str(Path(__file__).parent / "CLAUDE.md"))
    f.set_defaults(func=_cmd_finalize)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest tests/test_ingest_finalize.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Run the full test suite**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -m pytest -v
```

Expected: every test green (paths, meta, download, transcribe, frames, index, ingest_prepare, ingest_finalize).

- [ ] **Step 6: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add ingest.py tests/test_ingest_finalize.py && git status --short
```

Ask: *"finalize subcommand + tests ready, full suite green. Commit?"*

If yes:

```bash
git commit -m "feat(ingest): finalize subcommand (frames + meta + index + cleanup)"
```

---

## Task 11: Initial CLAUDE.md skeleton

**Files:**
- Create: `~/Projects/VideoSkill/CLAUDE.md`

- [ ] **Step 1: Write the skeleton**

Create `~/Projects/VideoSkill/CLAUDE.md` with:

```markdown
# VideoSkill library

Library of expert video content. Each video lives in `library/<creator-or-topic>/<slug>/`
with `meta.json`, `transcript.md`, `summary.md`, `extracted.md`, and `frames/`.

## How to use this library

When the user asks about a creator's content (e.g. "what would Daniel Priestly say about
LinkedIn posts"):

1. Skim the auto-index below to spot the relevant subfolder.
2. `grep -l <topic> library/<sub>/*/summary.md library/<sub>/*/extracted.md` to find
   matching videos quickly. `extracted.md` is where frameworks, templates, and quotes live;
   `summary.md` is the lighter overview.
3. Read the matching `summary.md` and `extracted.md` files.
4. Open `transcript.md` only if you need exact wording — quote with the `[mm:ss]` timestamp.
5. If the question is visual, look at `frames/` for the relevant timestamp.
6. Answer with citations like `(daniel-priestly/kpoi-five-ps, 14:32)` so the user can jump
   back to source.

## How to ingest new content

1. `source ./load-secrets.sh` to load `GROQ_API_KEY` from bws.
2. `source .venv/bin/activate`.
3. Tell Claude in this folder, e.g. *"ingest these URLs into daniel-priestly: <URLs>"*.

The Python helpers do mechanical work; Claude does summarisation and frame-timestamp
selection. See `docs/superpowers/specs/2026-04-29-videoskill-design.md` for the design
and `docs/superpowers/plans/2026-04-29-videoskill-implementation.md` for the build.

<!-- BEGIN AUTO-INDEX -->
## Library

*Empty. Run an ingest to populate.*
<!-- END AUTO-INDEX -->
```

- [ ] **Step 2: Verify auto-regeneration preserves the prose**

```bash
cd ~/Projects/VideoSkill && .venv/bin/python -c "
from pathlib import Path
from lib import index
index.regenerate(
    claude_md_path=Path('CLAUDE.md'),
    library_root=Path('library'),
)
print(Path('CLAUDE.md').read_text())
"
```

Expected: `CLAUDE.md` contents printed; the prose above the marker is preserved; the auto-index section says *"Empty. Run an ingest to populate."*.

- [ ] **Step 3: Stage and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git add CLAUDE.md && git status --short
```

Ask: *"`CLAUDE.md` skeleton ready. Commit?"*

If yes:

```bash
git commit -m "docs: initial CLAUDE.md library index skeleton"
```

---

## Task 12: Install upstream `/watch` skill

This is a manual Claude Code action — no file changes in `~/Projects/VideoSkill/`.

- [ ] **Step 1: Add the marketplace and install the skill**

In a Claude Code session (any folder), run:

```
/plugin marketplace add bradautomates/claude-video
/plugin install watch@claude-video
```

- [ ] **Step 2: Verify install**

In the same session:

```
/help
```

Expected: `/watch` appears among the available commands. Or run `/watch --help` and check it responds.

- [ ] **Step 3: No commit** — this is plugin-level, outside the project repo.

---

## Task 13: End-to-end smoke test on one short video

**Files modified during this task:** `~/Projects/VideoSkill/CLAUDE.md`, `~/Projects/VideoSkill/library/<subfolder>/<slug>/*` (new content). Possibly small adjustments to the cognitive prompt instructions if the smoke test reveals issues.

Goal: prove the whole loop end-to-end on one ~5-10 minute Priestly clip before any batch.

- [ ] **Step 1: Pick a short test video**

Ask Simon: *"Got a short (~5-10 min) Priestly clip URL for the smoke test? Otherwise I'll pick one from his channel."*

If Simon picks: use that URL. Otherwise: search Daniel Priestly's YouTube channel for a clip ≤ 10 minutes; record the URL chosen.

- [ ] **Step 2: Activate venv and load secrets in the terminal where Claude Code is running**

```bash
cd ~/Projects/VideoSkill && source ./load-secrets.sh && source .venv/bin/activate && [ -n "${GROQ_API_KEY:-}" ] && echo "ready"
```

Expected: `GROQ_API_KEY loaded from bws (Grok_API_Key).` then `ready`.

- [ ] **Step 3: Run `prepare`**

```bash
cd ~/Projects/VideoSkill && python ingest.py prepare "<URL>" --to daniel-priestly
```

Expected: prints `slug_folder=...`, `transcript=...`, and a hint to call `finalize`. Look at `slug_folder/transcript.md` — it should contain timestamped lines.

- [ ] **Step 4: Read the transcript and write summary.md + extracted.md**

The Claude session that's executing this plan reads `<slug_folder>/transcript.md` and writes:

- `<slug_folder>/summary.md` — 200-word overview, plus 5-10 timestamped key points (e.g. `- [04:12] He defines the 5 Ps as...`).
- `<slug_folder>/extracted.md` — frameworks (named, with definitions); step-by-step processes (numbered); templates / scripts (verbatim, in code fences); memorable quotes (verbatim, with timestamp); explicit do's / don'ts. Skip generic "summary"-style prose — this file is fuel for skill creation.

Also pick **5–15 frame timestamps** that capture meaningful visual moments (slides, on-screen examples, key beats). Note them as a comma-separated `mm:ss` list, e.g. `01:30,03:45,05:12,07:00`.

- [ ] **Step 5: Run `finalize`**

```bash
cd ~/Projects/VideoSkill && python ingest.py finalize "<slug_folder>" --frames "<the,picked,timestamps>"
```

Expected: prints `finalized: <slug_folder>`. Inside the folder you should now see `meta.json`, `frames/` with one JPG per timestamp, no `.source.mp4` / `.audio.mp3` / `.work-state.json`.

- [ ] **Step 6: Verify `CLAUDE.md` was regenerated**

```bash
grep -A 30 "BEGIN AUTO-INDEX" ~/Projects/VideoSkill/CLAUDE.md
```

Expected: the auto-index section now lists `daniel-priestly/<slug>/`.

- [ ] **Step 7: Open a fresh chat in the project and test retrieval**

```bash
cd ~/Projects/VideoSkill && claude
```

In that chat, ask the question your test video should be able to answer (e.g. *"What's the main argument in the Priestly clip we just ingested?"*). Verify Claude can find the right `summary.md` / `extracted.md` and answer with a citation.

- [ ] **Step 8: Iterate on prompt quality if needed**

If `summary.md` or `extracted.md` is too generic, refine the cognitive instructions in step 4 above and either:

- Re-run steps 4–6 by deleting the slug folder's `summary.md` / `extracted.md` (keeping transcript), rewriting them, and re-running finalize. Or
- Adjust step-4 guidance in this plan / in `CLAUDE.md` and try a fresh video.

Capture any rule that worked well into a "writing summary.md / extracted.md" section in `CLAUDE.md` so future ingests inherit it.

- [ ] **Step 9: Stage any edits and pause for commit approval**

```bash
cd ~/Projects/VideoSkill && git status --short
```

If anything new in tracked code (e.g. `CLAUDE.md` updates from step 8):

Ask: *"Smoke test passed. Commit the prompt-tuning changes?"*

If yes:

```bash
git add -u && git commit -m "chore: tune cognitive prompt after smoke test"
```

The library content (`library/daniel-priestly/...`) is gitignored — nothing to commit there.

---

## Self-review

**Spec coverage check:**

- ✅ Components installed (upstream `/watch` skill: Task 12; `ingest.py` + lib: Tasks 5–10; top-level `CLAUDE.md`: Task 11)
- ✅ Folder layout matches spec (Tasks 1, 9, 10, 11)
- ✅ Per-video flow steps 1–10 from spec → Tasks 9 (steps 1–5) and 10 (steps 6–10)
- ✅ Idempotence / resume by URL hash → Task 9 step 3 (URL match in existing meta.json)
- ✅ Batch interface → not a Task; deliberate, since batch is Claude-driven (one prepare/finalize loop per URL)
- ✅ Retrieval pattern → Task 11 (skeleton text guides Claude on retrieval) + Task 13 step 7 (verify it works)
- ✅ Skill creation workflow → not a Task; emerges from the library + existing `anthropic-skills:skill-creator`
- ✅ Costs match: only Groq is metered; Claude work is in-session
- ✅ Prerequisites: bws verified Task 2; Python deps Task 1; upstream skill Task 12
- ✅ Install order from spec: Tasks 1–13 follow it linearly

**Placeholder scan:** No "TBD", "implement later", "add appropriate error handling", or "similar to Task N". Every code block has the actual code. The only deferred decision is the cognitive prompt quality, and that has an explicit iteration loop (Task 13 step 8).

**Type / signature consistency:**

- `paths.slug_for_title(title: str) -> str` ✓ used in `paths.slug_folder`, no other callers
- `paths.slug_folder(library_root, subfolder, title) -> Path` ✓ used in `ingest._cmd_prepare`
- `download.download_video(*, url, out_dir, out_basename) -> DownloadResult` ✓ used in `ingest._cmd_prepare`
- `transcribe.extract_audio(*, video_path, audio_path)` ✓ used in `ingest._cmd_prepare`
- `transcribe.transcribe_audio(*, audio_path)` ✓ used in `ingest._cmd_prepare`
- `transcribe.format_transcript(segments)` ✓ used in `ingest._cmd_prepare`
- `frames.extract_frames(*, video_path, timestamps, out_dir)` ✓ used in `ingest._cmd_finalize`
- `meta.write(*, folder, url, title, channel, duration_seconds, ingest_date, source_hash)` ✓ used in `ingest._cmd_finalize`
- `meta.hash_url(url) -> str` ✓ used in `ingest._cmd_finalize`
- `index.regenerate(*, claude_md_path, library_root)` ✓ used in `ingest._cmd_finalize`
- All keyword-only args called with keywords. ✓
- Test mocks target the imported names actually used (`ingest.download.download_video`, etc.). ✓

No mismatches found.

---

## Done criteria

- All `pytest -v` green.
- `python ingest.py prepare … && python ingest.py finalize …` produces a complete slug folder (`meta.json`, `transcript.md`, `summary.md`, `extracted.md`, `frames/`).
- Top-level `CLAUDE.md` auto-updates after every `finalize`.
- Fresh Claude Code chat in `~/Projects/VideoSkill/` can answer a content question with a correct citation pointing back to the right slug folder.
- Upstream `/watch` skill installed and `/watch` available in any Claude Code session.
