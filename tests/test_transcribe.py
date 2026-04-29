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
