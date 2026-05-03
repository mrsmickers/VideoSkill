import random
import subprocess
import time
from pathlib import Path
from typing import Iterable, NamedTuple

from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    Groq,
    RateLimitError,
)


class TranscribeError(RuntimeError):
    pass


class Segment(NamedTuple):
    start: float
    end: float
    text: str


_RETRY_EXCEPTIONS = (RateLimitError, APIConnectionError, APITimeoutError)
_MAX_ATTEMPTS = 5
_BASE_DELAY_SECONDS = 1.0
_MAX_DELAY_SECONDS = 60.0


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
            audio_bytes = f.read()
        response = _call_with_retry(
            lambda: client.audio.transcriptions.create(
                file=(audio_path.name, audio_bytes),
                model="whisper-large-v3",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        )
    except Exception as e:
        raise TranscribeError(f"Groq transcription failed: {e}") from e
    return [_segment_from_raw(s) for s in response.segments]


def _call_with_retry(func):
    """Run func() with retry on transient Groq errors (429, 5xx, network).
    Honours Retry-After when present; otherwise exponential backoff with jitter.
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return func()
        except _RETRY_EXCEPTIONS as e:
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(_compute_delay(e, attempt))
        except APIStatusError as e:
            # Retry only on server-side errors (5xx); client errors propagate.
            if attempt == _MAX_ATTEMPTS or getattr(e, "status_code", 0) < 500:
                raise
            time.sleep(_compute_delay(e, attempt))


def _compute_delay(exc: Exception, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(retry_after, _MAX_DELAY_SECONDS)
    delay = min(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), _MAX_DELAY_SECONDS)
    return delay + random.uniform(0, delay * 0.25)  # jitter so parallel callers don't sync


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


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
