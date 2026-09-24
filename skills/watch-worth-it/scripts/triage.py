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
import shutil
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


def _trim_overlap(prev_text: str, text: str) -> str:
    """Drop the longest run of words that ends prev_text AND starts text.

    YouTube auto-subs repeat the tail of one cue as the head of the next
    ("…almost built" / "almost built flawlessly…"); this strips the repeat.
    """
    prev_words = prev_text.split()
    words = text.split()
    for k in range(min(len(prev_words), len(words)), 0, -1):
        if prev_words[-k:] == words[:k]:
            return " ".join(words[k:])
    return text


def _dedupe(segments: list[dict]) -> list[dict]:
    """Collapse rolling duplicates common in YouTube auto-subs."""
    out: list[dict] = []
    for seg in segments:
        if out:
            if seg["text"] == out[-1]["text"]:
                out[-1]["end"] = seg["end"]
                continue
            if seg["text"].startswith(out[-1]["text"] + " "):
                out[-1]["text"] = seg["text"]
                out[-1]["end"] = seg["end"]
                continue
            trimmed = _trim_overlap(out[-1]["text"], seg["text"])
            if not trimmed:
                out[-1]["end"] = seg["end"]
                continue
            if trimmed != seg["text"]:
                seg = {**seg, "text": trimmed}
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
        lines.append(f"library_index={root / 'library-index.md'}")
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

def require_binaries() -> list[str]:
    """Names of required binaries missing from PATH (empty = ready)."""
    return [name for name in ("yt-dlp", "ffmpeg", "ffprobe") if shutil.which(name) is None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage.py")
    parser.add_argument("url")
    parser.add_argument("--frames", type=int, default=0, metavar="N",
                        help="also download 480p video and extract N scene frames")
    parser.add_argument("--work-dir", default=None)
    args = parser.parse_args(argv)

    missing = require_binaries()
    if missing:
        print(f"SETUP NEEDED: missing on PATH: {', '.join(missing)}", file=sys.stderr)
        print("Install (ffprobe ships with ffmpeg):", file=sys.stderr)
        print("  macOS:          brew install ffmpeg yt-dlp", file=sys.stderr)
        print("  Debian/Ubuntu:  sudo apt install ffmpeg && pipx install yt-dlp", file=sys.stderr)
        print("  Windows:        winget install Gyan.FFmpeg yt-dlp.yt-dlp", file=sys.stderr)
        return 3

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
