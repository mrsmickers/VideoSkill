import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import ingest as ingest_cli


def test_prepare_downloads_transcribes_writes_transcript(tmp_path, mocker, capsys):
    library = tmp_path / "library"

    fake_info = {
        "title": "KPOI Talk",
        "channel": "Daniel Priestly",
        "duration": 1800,
        "webpage_url": "https://youtu.be/abc",
    }

    def fake_download(*, url, out_dir, out_basename):
        video = out_dir / f"{out_basename}.mp4"
        video.write_bytes(b"fake-mp4")
        info_path = out_dir / f"{out_basename}.info.json"
        info_path.write_text(json.dumps(fake_info))
        return {"video_path": video, "info_path": info_path, "info": fake_info}

    mocker.patch("ingest.download.download_video", side_effect=fake_download)
    mocker.patch("ingest.transcribe.extract_audio", side_effect=lambda *, video_path, audio_path: audio_path.write_bytes(b"fake-mp3"))
    mocker.patch(
        "ingest.transcribe.transcribe_audio",
        return_value=[
            SimpleNamespace(start=0.0, end=2.0, text="Hello."),
            SimpleNamespace(start=120.0, end=125.0, text="Now the next bit."),
        ],
    )

    rc = ingest_cli.run(["prepare", "https://youtu.be/abc", "--to", "daniel-priestly", "--library", str(library)])

    assert rc == 0
    slug_folder = library / "daniel-priestly" / "kpoi-talk"
    assert (slug_folder / "transcript.md").exists()
    assert (slug_folder / ".source.mp4").exists()
    assert (slug_folder / ".audio.mp3").exists()

    transcript = (slug_folder / "transcript.md").read_text()
    assert "[00:00] Hello." in transcript
    assert "[02:00] Now the next bit." in transcript

    state = json.loads((slug_folder / ".work-state.json").read_text())
    assert state["url"] == "https://youtu.be/abc"
    assert state["title"] == "KPOI Talk"
    assert state["channel"] == "Daniel Priestly"

    out = capsys.readouterr().out
    assert f"slug_folder={slug_folder}" in out


def test_prepare_skips_when_already_ingested(tmp_path, mocker, capsys):
    library = tmp_path / "library"
    slug = library / "daniel-priestly" / "kpoi-talk"
    slug.mkdir(parents=True)
    (slug / "meta.json").write_text(json.dumps({"url": "https://youtu.be/abc", "title": "KPOI Talk"}))

    download_mock = mocker.patch("ingest.download.download_video")

    rc = ingest_cli.run(["prepare", "https://youtu.be/abc", "--to", "daniel-priestly", "--library", str(library)])

    assert rc == 0
    download_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "already ingested" in out.lower()
