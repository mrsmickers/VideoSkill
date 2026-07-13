# Parakeet Transcription + claude-video Raids + /watch-worth-it Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Groq with local Parakeet v2 transcription, raid download/frame mechanics from bradautomates/claude-video (MIT), and add a cross-agent `/watch-worth-it` triage skill.

**Architecture:** `lib/transcribe.py` swaps its backend to a lazily-loaded parakeet-mlx model (same `Segment` interface, so `ingest.py` and `transcript.md` are untouched). `lib/download.py` gains argv hardening and capped-resolution parallel downloads. `lib/frames.py` gains advisory scene-detection and near-duplicate helpers used by two new `ingest.py` behaviours. The triage skill is a self-contained `skills/watch-worth-it/` folder (SKILL.md + stdlib-only script) installable by symlink on any agent host.

**Tech Stack:** Python 3.14 (venv), parakeet-mlx (MLX, Apple Silicon), ffmpeg, yt-dlp, pytest + pytest-mock.

**Spec:** `docs/superpowers/specs/2026-07-13-parakeet-watch-worth-it-design.md`

**Branch:** all commits on `parakeet-watch-worth-it` (create with `git checkout -b parakeet-watch-worth-it` before Task 1). Do NOT stage the pre-existing uncommitted `CLAUDE.md` modification, `.claude/`, or `AGENTS.md` — always `git add` explicit paths.

---

### Task 1: Swap `lib/transcribe.py` to Parakeet

**Files:**
- Modify: `lib/transcribe.py`
- Modify: `tests/test_transcribe.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Rewrite the transcription tests**

Replace ALL Groq tests in `tests/test_transcribe.py` (keep `test_extract_audio_invokes_ffmpeg_with_expected_args`, `test_format_transcript_emits_timestamped_markdown`, `test_extract_audio_raises_on_ffmpeg_failure` unchanged) with:

```python
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lib import transcribe


@pytest.fixture(autouse=True)
def _reset_model_cache():
    transcribe._model = None
    yield
    transcribe._model = None


def _install_fake_parakeet(mocker, sentences):
    fake_result = SimpleNamespace(sentences=sentences)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = fake_result
    fake_module = ModuleType("parakeet_mlx")
    fake_module.from_pretrained = MagicMock(return_value=fake_model)
    mocker.patch.dict(sys.modules, {"parakeet_mlx": fake_module})
    return fake_module, fake_model


