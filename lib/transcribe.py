import subprocess
from pathlib import Path
from typing import Iterable, NamedTuple

from groq import Groq


class TranscribeError(RuntimeError):
    pass


class Segment(NamedTuple):
    start: float
    end: float
    text: str


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
    client = Groq()
    try:
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                file=(audio_path.name, f.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
    except Exception as e:
        raise TranscribeError(f"Groq transcription failed: {e}") from e
    return [_segment_from_raw(s) for s in response.segments]


def _segment_from_raw(raw) -> Segment:
    """Normalise a Groq response segment (dict or object) into a Segment."""
    if isinstance(raw, dict):
        return Segment(start=float(raw["start"]), end=float(raw["end"]), text=str(raw["text"]))
    return Segment(start=float(raw.start), end=float(raw.end), text=str(raw.text))


def format_transcript(segments: Iterable) -> str:
    lines = []
    for seg in segments:
        start = int(seg.start)
        mm, ss = divmod(start, 60)
        text = (seg.text or "").strip()
        # mm:ss — visual alignment breaks (not value) for videos > 99 min; fine for our use case.
        lines.append(f"[{mm:02d}:{ss:02d}] {text}")
    return "\n".join(lines) + "\n"
