import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib import download

FIXTURE = Path(__file__).parent / "fixtures" / "yt_dlp_info.json"


def test_download_invokes_yt_dlp_with_expected_args(tmp_path, mocker):
    fake_info = json.loads(FIXTURE.read_text())
    info_path = tmp_path / "video.info.json"
    info_path.write_text(json.dumps(fake_info))
    video_path = tmp_path / "video.mp4"
    video_path.touch()

    def fake_run(cmd, *args, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    run_mock = mocker.patch("lib.download.subprocess.run", side_effect=fake_run)

    result = download.download_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        out_dir=tmp_path,
        out_basename="video",
    )

    cmd = run_mock.call_args.args[0]
    assert cmd[0] == "yt-dlp"
    assert "--no-playlist" in cmd
    assert "--write-info-json" in cmd
    assert "--merge-output-format" in cmd and "mp4" in cmd
    assert "https://youtu.be/dQw4w9WgXcQ" in cmd

    assert result["video_path"] == video_path
    assert result["info"]["title"] == "Key Person of Influence — Daniel Priestly"
    assert result["info"]["channel"] == "Daniel Priestly"
    assert result["info"]["duration"] == 1834


def test_download_raises_on_yt_dlp_failure(tmp_path, mocker):
    mocker.patch(
        "lib.download.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "yt-dlp", stderr="ERROR: video unavailable"),
    )
    with pytest.raises(download.DownloadError, match="video unavailable"):
        download.download_video(url="https://x", out_dir=tmp_path, out_basename="v")