def test_transcribe_audio_maps_parakeet_sentences_to_segments(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    fake_module, fake_model = _install_fake_parakeet(mocker, [
        SimpleNamespace(start=0.0, end=3.5, text=" Hello and welcome. "),
        SimpleNamespace(start=3.5, end=9.0, text="Step one."),
    ])

    segments = transcribe.transcribe_audio(audio_path=audio)

    fake_module.from_pretrained.assert_called_once_with("mlx-community/parakeet-tdt-0.6b-v2")
    call = fake_model.transcribe.call_args
    assert call.args[0] == str(audio)
    assert call.kwargs["chunk_duration"] == 120.0
    assert call.kwargs["overlap_duration"] == 15.0
    assert segments == [
        transcribe.Segment(start=0.0, end=3.5, text="Hello and welcome."),
        transcribe.Segment(start=3.5, end=9.0, text="Step one."),
    ]


def test_transcribe_audio_honours_model_env_override(tmp_path, mocker, monkeypatch):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    monkeypatch.setenv("VIDEOSKILL_PARAKEET_MODEL", "mlx-community/other-model")
    fake_module, _ = _install_fake_parakeet(
        mocker, [SimpleNamespace(start=0.0, end=1.0, text="Hi.")]
    )

    transcribe.transcribe_audio(audio_path=audio)

    fake_module.from_pretrained.assert_called_once_with("mlx-community/other-model")


def test_transcribe_audio_loads_model_once_across_calls(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    fake_module, _ = _install_fake_parakeet(
        mocker, [SimpleNamespace(start=0.0, end=1.0, text="Hi.")]
    )

    transcribe.transcribe_audio(audio_path=audio)
    transcribe.transcribe_audio(audio_path=audio)

    assert fake_module.from_pretrained.call_count == 1


def test_transcribe_audio_raises_clear_error_when_parakeet_missing(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    mocker.patch.dict(sys.modules, {"parakeet_mlx": None})  # import → ImportError

    with pytest.raises(transcribe.TranscribeError, match="pip install parakeet-mlx"):
        transcribe.transcribe_audio(audio_path=audio)


def test_transcribe_audio_wraps_model_errors(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    _, fake_model = _install_fake_parakeet(mocker, [])
    fake_model.transcribe.side_effect = RuntimeError("mlx exploded")

    with pytest.raises(transcribe.TranscribeError, match="mlx exploded"):
        transcribe.transcribe_audio(audio_path=audio)


def test_transcribe_audio_raises_on_empty_result(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")
    _install_fake_parakeet(mocker, [])

    with pytest.raises(transcribe.TranscribeError, match="no sentences"):
        transcribe.transcribe_audio(audio_path=audio)
```

Also update `test_format_transcript_emits_timestamped_markdown` only if it references Groq (it doesn't — leave as is).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_transcribe.py -v`
Expected: new tests FAIL (`transcribe_audio` still calls Groq; `_model` attribute missing).

- [ ] **Step 3: Rewrite `lib/transcribe.py`**

Full replacement (keeps `extract_audio` and `format_transcript` byte-identical to current):

```python
import os
import subprocess
from pathlib import Path
from typing import Iterable, NamedTuple

PARAKEET_MODEL_ENV = "VIDEOSKILL_PARAKEET_MODEL"
DEFAULT_PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v2"
# parakeet-tdt-0.6b-v2 handles up to ~24 min in one pass; chunking with overlap
# keeps memory flat and timestamps stitched on longer audio.
CHUNK_DURATION_SECONDS = 120.0
OVERLAP_DURATION_SECONDS = 15.0


class TranscribeError(RuntimeError):
    pass


class Segment(NamedTuple):
    start: float
    end: float
    text: str


_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from parakeet_mlx import from_pretrained
        except ImportError as e:
            raise TranscribeError(
                "parakeet-mlx is not installed. Fix: .venv/bin/pip install parakeet-mlx "
                "(Apple Silicon only; first run downloads the ~1.2 GB model from Hugging Face)"
            ) from e
        model_name = os.environ.get(PARAKEET_MODEL_ENV) or DEFAULT_PARAKEET_MODEL
        _model = from_pretrained(model_name)
    return _model


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


def transcribe_audio(*, audio_path: Path) -> list[Segment]:
    model = _get_model()
    try:
        result = model.transcribe(
            str(audio_path),
            chunk_duration=CHUNK_DURATION_SECONDS,
            overlap_duration=OVERLAP_DURATION_SECONDS,
        )
    except Exception as e:
        raise TranscribeError(f"Parakeet transcription failed: {e}") from e
    segments = [
        Segment(start=float(s.start), end=float(s.end), text=str(s.text).strip())
        for s in result.sentences
        if str(s.text).strip()
    ]
    if not segments:
        raise TranscribeError("Parakeet returned no sentences")
    return segments


def format_transcript(segments: Iterable) -> str:
    lines = []
    for seg in segments:
        start = int(seg.start)
        mm, ss = divmod(start, 60)
        text = (seg.text or "").strip()
        # mm:ss — visual alignment breaks (not value) for videos > 99 min; fine for our use case.
        lines.append(f"[{mm:02d}:{ss:02d}] {text}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Update `requirements.txt`**

Replace the `groq>=0.11.0` line with:

```
parakeet-mlx>=0.5.2; sys_platform == "darwin" and platform_machine == "arm64"
```

(Marker keeps Linux CI installs working; tests mock the module so CI never needs MLX.)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: ALL PASS (no test imports `groq` any more).

- [ ] **Step 6: Commit**

```bash
git add lib/transcribe.py tests/test_transcribe.py requirements.txt
git commit -m "feat(transcribe): replace Groq API with local parakeet-mlx (parakeet-tdt-0.6b-v2)"
```

---

### Task 2: Groq removal sweep — env, secrets loader, docs

**Files:**
- Modify: `.env.example`
- Modify: `load-secrets.sh`
- Modify: `CLAUDE.md` (setup steps 3–4, ingest intro)
- Modify: `README.md` (any GROQ/Groq mentions)

- [ ] **Step 1: `.env.example`** — delete the `=== Required for ingestion ===` block and `GROQ_API_KEY=` line; change the header comment to:

```
# Copy this file to .env (or .env.local) and fill in your own values, then:
#   set -a; source .env; set +a
# Transcription is fully local (parakeet-mlx) — no API key needed to ingest.
# These vars are only needed for publishing frames (Notion or R2).
```

- [ ] **Step 2: `load-secrets.sh`** — delete the entire "Groq whisper key" block; change the summary section so `_loaded` starts empty and only lists R2/Notion (print "Loaded from bws: <list>." only when non-empty, otherwise "Nothing loaded from bws — R2/Notion entries not found."). Keep R2 and Notion blocks unchanged.

- [ ] **Step 3: `CLAUDE.md`** — in "### 3. Get a Groq API key from the user", replace the whole section with:

```markdown
### 3. First transcription downloads the model

Transcription runs locally via parakeet-mlx (installed in step 2; Apple
Silicon only). The first ingest downloads the ~1.2 GB
`mlx-community/parakeet-tdt-0.6b-v2` model from Hugging Face — let the
user know, then it's cached forever. No API key needed.
```

In "### 4. Load env into the current shell": note env is only needed when publishing (Notion/R2), not for ingestion. In "## How to ingest new content": change "Make sure env is loaded first: `set -a; source .env; set +a`." to "No env needed for ingestion (transcription is local). Load `.env` only when publishing frames."

- [ ] **Step 4: `README.md`** — `grep -n -i groq README.md` and rewrite each hit to describe local Parakeet transcription (free, local, Apple Silicon, ~1.2 GB one-time model download). Keep tone/structure of surrounding text.

- [ ] **Step 5: Verify no stale references**

Run: `grep -rn -i groq --include='*.py' --include='*.md' --include='*.sh' --include='*.txt' . | grep -v .venv | grep -v library/ | grep -v docs/superpowers | grep -v scratchpad`
Expected: no hits (spec/plan under docs/superpowers may mention Groq historically — excluded).

- [ ] **Step 6: Commit**

```bash
git add .env.example load-secrets.sh CLAUDE.md README.md
git commit -m "docs: drop Groq setup — transcription is local via parakeet-mlx"
```

---

### Task 3: Harden + speed up `lib/download.py`

**Files:**
- Modify: `lib/download.py`
- Modify: `tests/test_download.py`

- [ ] **Step 1: Add failing tests** (append to `tests/test_download.py`):

```python
def test_download_hardens_argv_and_caps_resolution(tmp_path, mocker):
    fake_info = json.loads(FIXTURE.read_text())
    (tmp_path / "video.info.json").write_text(json.dumps(fake_info))
    (tmp_path / "video.mp4").touch()
    run_mock = mocker.patch(
        "lib.download.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="", stderr=""),
    )

    download.download_video(url="https://youtu.be/abc", out_dir=tmp_path, out_basename="video")

    cmd = run_mock.call_args.args[0]
    # option-injection hardening: URL is the last element, preceded by `--`
    assert cmd[-1] == "https://youtu.be/abc"
    assert cmd[-2] == "--"
    # capped resolution + parallel fragments
    assert "-N" in cmd and "8" in cmd
    fmt = cmd[cmd.index("-f") + 1]
    assert "height<=1080" in fmt


def test_download_rejects_dash_prefixed_source(tmp_path, mocker):
    run_mock = mocker.patch("lib.download.subprocess.run")
    with pytest.raises(download.DownloadError, match="refusing"):
        download.download_video(url="--exec=evil", out_dir=tmp_path, out_basename="v")
    run_mock.assert_not_called()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_download.py -v` — new tests FAIL.

- [ ] **Step 3: Implement** — in `download_video`, before building the command:

```python
    if url.startswith("-"):
        raise DownloadError(f"refusing suspicious source (starts with '-'): {url!r}")
```

and change the command to:

```python
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--write-info-json",
        "-N", "8",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/bv+ba/b",
        "--merge-output-format", "mp4",
        "--restrict-filenames",
        "-o", out_template,
        "--",
        url,
    ]
```

- [ ] **Step 4: Run the suite** — `.venv/bin/python -m pytest -q` → ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/download.py tests/test_download.py
git commit -m "feat(download): harden yt-dlp argv, cap 1080p, 8 parallel fragments (raided from claude-video)"
```

---

### Task 4: Scene detection + near-duplicate helpers in `lib/frames.py`

**Files:**
- Create: `tests/conftest.py`
- Modify: `lib/frames.py`
- Modify: `tests/test_frames.py`

- [ ] **Step 1: Create `tests/conftest.py`** with ffmpeg-synthesised clip fixtures (adapted from bradautomates/claude-video, MIT):

```python
"""Shared fixtures: ffmpeg-synthesised clips (no network).

Clip builders adapted from bradautomates/claude-video (MIT,
https://github.com/bradautomates/claude-video).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

COLORS = ["red", "green", "blue", "white", "black", "yellow", "cyan", "magenta"]


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr}")


def build_cut_clip(path: Path, n: int = 8, seg: float = 0.5, size: str = "320x240", fps: int = 10) -> None:
    """n solid-colour segments concatenated — a hard scene cut at every boundary."""
    inputs: list[str] = []
    for i in range(n):
        inputs += ["-f", "lavfi", "-t", str(seg), "-i", f"color=c={COLORS[i % len(COLORS)]}:s={size}:r={fps}"]
    streams = "".join(f"[{i}:v]" for i in range(n))
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", f"{streams}concat=n={n}:v=1:a=0[out]", "-map", "[out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-force_key_frames", f"expr:gte(t,n_forced*{seg})",
        str(path),
    ])


def build_static_clip(path: Path, duration: float = 3.0, size: str = "320x240", fps: int = 10) -> None:
    """One solid colour for the whole clip: no scene changes."""
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-t", str(duration), "-i", f"color=c=blue:s={size}:r={fps}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path),
    ])


@pytest.fixture(scope="session")
def cut_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("clips") / "cuts.mp4"
    build_cut_clip(path)
    return path


@pytest.fixture(scope="session")
def static_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("clips") / "static.mp4"
    build_static_clip(path)
    return path
```

- [ ] **Step 2: Add failing tests** (append to `tests/test_frames.py`):

```python
def test_detect_scene_timestamps_finds_cuts(cut_clip):
    ts = frames.detect_scene_timestamps(video_path=cut_clip)
    assert len(ts) >= 5          # 8 segments → 7 cuts; allow encoder slack
    assert ts == sorted(ts)
    assert all(0.0 < t < 4.0 for t in ts)


def test_detect_scene_timestamps_static_clip_finds_none(static_clip):
    assert frames.detect_scene_timestamps(video_path=static_clip) == []


def test_near_duplicate_pairs_flags_identical_frames(tmp_path, static_clip, cut_clip):
    a = frames.extract_frames(video_path=static_clip, timestamps=["00:00"], out_dir=tmp_path / "x")[0]
    b = frames.extract_frames(video_path=static_clip, timestamps=["00:02"], out_dir=tmp_path / "y")[0]
    c = frames.extract_frames(video_path=cut_clip, timestamps=["00:01"], out_dir=tmp_path / "z")[0]
    assert frames.near_duplicate_pairs([a, b]) == [(a, b)]
    assert frames.near_duplicate_pairs([a, c]) == []
```

- [ ] **Step 3: Run to verify failure** — `.venv/bin/python -m pytest tests/test_frames.py -v` → new tests FAIL (`AttributeError`).

- [ ] **Step 4: Implement in `lib/frames.py`** (append; add `import re` at top):

```python
SCENE_THRESHOLD = 0.20
DEDUP_THUMB = 16
DEDUP_THRESHOLD = 2.0
_SHOWINFO_TS_RE = re.compile(r"pts_time:([0-9.]+)")


def detect_scene_timestamps(*, video_path: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Advisory scene-change timestamps (seconds), via ffmpeg select+showinfo.

    Writes no files — used by `ingest.py propose-frames` to suggest candidates.
    Technique raided from bradautomates/claude-video (MIT).
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-i", str(Path(video_path).resolve()),
        "-vf", f"select='gt(scene\\,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FrameExtractError(f"ffmpeg scene detection failed: {result.stderr.strip()}")
    return [round(float(m.group(1)), 2) for m in _SHOWINFO_TS_RE.finditer(result.stderr)]


def _gray_thumb(path: Path) -> bytes:
    """16x16 grayscale raw bytes for a JPEG, via ffmpeg (no image libraries)."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(path),
        "-vf", f"scale={DEDUP_THUMB}:{DEDUP_THUMB},format=gray",
        "-f", "rawvideo", "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or len(result.stdout) != DEDUP_THUMB * DEDUP_THUMB:
        return b""  # fail-open: caller treats as not-a-duplicate
    return result.stdout


def near_duplicate_pairs(paths: Sequence[Path], threshold: float = DEDUP_THRESHOLD) -> list[tuple[Path, Path]]:
    """Consecutive pairs of frames that are visually near-identical.

    Mean absolute per-pixel difference of 16x16 grayscale thumbnails, compared
    pairwise in the given order. Advisory only — nothing is deleted.
    """
    pairs: list[tuple[Path, Path]] = []
    thumbs = [_gray_thumb(Path(p)) for p in paths]
    for (pa, ta), (pb, tb) in zip(zip(paths, thumbs), list(zip(paths, thumbs))[1:]):
        if not ta or not tb or len(ta) != len(tb):
            continue
        delta = sum(abs(x - y) for x, y in zip(ta, tb)) / len(ta)
        if delta <= threshold:
            pairs.append((Path(pa), Path(pb)))
    return pairs
```

- [ ] **Step 5: Run the suite** — `.venv/bin/python -m pytest -q` → ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/frames.py tests/test_frames.py tests/conftest.py
git commit -m "feat(frames): scene-change detection + near-duplicate helpers (raided from claude-video)"
```

---

### Task 5: `ingest.py propose-frames` subcommand

**Files:**
- Modify: `ingest.py`
- Create: `tests/test_ingest_propose_frames.py`

- [ ] **Step 1: Write failing test**

```python
import json
from pathlib import Path

import pytest

import ingest


def _make_prepared_slug(tmp_path: Path, cut_clip: Path) -> Path:
    slug = tmp_path / "lib" / "sub" / "some-video"
    slug.mkdir(parents=True)
    source = slug / ".source.mp4"
    source.write_bytes(cut_clip.read_bytes())
    (slug / ".work-state.json").write_text(json.dumps({
        "url": "https://x", "title": "T", "channel": "C",
        "duration_seconds": 4, "subfolder": "sub",
        "source_video": str(source), "source_audio": str(slug / ".audio.mp3"),
    }))
    return slug


def test_propose_frames_prints_mmss_candidates(tmp_path, cut_clip, capsys):
    slug = _make_prepared_slug(tmp_path, cut_clip)
    rc = ingest.run(["propose-frames", str(slug)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "candidate frame timestamps" in out
    assert "00:0" in out  # cuts land within the first 4 seconds


def test_propose_frames_errors_when_source_missing(tmp_path, capsys):
    slug = tmp_path / "no-source"
    slug.mkdir()
    rc = ingest.run(["propose-frames", str(slug)])
    assert rc == 7
    assert "prepare" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_ingest_propose_frames.py -v` → FAIL (unknown command).

- [ ] **Step 3: Implement** — add to `ingest.py`:

```python
def _cmd_propose_frames(args: argparse.Namespace) -> int:
    slug_folder = Path(args.slug_folder).resolve()
    state_path = slug_folder / ".work-state.json"
    source = slug_folder / ".source.mp4"
    if not state_path.exists() or not source.exists():
        print(
            f"ERROR: no .source.mp4/.work-state.json in {slug_folder} — "
            "run prepare first (propose-frames only works before finalize)",
            file=sys.stderr,
        )
        return 7

    try:
        timestamps = frames.detect_scene_timestamps(video_path=source)
    except frames.FrameExtractError as e:
        print(f"ERROR: scene detection failed: {e}", file=sys.stderr)
        return 8

    print(f"{len(timestamps)} candidate frame timestamps (scene changes):")
    for t in timestamps:
        mm, ss = divmod(int(t), 60)
        print(f"  {mm:02d}:{ss:02d}")
    print(
        "\nThese are candidates only — cross-reference the transcript (deictic cues"
        ' like "as you can see" / "look here") and prefer the END of animated'
        " whiteboard sections. Pick 8-15 and pass them to finalize --frames."
    )
    return 0
```

and register in `build_parser()`:

```python
    pf = sub.add_parser("propose-frames", help="print scene-change candidate timestamps for a prepared slug")
    pf.add_argument("slug_folder")
    pf.set_defaults(func=_cmd_propose_frames)
```

- [ ] **Step 4: Run the suite** — ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest.py tests/test_ingest_propose_frames.py
git commit -m "feat(ingest): propose-frames subcommand — scene-change candidate timestamps"
```

---

### Task 6: Near-duplicate warning in `finalize`

**Files:**
- Modify: `ingest.py` (`_cmd_finalize`)
- Modify: `tests/test_ingest_finalize.py`

- [ ] **Step 1: Add failing test** (append; reuse existing finalize-test setup helpers in that file, adapting to whatever fixture pattern it already uses — the key assertions):

```python
def test_finalize_warns_on_near_identical_frames(tmp_path, static_clip, capsys, mocker):
    # build a prepared slug whose source is a static clip, then finalize with
    # two timestamps → identical frames → warning (frames still written).
    slug = _make_prepared_slug(tmp_path, static_clip)  # same helper as prepare tests
    rc = ingest.run([
        "finalize", str(slug), "--frames", "00:00,00:02",
        "--library", str(tmp_path / "lib"),
        "--claude-md", str(tmp_path / "CLAUDE.md"),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "near-identical" in out
    assert len(list((slug / "frames").glob("*.jpg"))) == 2  # warning only, nothing dropped
```

(Adapt `_make_prepared_slug` from Task 5's test or the existing finalize test setup — the file already builds prepared slugs for its other cases; follow its local convention. `--claude-md` needs a seed file: `(tmp_path / "CLAUDE.md").write_text("# x\n\n## Library\n")` if the existing tests don't already do this.)

- [ ] **Step 2: Run to verify failure** — FAIL (no warning printed).

- [ ] **Step 3: Implement** — in `_cmd_finalize`, right after the `frames.extract_frames(...)` call succeeds:

```python
        written = sorted((slug_folder / "frames").glob("*.jpg"))
        for a, b in frames.near_duplicate_pairs(written):
            print(f"WARNING: near-identical frames: {a.name} and {b.name} — consider replacing one")
```

- [ ] **Step 4: Run the suite** — ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest.py tests/test_ingest_finalize.py
git commit -m "feat(ingest): warn when chosen frames are near-identical"
```

---

### Task 7: CLAUDE.md ingestion guidance (deictic cues + propose-frames)

**Files:**
- Modify: `CLAUDE.md` ("How to ingest new content", step 5)

- [ ] **Step 1: Edit step 5** to read:

```markdown
5. **Pick 8–15 frame timestamps** that capture the most important visuals —
   whiteboards, diagrams, key text overlays. Two inputs help:
   run `.venv/bin/python ingest.py propose-frames <slug_folder>` for
   scene-change candidates, and scan the transcript for deictic cues
   ("as you can see", "look here", "notice this") — moments the speaker
   points at something on screen that scene detection may miss.
   Animated whiteboards build up over time, so target the *end* of each
   animated section, not the middle. Frames are auto-capped at 1600px to
   stay under Anthropic's many-image dimension limit.
```

- [ ] **Step 2: Sanity check** — `lib/index.py` regenerate only rewrites the `## Library` section; confirm the edit sits above it and run `.venv/bin/python -m pytest tests/test_index.py -q` → PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): frame-picking guidance — propose-frames + deictic cues"
```

---

### Task 8: `skills/watch-worth-it/scripts/triage.py`

**Files:**
- Create: `skills/watch-worth-it/scripts/triage.py`
- Create: `tests/test_triage.py`
- Create: `tests/fixtures/rolling_dupes.vtt`

- [ ] **Step 1: Create the VTT fixture** `tests/fixtures/rolling_dupes.vtt`:

```
WEBVTT

00:00:00.000 --> 00:00:02.000
Hello and welcome

00:00:02.000 --> 00:00:04.000
Hello and welcome

00:00:02.000 --> 00:00:04.000
Hello and welcome to the channel

00:00:04.000 --> 00:00:07.500
<c>Today</c> we cover pricing
```

- [ ] **Step 2: Write failing tests** `tests/test_triage.py`:

```python
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

TRIAGE_PATH = Path(__file__).parent.parent / "skills" / "watch-worth-it" / "scripts" / "triage.py"
VTT_FIXTURE = Path(__file__).parent / "fixtures" / "rolling_dupes.vtt"

spec = importlib.util.spec_from_file_location("triage", TRIAGE_PATH)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


def test_parse_vtt_collapses_rolling_duplicates():
    segments = triage.parse_vtt(str(VTT_FIXTURE))
    texts = [s["text"] for s in segments]
    assert texts == ["Hello and welcome to the channel", "Today we cover pricing"]
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 4.0


def test_format_transcript_timestamps():
    segs = [{"start": 65.0, "end": 70.0, "text": "Step one."}]
    assert triage.format_transcript(segs) == "[01:05] Step one."


def test_is_safe_source():
    assert triage.is_safe_source("https://youtu.be/abc")
    assert not triage.is_safe_source("--exec=evil")
    assert not triage.is_safe_source("ftp://x/y")


def test_fetch_captions_argv(tmp_path, mocker):
    run_mock = mocker.patch.object(
        triage.subprocess, "run", return_value=MagicMock(returncode=0)
    )
    triage.fetch_captions("https://youtu.be/abc", tmp_path)
    cmd = run_mock.call_args.args[0]
    assert cmd[0] == "yt-dlp"
    assert "--skip-download" in cmd
    assert "--write-subs" in cmd and "--write-auto-subs" in cmd
    assert cmd[-2:] == ["--", "https://youtu.be/abc"]


def test_download_lowres_argv(tmp_path, mocker):
    (tmp_path / "video.mp4").touch()
    run_mock = mocker.patch.object(
        triage.subprocess, "run", return_value=MagicMock(returncode=0)
    )
    triage.download_lowres("https://youtu.be/abc", tmp_path)
    cmd = run_mock.call_args.args[0]
    fmt = cmd[cmd.index("-f") + 1]
    assert "height<=480" in fmt
    assert cmd[-2:] == ["--", "https://youtu.be/abc"]


def test_pick_frame_timestamps_even_samples():
    # 10 candidates, want 4 → first and last always kept
    picked = triage.pick_frame_timestamps(list(range(10)), 4, duration=100.0)
    assert picked[0] == 0 and picked[-1] == 9 and len(picked) == 4


def test_pick_frame_timestamps_uniform_fallback():
    # no scene candidates → uniform spread across duration
    picked = triage.pick_frame_timestamps([], 4, duration=100.0)
    assert len(picked) == 4
    assert picked[0] >= 0 and picked[-1] <= 100.0


def test_extract_triage_frames(tmp_path, cut_clip):
    out = triage.extract_triage_frames(str(cut_clip), tmp_path, [0.5, 1.5, 2.5])
    assert len(out) == 3
    assert all(Path(p).exists() for _, p in out)
    assert out[0][0] == 0.5


def test_build_report_sections(tmp_path):
    info = {"title": "T", "uploader": "C", "duration": 90, "webpage_url": "https://u", "view_count": 5}
    segs = [{"start": 0.0, "end": 2.0, "text": "Hi."}]
    report = triage.build_report(info, segs, "captions", [(1.0, "/tmp/f.jpg")], tmp_path)
    assert "Title:    T" in report
    assert "Duration: 01:30" in report
    assert "[00:00] Hi." in report
    assert "t=00:01 /tmp/f.jpg" in report
    assert f"work_dir={tmp_path}" in report
```

- [ ] **Step 3: Run to verify failure** — `.venv/bin/python -m pytest tests/test_triage.py -v` → FAIL (file missing).

- [ ] **Step 4: Implement `skills/watch-worth-it/scripts/triage.py`** (pure stdlib):

```python
#!/usr/bin/env python3
"""watch-worth-it triage: is this video worth a full VideoSkill library ingest?

Captions-first — fetches metadata + native captions with NO video download.
`--frames N` optionally downloads a 480p copy and extracts scene-change frames.

Pure stdlib; needs only yt-dlp and ffmpeg on PATH (no venv, no API keys).

VTT parsing, rolling-duplicate dedupe, and scene detection adapted from
bradautomates/claude-video (MIT, https://github.com/bradautomates/claude-video).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

TS_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")
SHOWINFO_TS_RE = re.compile(r"pts_time:([0-9.]+)")
SCENE_THRESHOLD = 0.20
FRAME_WIDTH = 512


# --- transcript ---------------------------------------------------------------

def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(path: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    segments: list[dict] = []
    i = 0
    while i < len(lines):
        match = TS_RE.match(lines[i])
        if not match:
            i += 1
            continue
        start = _to_seconds(*match.groups()[:4])
        end = _to_seconds(*match.groups()[4:])
        i += 1
        cue_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            cleaned = TAG_RE.sub("", lines[i]).strip()
            if cleaned:
                cue_lines.append(cleaned)
            i += 1
        cue_text = " ".join(cue_lines).strip()
        if cue_text:
            segments.append({"start": round(start, 2), "end": round(end, 2), "text": cue_text})
        i += 1
    return _dedupe(segments)


def _dedupe(segments: list[dict]) -> list[dict]:
    """Collapse rolling duplicates common in YouTube auto-subs."""
    out: list[dict] = []
    for seg in segments:
        if out and seg["text"] == out[-1]["text"]:
            out[-1]["end"] = seg["end"]
            continue
        if out and seg["text"].startswith(out[-1]["text"] + " "):
            out[-1]["text"] = seg["text"]
            out[-1]["end"] = seg["end"]
            continue
        out.append(seg)
    return out


def _mmss(seconds: float) -> str:
    mm, ss = divmod(int(seconds), 60)
    return f"{mm:02d}:{ss:02d}"


def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{_mmss(seg['start'])}] {seg['text']}" for seg in segments)


# --- yt-dlp -------------------------------------------------------------------

def is_safe_source(source: str) -> bool:
    if source.startswith("-"):
        return False
    parsed = urlparse(source)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _sub_flags() -> list[str]:
    return [
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "en.*",
        "--sub-format", "vtt", "--convert-subs", "vtt",
    ]


def fetch_captions(url: str, work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp", "--skip-download", "--write-info-json",
        *_sub_flags(),
        "--no-playlist", "--ignore-errors",
        "-o", str(work_dir / "video.%(ext)s"),
        "--", url,
    ]
    subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)


def download_lowres(url: str, work_dir: Path) -> Path | None:
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp", "-N", "8",
        "-f", "bv*[height<=480]+ba/b[height<=480]/bv+ba/b",
        "--merge-output-format", "mp4",
        "--no-playlist", "--ignore-errors",
        "-o", str(work_dir / "video.%(ext)s"),
        "--", url,
    ]
    subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
    for candidate in sorted(work_dir.glob("video.*")):
        if candidate.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
            return candidate
    return None


def pick_subtitle(work_dir: Path) -> Path | None:
    candidates = sorted(work_dir.glob("video*.vtt"))
    if not candidates:
        return None
    preferred = [
        c for c in candidates
        if any(m in c.name for m in (".en.", ".en-US.", ".en-GB.", ".en-orig."))
    ]
    return preferred[0] if preferred else candidates[0]


def read_info(work_dir: Path, url: str) -> dict:
    info_path = work_dir / "video.info.json"
    if not info_path.exists():
        return {"webpage_url": url}
    try:
        raw = json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return {"webpage_url": url}
    return {
        "title": raw.get("title"),
        "uploader": raw.get("uploader") or raw.get("channel"),
        "duration": raw.get("duration"),
        "upload_date": raw.get("upload_date"),
        "view_count": raw.get("view_count"),
        "webpage_url": raw.get("webpage_url") or url,
    }


# --- frames -------------------------------------------------------------------

def scene_timestamps(video_path: str, threshold: float = SCENE_THRESHOLD) -> list[float]:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-i", str(Path(video_path).resolve()),
        "-vf", f"select='gt(scene\\,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [round(float(m.group(1)), 2) for m in SHOWINFO_TS_RE.finditer(result.stderr)]


def probe_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
         str(Path(video_path).resolve())],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return 0.0
    fmt = json.loads(result.stdout or "{}").get("format", {})
    return float(fmt.get("duration") or 0.0)


def pick_frame_timestamps(candidates: list[float], n: int, duration: float) -> list[float]:
    """Even-sample n from scene candidates (first+last kept); uniform when none."""
    if not candidates:
        if duration <= 0 or n <= 0:
            return []
        step = duration / (n + 1)
        return [round(step * (i + 1), 2) for i in range(n)]
    if n >= len(candidates):
        return list(candidates)
    idx = [round(i * (len(candidates) - 1) / (n - 1)) for i in range(n)]
    return [candidates[i] for i in dict.fromkeys(idx)]


def extract_triage_frames(video_path: str, out_dir: Path, timestamps: list[float]) -> list[tuple[float, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[tuple[float, str]] = []
    for t in timestamps:
        path = out_dir / f"frame_{len(out):03d}.jpg"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{t:.3f}",
            "-i", str(Path(video_path).resolve()),
            "-frames:v", "1",
            "-vf", f"scale='min({FRAME_WIDTH},iw)':-2",
            "-q:v", "4",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and path.exists():
            out.append((t, str(path)))
    return out


# --- report -------------------------------------------------------------------

def _repo_root() -> Path | None:
    """VideoSkill repo root, resolved through any install symlink."""
    root = Path(__file__).resolve().parents[3]
    return root if (root / "library").exists() else None


def build_report(info: dict, segments: list[dict], transcript_source: str,
                 frames: list[tuple[float, str]], work_dir: Path) -> str:
    lines = ["== watch-worth-it report =="]
    lines.append(f"Title:    {info.get('title') or '?'}")
    lines.append(f"Channel:  {info.get('uploader') or '?'}")
    duration = info.get("duration")
    lines.append(f"Duration: {_mmss(duration) if duration else '?'}")
    if info.get("upload_date"):
        lines.append(f"Uploaded: {info['upload_date']}")
    if info.get("view_count") is not None:
        lines.append(f"Views:    {info['view_count']}")
    lines.append(f"URL:      {info.get('webpage_url') or '?'}")
    lines.append("")

    if segments:
        words = sum(len(s["text"].split()) for s in segments)
        wpm = int(words / (duration / 60)) if duration else 0
        lines.append(f"Transcript source: {transcript_source}")
        lines.append(f"Words: {words}" + (f" (~{wpm} wpm)" if wpm else ""))
    else:
        lines.append("Transcript: NONE AVAILABLE (no captions). Options: re-run with")
        lines.append("  --frames 6 for a visual-only triage, or do a full `ingest.py prepare`")
        lines.append("  (local Parakeet transcription) if the metadata already looks promising.")

    root = _repo_root()
    if root:
        lines.append("")
        lines.append(f"library_index={root / 'CLAUDE.md'}")
        lines.append(f"library_root={root / 'library'}")

    if frames:
        lines.append("")
        lines.append("Frames:")
        for t, path in frames:
            lines.append(f"t={_mmss(t)} {path}")

    if segments:
        lines.append("")
        lines.append("Transcript:")
        lines.append(format_transcript(segments))

    lines.append("")
    lines.append(f"work_dir={work_dir}   (delete when done: rm -rf {work_dir})")
    return "\n".join(lines)


# --- main ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage.py")
    parser.add_argument("url")
    parser.add_argument("--frames", type=int, default=0, metavar="N",
                        help="also download 480p video and extract N scene frames")
    parser.add_argument("--work-dir", default=None)
    args = parser.parse_args(argv)

    if not is_safe_source(args.url):
        print(f"ERROR: refusing suspicious source: {args.url!r}", file=sys.stderr)
        return 2

    work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="watch-worth-it-"))
    fetch_captions(args.url, work_dir)
    info = read_info(work_dir, args.url)

    subtitle = pick_subtitle(work_dir)
    segments = parse_vtt(str(subtitle)) if subtitle else []
    transcript_source = "captions (en)" if subtitle else "none"

    frames: list[tuple[float, str]] = []
    if args.frames > 0:
        video = download_lowres(args.url, work_dir)
        if video is None:
            print("WARNING: video download failed — report is transcript-only", file=sys.stderr)
        else:
            duration = probe_duration(str(video)) or float(info.get("duration") or 0)
            picks = pick_frame_timestamps(scene_timestamps(str(video)), args.frames, duration)
            frames = extract_triage_frames(str(video), work_dir / "frames", picks)

    print(build_report(info, segments, transcript_source, frames, work_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the suite** — `.venv/bin/python -m pytest tests/test_triage.py -v` then full `-q` → ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/watch-worth-it/scripts/triage.py tests/test_triage.py tests/fixtures/rolling_dupes.vtt
git commit -m "feat(watch-worth-it): stdlib triage script — captions-first, optional 480p frame pass"
```

---

### Task 9: `skills/watch-worth-it/SKILL.md`

**Files:**
- Create: `skills/watch-worth-it/SKILL.md`

- [ ] **Step 1: Write SKILL.md**:

````markdown
---
name: watch-worth-it
version: "0.1.0"
description: Triage a video URL before ingesting it into the VideoSkill library. Fetches metadata + captions with no video download (optionally a few low-res frames), then judges whether the video is worth a full ingest — INGEST / PARTIAL / SKIP.
argument-hint: "<video-url> [--frames N]"
allowed-tools: Bash, Read
license: MIT
user-invocable: true
---

# /watch-worth-it

Decide cheaply whether a video deserves a full VideoSkill library ingest
(download → local Parakeet transcription → summary/extraction/frames), before
spending the time. Works in any agent host (Claude Code, Codex, Hermes, …).

## Resolve SKILL_DIR (before any command)

Set `SKILL_DIR` to the absolute directory containing THIS SKILL.md (your
harness reported the path when you read it). The script is always at
`SKILL_DIR/scripts/triage.py`, in every install layout — including symlinked
installs. Guard once:

```bash
SKILL_DIR="<absolute dir of the SKILL.md you just read>"
[ -f "$SKILL_DIR/scripts/triage.py" ] || echo "ERROR: triage.py not found under $SKILL_DIR"
```

## Step 1 — run the triage script

```bash
python3 "$SKILL_DIR/scripts/triage.py" "<url>"
```

Needs only `yt-dlp` and `ffmpeg` on PATH — no venv, no API keys. Default is
captions-only (no video download, a few seconds). Add `--frames 6` to also
pull a 480p copy and extract ~6 scene-change frames (use when the creator is
whiteboard/diagram-heavy and visuals decide the value). If frames were
produced, Read each listed path — they render as images.

## Step 2 — check overlap with the existing library

The report prints `library_index=` and `library_root=` lines when the skill
lives inside a VideoSkill repo. Read the index and grep for topic overlap:

```bash
grep -il "<topic>" "<library_root>"/*/*/summary.md "<library_root>"/*/*/extracted.md
```

## Step 3 — judge

Score the transcript against four dials:

- **Framework density** — named models, numbered steps, templates, scripts.
  High density → high extract value.
- **Novelty vs library** — does the index/grep show we already cover this?
  Same creator saying the same thing again → SKIP.
- **Specificity vs fluff** — sponsor reads, recycled intros, "smash that
  like button", vague motivation → discount heavily.
- **Visual payload** — does the speaker keep referencing things on screen
  ("as you can see", "this diagram")? That raises ingest value (frames) and
  is a reason to re-run with `--frames`.

## Step 4 — verdict

Answer with exactly one of:

- **INGEST** — worth it. Give the suggested subfolder and the ready-to-run
  command: `.venv/bin/python ingest.py prepare "<url>" --to <subfolder>`
- **PARTIAL** — only sections are valuable. List the `mm:ss–mm:ss` ranges
  and what each contains; ingest is still all-or-nothing today, so say
  whether the good sections justify a full ingest anyway.
- **SKIP** — one line on why (overlap, fluff, too thin).

Always show 2–4 bullet reasons with timestamps. Never paste the full
transcript back at the user.

## Step 5 — clean up

The report's last line prints `work_dir=…`. Unless the user wants follow-ups
(e.g. an ingest next, which re-downloads anyway), `rm -rf` it.

## No captions?

The report says so explicitly. Options, in order: re-run with `--frames 6`
(visual-only triage), or — if metadata + your knowledge of the creator already
look promising — recommend going straight to a full `prepare` (local Parakeet
transcription doesn't need captions).
````

- [ ] **Step 2: Commit**

```bash
git add skills/watch-worth-it/SKILL.md
git commit -m "feat(watch-worth-it): SKILL.md — cross-agent triage contract and INGEST/PARTIAL/SKIP rubric"
```

---

### Task 10: README section + local installs

**Files:**
- Modify: `README.md`
- Create (outside repo): symlinks in `~/.claude/skills/` and `~/.codex/skills/`

- [ ] **Step 1: README** — add a section after the ingestion docs:

```markdown
## /watch-worth-it — triage before you ingest

`skills/watch-worth-it/` is a self-contained, host-agnostic agent skill that
answers "is this video worth a full ingest?" using metadata + captions only
(no video download; optional `--frames N` low-res visual pass). It needs just
`yt-dlp` and `ffmpeg` — no venv, no API keys.

Install by symlink into whichever agents you use:

​```bash
ln -s "$(pwd)/skills/watch-worth-it" ~/.claude/skills/watch-worth-it   # Claude Code
ln -s "$(pwd)/skills/watch-worth-it" ~/.codex/skills/watch-worth-it    # Codex
# Hermes: symlink the same folder into its skills directory
​```

Then: `/watch-worth-it <url>` → INGEST / PARTIAL / SKIP with reasons, and a
ready-to-run `ingest.py prepare` command when it's a yes.
```

(Strip the zero-width escapes around the inner code fence when writing.)

- [ ] **Step 2: Create the symlinks on this machine**

```bash
mkdir -p ~/.claude/skills ~/.codex/skills
ln -sfn "/Users/simonsmyth/Projects/VideoSkill/skills/watch-worth-it" ~/.claude/skills/watch-worth-it
ln -sfn "/Users/simonsmyth/Projects/VideoSkill/skills/watch-worth-it" ~/.codex/skills/watch-worth-it
```

(Hermes: ask Simon for its skills dir or leave for him — note it in the final summary.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(README): /watch-worth-it triage skill + cross-agent install"
```

---

### Task 11: End-to-end verification (no commit)

- [ ] **Step 1:** `.venv/bin/pip install parakeet-mlx` — expect clean install (MLX cp314 arm64 wheel).
- [ ] **Step 2:** `.venv/bin/python -m pytest -q` → ALL PASS.
- [ ] **Step 3:** Real ingest into a throwaway library: pick the URL from `library/daniel-priestley/why-you-must-build-a-youtube-channel/meta.json`, then
  `.venv/bin/python ingest.py prepare "<url>" --to smoke --library /private/tmp/.../scratchpad/smoke-library` — first run downloads the model (report progress). Diff the new `transcript.md` against the Groq-era one for sanity (spot-check 3 timestamps + punctuation quality).
- [ ] **Step 4:** `propose-frames` on the prepared slug → sensible candidate list.
- [ ] **Step 5:** `python3 skills/watch-worth-it/scripts/triage.py "<same url>"` → report with captions; then once with `--frames 4`.
- [ ] **Step 6:** Clean up the throwaway library dir. Summarise transcript-quality comparison + timings for Simon.
