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
