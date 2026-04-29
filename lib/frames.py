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
