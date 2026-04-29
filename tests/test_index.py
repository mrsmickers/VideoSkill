import json
from datetime import datetime, timezone
from pathlib import Path

from lib import index


def _write_video(library_root: Path, sub: str, slug: str, *, title: str, channel: str = "X"):
    folder = library_root / sub / slug
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({
        "url": f"https://youtu.be/{slug}",
        "title": title,
        "channel": channel,
        "duration_seconds": 600,
        "ingest_date": "2026-04-29T12:00:00+00:00",
        "source_hash": "sha1:x",
    }))
    (folder / "summary.md").write_text(f"# {title}\n\n200-word overview here.\n")


def test_scan_library_groups_by_subfolder(tmp_path):
    _write_video(tmp_path, "daniel-priestly", "kpoi", title="KPOI", channel="Daniel Priestly")
    _write_video(tmp_path, "daniel-priestly", "linkedin", title="LinkedIn", channel="Daniel Priestly")
    _write_video(tmp_path, "ppc", "audit", title="PPC Audit", channel="Some Expert")

    grouped = index.scan_library(tmp_path)

    assert set(grouped.keys()) == {"daniel-priestly", "ppc"}
    assert {v["slug"] for v in grouped["daniel-priestly"]} == {"kpoi", "linkedin"}
    assert grouped["ppc"][0]["title"] == "PPC Audit"


def test_render_index_section_lists_videos(tmp_path):
    _write_video(tmp_path, "daniel-priestly", "kpoi", title="KPOI Talk", channel="Daniel Priestly")
    grouped = index.scan_library(tmp_path)

    section = index.render_index_section(grouped)
    assert "## Library" in section
    assert "### daniel-priestly" in section
    assert "kpoi" in section
    assert "KPOI Talk" in section


def test_regenerate_replaces_only_marked_section(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    _write_video(library, "x", "v1", title="V1")

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# VideoSkill library\n"
        "\n"
        "Header prose, user-edited.\n"
        "\n"
        "<!-- BEGIN AUTO-INDEX -->\n"
        "old content\n"
        "<!-- END AUTO-INDEX -->\n"
        "\n"
        "Footer prose.\n"
    )

    index.regenerate(claude_md_path=claude_md, library_root=library)

    text = claude_md.read_text()
    assert "Header prose, user-edited." in text
    assert "Footer prose." in text
    assert "old content" not in text
    assert "### x" in text
    assert "v1" in text


def test_render_index_section_empty_library():
    section = index.render_index_section({})
    assert "## Library" in section
    assert "Empty" in section


def test_regenerate_creates_claude_md_when_missing(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    _write_video(library, "x", "v1", title="V1")
    claude_md = tmp_path / "CLAUDE.md"

    index.regenerate(claude_md_path=claude_md, library_root=library)

    text = claude_md.read_text()
    assert "VideoSkill library" in text
    assert "<!-- BEGIN AUTO-INDEX -->" in text
    assert "v1" in text
