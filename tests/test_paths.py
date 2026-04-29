from pathlib import Path

from lib import paths


class TestSlugForTitle:
    def test_basic_lowercase_hyphenated(self):
        assert paths.slug_for_title("Key Person of Influence") == "key-person-of-influence"

    def test_strips_special_characters(self):
        assert paths.slug_for_title("KPOI: The 5 P's!") == "kpoi-the-5-ps"

    def test_preserves_standalone_letters(self):
        # Don't mangle common English articles
        assert paths.slug_for_title("How I Built a Startup") == "how-i-built-a-startup"
        assert paths.slug_for_title("The A Team") == "the-a-team"

    def test_collapses_whitespace(self):
        assert paths.slug_for_title("  Many   Spaces  ") == "many-spaces"

    def test_truncates_long_titles(self):
        long = "a " * 200
        result = paths.slug_for_title(long)
        assert len(result) <= 80
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_falls_back(self):
        assert paths.slug_for_title("") == "untitled"

    def test_only_punctuation_falls_back(self):
        assert paths.slug_for_title("!!!") == "untitled"


class TestSlugFolder:
    def test_builds_under_library(self, tmp_path):
        result = paths.slug_folder(library_root=tmp_path, subfolder="daniel-priestly", title="KPOI Talk")
        assert result == tmp_path / "daniel-priestly" / "kpoi-talk"

    def test_uniquifies_existing_slug(self, tmp_path):
        existing = tmp_path / "daniel-priestly" / "kpoi-talk"
        existing.mkdir(parents=True)
        result = paths.slug_folder(library_root=tmp_path, subfolder="daniel-priestly", title="KPOI Talk")
        assert result == tmp_path / "daniel-priestly" / "kpoi-talk-2"

    def test_uniquifies_repeatedly(self, tmp_path):
        (tmp_path / "x" / "talk").mkdir(parents=True)
        (tmp_path / "x" / "talk-2").mkdir(parents=True)
        result = paths.slug_folder(library_root=tmp_path, subfolder="x", title="Talk")
        assert result == tmp_path / "x" / "talk-3"


class TestLibraryRoot:
    def test_returns_library_dir_under_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VIDEOSKILL_HOME", str(tmp_path))
        assert paths.library_root() == tmp_path / "library"

    def test_default_anchors_to_project(self, monkeypatch):
        monkeypatch.delenv("VIDEOSKILL_HOME", raising=False)
        result = paths.library_root()
        assert result.name == "library"
        assert result.parent == Path(__file__).resolve().parent.parent
