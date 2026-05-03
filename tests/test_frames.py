from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib import frames


def test_parse_timestamp_handles_mm_ss():
    assert frames.parse_timestamp("00:30") == 30
    assert frames.parse_timestamp("02:15") == 135
    assert frames.parse_timestamp("00:00") == 0


def test_parse_timestamp_handles_h_mm_ss():
    assert frames.parse_timestamp("1:02:15") == 3735


def test_parse_timestamp_rejects_garbage():
    with pytest.raises(ValueError):
        frames.parse_timestamp("not-a-time")


def test_format_frame_filename_zero_pads():
    assert frames.format_frame_filename(30) == "00-00-30.jpg"
    assert frames.format_frame_filename(3735) == "01-02-15.jpg"


def test_extract_frames_invokes_ffmpeg_per_timestamp(tmp_path, mocker):
    video = tmp_path / "v.mp4"
    video.touch()
    out = tmp_path / "frames"

    run_mock = mocker.patch("lib.frames.subprocess.run", return_value=MagicMock(returncode=0))

    written = frames.extract_frames(
        video_path=video,
        timestamps=["00:30", "02:15"],
        out_dir=out,
    )

    assert run_mock.call_count == 2
    cmd = run_mock.call_args_list[0].args[0]
    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd
    assert "30" in cmd  # parsed seconds
    assert "-frames:v" in cmd and "1" in cmd
    assert "-q:v" in cmd and "2" in cmd
    # Frames must be capped under Anthropic's 2000px many-image limit.
    assert "-vf" in cmd
    vf_value = cmd[cmd.index("-vf") + 1]
    assert "1600" in vf_value
    assert "force_original_aspect_ratio=decrease" in vf_value
    assert str(out / "00-00-30.jpg") in cmd

    assert written == [out / "00-00-30.jpg", out / "00-02-15.jpg"]
    assert out.exists()
