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
    assert segments == [transcribe.Segment(start=0.0, end=1.0, text="Hi.")]


def test_transcribe_audio_handles_dict_segments_from_groq(tmp_path, mocker):
    """Real Groq SDK returns segments as dicts, not objects. Verify we normalise."""
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_response = SimpleNamespace(
        segments=[
            {"start": 0.0, "end": 2.5, "text": "Hello."},
            {"start": 2.5, "end": 5.0, "text": "World."},
        ]
    )
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_response
    mocker.patch("lib.transcribe.Groq", return_value=fake_client)

    segments = transcribe.transcribe_audio(audio_path=audio)

    assert segments == [
        transcribe.Segment(start=0.0, end=2.5, text="Hello."),
        transcribe.Segment(start=2.5, end=5.0, text="World."),
    ]


def test_extract_audio_raises_on_ffmpeg_failure(tmp_path, mocker):
    video = tmp_path / "v.mp4"
    video.touch()
    audio = tmp_path / ".audio.mp3"

    mocker.patch(
        "lib.transcribe.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "ffmpeg", stderr="ERROR: no such file"),
    )

    with pytest.raises(transcribe.TranscribeError, match="no such file"):
        transcribe.extract_audio(video_path=video, audio_path=audio)


def test_transcribe_audio_wraps_groq_errors(tmp_path, mocker):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = RuntimeError("groq exploded")
    mocker.patch("lib.transcribe.Groq", return_value=fake_client)

    with pytest.raises(transcribe.TranscribeError, match="groq exploded"):
        transcribe.transcribe_audio(audio_path=audio)


def test_transcribe_audio_retries_on_rate_limit(tmp_path, mocker):
    """A real Groq RateLimitError twice, then success — verify the retry."""
    from groq import RateLimitError

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    # RateLimitError requires a response object; use a MagicMock with no Retry-After
    # so the helper falls back to exponential backoff (which we mock to be instant).
    fake_http_resp = MagicMock()
    fake_http_resp.headers = {}
    rate_limit = RateLimitError(message="429", response=fake_http_resp, body=None)

    fake_response = SimpleNamespace(
        segments=[SimpleNamespace(start=0.0, end=1.0, text="Hi.")]
    )
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = [
        rate_limit, rate_limit, fake_response,
    ]
    mocker.patch("lib.transcribe.Groq", return_value=fake_client)
    sleep_mock = mocker.patch("lib.transcribe.time.sleep")

    segments = transcribe.transcribe_audio(audio_path=audio)

    assert fake_client.audio.transcriptions.create.call_count == 3
    assert sleep_mock.call_count == 2  # one sleep per retry, none after success
    assert segments == [transcribe.Segment(start=0.0, end=1.0, text="Hi.")]


def test_transcribe_audio_honours_retry_after_header(tmp_path, mocker):
    """If the rate-limit response includes Retry-After, sleep that long (capped)."""
    from groq import RateLimitError

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_http_resp = MagicMock()
    fake_http_resp.headers = {"Retry-After": "7"}
    rate_limit = RateLimitError(message="429", response=fake_http_resp, body=None)

    fake_response = SimpleNamespace(
        segments=[SimpleNamespace(start=0.0, end=1.0, text="Hi.")]
    )
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = [rate_limit, fake_response]
    mocker.patch("lib.transcribe.Groq", return_value=fake_client)
    sleep_mock = mocker.patch("lib.transcribe.time.sleep")

    transcribe.transcribe_audio(audio_path=audio)

    sleep_mock.assert_called_once_with(7.0)


def test_transcribe_audio_gives_up_after_max_attempts(tmp_path, mocker):
    """Persistent rate limiting eventually surfaces as TranscribeError."""
    from groq import RateLimitError

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_http_resp = MagicMock()
    fake_http_resp.headers = {}
    rate_limit = RateLimitError(message="429", response=fake_http_resp, body=None)

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = rate_limit
    mocker.patch("lib.transcribe.Groq", return_value=fake_client)
    mocker.patch("lib.transcribe.time.sleep")

    with pytest.raises(transcribe.TranscribeError, match="429"):
        transcribe.transcribe_audio(audio_path=audio)

    # Default max_attempts is 5
    assert fake_client.audio.transcriptions.create.call_count == 5
