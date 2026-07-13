import json
from pathlib import Path

import ingest as ingest_cli


def _seed_prepared_slug(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    slug = library / "daniel-priestly" / "kpoi-talk"
    slug.mkdir(parents=True)
    (slug / ".source.mp4").write_bytes(b"x")
    (slug / ".audio.mp3").write_bytes(b"x")
    (slug / "transcript.md").write_text("[00:00] hello\n")
    (slug / "summary.md").write_text("# KPOI Talk\nOverview...\n")
    (slug / "extracted.md").write_text("# Frameworks\n- 5 Ps\n")
    (slug / ".work-state.json").write_text(json.dumps({
        "url": "https://youtu.be/abc",
        "title": "KPOI Talk",
        "channel": "Daniel Priestly",
        "duration_seconds": 1800,
        "subfolder": "daniel-priestly",
        "source_video": str(slug / ".source.mp4"),
        "source_audio": str(slug / ".audio.mp3"),
    }))
    (tmp_path / "CLAUDE.md").write_text(
        "# Library\n\n<!-- BEGIN AUTO-INDEX -->\nold\n<!-- END AUTO-INDEX -->\n"
    )
    return slug


def test_finalize_extracts_frames_writes_meta_cleans_up(tmp_path, mocker):
    slug = _seed_prepared_slug(tmp_path)

    def fake_extract(*, video_path, timestamps, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for ts in timestamps:
            p = out_dir / f"frame-{ts.replace(':', '-')}.jpg"
            p.write_bytes(b"jpg")
            written.append(p)
        return written

    mocker.patch("ingest.frames.extract_frames", side_effect=fake_extract)

    rc = ingest_cli.run([
        "finalize",
        str(slug),
        "--frames", "00:30,02:15",
        "--claude-md", str(tmp_path / "CLAUDE.md"),
        "--library", str(tmp_path / "library"),
    ])
    assert rc == 0

    # meta.json written with right fields
    meta_data = json.loads((slug / "meta.json").read_text())
    assert meta_data["url"] == "https://youtu.be/abc"
    assert meta_data["title"] == "KPOI Talk"
    assert meta_data["channel"] == "Daniel Priestly"
    assert meta_data["duration_seconds"] == 1800

    # frames extracted
    assert (slug / "frames").exists()
    assert any(p.suffix == ".jpg" for p in (slug / "frames").iterdir())

    # cleanup happened
    assert not (slug / ".source.mp4").exists()
    assert not (slug / ".audio.mp3").exists()
    assert not (slug / ".work-state.json").exists()

    # CLAUDE.md regenerated
    claude_text = (tmp_path / "CLAUDE.md").read_text()
    assert "old" not in claude_text
    assert "kpoi-talk" in claude_text


def test_finalize_errors_when_state_missing(tmp_path):
    slug = tmp_path / "library" / "x" / "y"
    slug.mkdir(parents=True)
    rc = ingest_cli.run([
        "finalize", str(slug),
        "--claude-md", str(tmp_path / "CLAUDE.md"),
        "--library", str(tmp_path / "library"),
    ])
    assert rc == 5


def test_finalize_warns_on_near_identical_frames(tmp_path, static_clip, capsys):
    slug = _seed_prepared_slug(tmp_path)
    # real static-colour clip → two chosen timestamps give identical frames
    (slug / ".source.mp4").write_bytes(static_clip.read_bytes())

    rc = ingest_cli.run([
        "finalize",
        str(slug),
        "--frames", "00:00,00:02",
        "--claude-md", str(tmp_path / "CLAUDE.md"),
        "--library", str(tmp_path / "library"),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "near-identical" in out
    # warning only — nothing dropped
    assert len(list((slug / "frames").glob("*.jpg"))) == 2


def test_finalize_empty_frames_skips_extraction(tmp_path, mocker):
    slug = _seed_prepared_slug(tmp_path)

    extract_mock = mocker.patch("ingest.frames.extract_frames")

    rc = ingest_cli.run([
        "finalize",
        str(slug),
        "--frames", "",
        "--claude-md", str(tmp_path / "CLAUDE.md"),
        "--library", str(tmp_path / "library"),
    ])
    assert rc == 0

    # extract_frames was NOT called
    extract_mock.assert_not_called()

    # meta.json still written
    meta_data = json.loads((slug / "meta.json").read_text())
    assert meta_data["url"] == "https://youtu.be/abc"

    # cleanup still happened
    assert not (slug / ".source.mp4").exists()
    assert not (slug / ".work-state.json").exists()

    # frames/ directory was NOT created (no extraction happened)
    assert not (slug / "frames").exists()

    # CLAUDE.md still regenerated
    claude_text = (tmp_path / "CLAUDE.md").read_text()
    assert "kpoi-talk" in claude_text
