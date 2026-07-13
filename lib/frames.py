import re
import subprocess
from pathlib import Path
from typing import Sequence


class FrameExtractError(RuntimeError):
    pass


SCENE_THRESHOLD = 0.20
DEDUP_THUMB = 16
DEDUP_THRESHOLD = 2.0
_SHOWINFO_TS_RE = re.compile(r"pts_time:([0-9.]+)")


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
    for raw in dict.fromkeys(timestamps):
        seconds = parse_timestamp(raw)
        out_path = out_dir / format_frame_filename(seconds)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seconds),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            # Cap longest side at 1600px so frames stay under Anthropic's 2000px
            # many-image dimension limit when reviewed in batches.
            "-vf", "scale='min(1600,iw)':'min(1600,ih)':force_original_aspect_ratio=decrease",
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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise FrameExtractError("ffmpeg not found on PATH") from e
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
    try:
        result = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError:
        return b""  # fail-open: no ffmpeg → treat as not-a-duplicate
    if result.returncode != 0 or len(result.stdout) != DEDUP_THUMB * DEDUP_THUMB:
        return b""  # fail-open: caller treats as not-a-duplicate
    return result.stdout


def near_duplicate_pairs(paths: Sequence[Path], threshold: float = DEDUP_THRESHOLD) -> list[tuple[Path, Path]]:
    """Consecutive pairs of frames that are visually near-identical.

    Mean absolute per-pixel difference of 16x16 grayscale thumbnails, compared
    pairwise in the given order. Advisory only — nothing is deleted.
    """
    thumbs = [_gray_thumb(Path(p)) for p in paths]
    pairs: list[tuple[Path, Path]] = []
    for i in range(1, len(paths)):
        ta, tb = thumbs[i - 1], thumbs[i]
        if not ta or not tb or len(ta) != len(tb):
            continue
        delta = sum(abs(x - y) for x, y in zip(ta, tb)) / len(ta)
        if delta <= threshold:
            pairs.append((Path(paths[i - 1]), Path(paths[i])))
    return pairs
