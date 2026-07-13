import json
from pathlib import Path

import ingest


def _make_prepared_slug(tmp_path: Path, clip: Path) -> Path:
    slug = tmp_path / "lib" / "sub" / "some-video"
    slug.mkdir(parents=True)
    source = slug / ".source.mp4"
    source.write_bytes(clip.read_bytes())
    (slug / ".work-state.json").write_text(json.dumps({
        "url": "https://x", "title": "T", "channel": "C",
        "duration_seconds": 4, "subfolder": "sub",
        "source_video": str(source), "source_audio": str(slug / ".audio.mp3"),
    }))
    return slug


def test_propose_frames_prints_mmss_candidates(tmp_path, cut_clip, capsys):
    slug = _make_prepared_slug(tmp_path, cut_clip)
    rc = ingest.run(["propose-frames", str(slug)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "candidate frame timestamps" in out
    assert "00:0" in out  # cuts land within the first 4 seconds


def test_propose_frames_errors_when_source_missing(tmp_path, capsys):
    slug = tmp_path / "no-source"
    slug.mkdir()
    rc = ingest.run(["propose-frames", str(slug)])
    assert rc == 7
    assert "prepare" in capsys.readouterr().err
