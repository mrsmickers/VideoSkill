import json
from datetime import datetime, timezone

from lib import meta


def test_write_meta_creates_file_with_required_fields(tmp_path):
    folder = tmp_path / "slug"
    folder.mkdir()

    meta.write(
        folder=folder,
        url="https://youtu.be/abc123",
        title="Key Person of Influence",
        channel="Daniel Priestly",
        duration_seconds=1834,
        ingest_date=datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
        source_hash="sha1:deadbeef",
    )

    out = json.loads((folder / "meta.json").read_text())
    assert out == {
        "url": "https://youtu.be/abc123",
        "title": "Key Person of Influence",
        "channel": "Daniel Priestly",
        "duration_seconds": 1834,
        "ingest_date": "2026-04-29T12:00:00+00:00",
        "source_hash": "sha1:deadbeef",
    }


def test_read_returns_parsed_dict(tmp_path):
    folder = tmp_path / "slug"
    folder.mkdir()
    (folder / "meta.json").write_text(json.dumps({"url": "u", "title": "t"}))
    assert meta.read(folder) == {"url": "u", "title": "t"}


def test_read_returns_none_when_missing(tmp_path):
    assert meta.read(tmp_path / "nope") is None


def test_hash_url_is_deterministic_and_short():
    h1 = meta.hash_url("https://youtu.be/abc123")
    h2 = meta.hash_url("https://youtu.be/abc123")
    h3 = meta.hash_url("https://youtu.be/different")
    assert h1 == h2
    assert h1 != h3
    assert h1.startswith("sha1:")
    assert len(h1) == len("sha1:") + 12  # 12 hex chars for compactness
