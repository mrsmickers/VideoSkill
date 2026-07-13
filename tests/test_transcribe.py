import subprocess
import sys
from pathlib import Path
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
