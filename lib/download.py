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
