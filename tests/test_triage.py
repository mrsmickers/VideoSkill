import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

TRIAGE_PATH = Path(__file__).parent.parent / "skills" / "watch-worth-it" / "scripts" / "triage.py"
VTT_FIXTURE = Path(__file__).parent / "fixtures" / "rolling_dupes.vtt"

spec = importlib.util.spec_from_file_location("triage", TRIAGE_PATH)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


def test_parse_vtt_collapses_rolling_duplicates():
    segments = triage.parse_vtt(str(VTT_FIXTURE))
    texts = [s["text"] for s in segments]
    assert texts == ["Hello and welcome to the channel", "Today we cover pricing"]
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 4.0


def test_format_transcript_timestamps():
    segs = [{"start": 65.0, "end": 70.0, "text": "Step one."}]
    assert triage.format_transcript(segs) == "[01:05] Step one."


def test_is_safe_source():
    assert triage.is_safe_source("https://youtu.be/abc")
    assert not triage.is_safe_source("--exec=evil")
    assert not triage.is_safe_source("ftp://x/y")


def test_fetch_captions_argv(tmp_path, mocker):
    run_mock = mocker.patch.object(
        triage.subprocess, "run", return_value=MagicMock(returncode=0)
    )
    triage.fetch_captions("https://youtu.be/abc", tmp_path)
    cmd = run_mock.call_args.args[0]
    assert cmd[0] == "yt-dlp"
    assert "--skip-download" in cmd
    assert "--write-subs" in cmd and "--write-auto-subs" in cmd
    assert cmd[-2:] == ["--", "https://youtu.be/abc"]


def test_download_lowres_argv(tmp_path, mocker):
    (tmp_path / "video.mp4").touch()
    run_mock = mocker.patch.object(
        triage.subprocess, "run", return_value=MagicMock(returncode=0)
    )
    triage.download_lowres("https://youtu.be/abc", tmp_path)
    cmd = run_mock.call_args.args[0]
    fmt = cmd[cmd.index("-f") + 1]
    assert "height<=480" in fmt
    assert cmd[-2:] == ["--", "https://youtu.be/abc"]


def test_pick_frame_timestamps_even_samples():
    picked = triage.pick_frame_timestamps(list(range(10)), 4, duration=100.0)
    assert picked[0] == 0 and picked[-1] == 9 and len(picked) == 4


def test_pick_frame_timestamps_uniform_fallback():
    picked = triage.pick_frame_timestamps([], 4, duration=100.0)
    assert len(picked) == 4
    assert picked[0] >= 0 and picked[-1] <= 100.0


def test_scene_timestamps_and_extract_triage_frames(tmp_path, cut_clip):
    ts = triage.scene_timestamps(str(cut_clip))
    assert len(ts) >= 5
    out = triage.extract_triage_frames(str(cut_clip), tmp_path, [0.5, 1.5, 2.5])
    assert len(out) == 3
    assert all(Path(p).exists() for _, p in out)
    assert out[0][0] == 0.5


def test_build_report_sections(tmp_path):
    info = {"title": "T", "uploader": "C", "duration": 90, "webpage_url": "https://u", "view_count": 5}
    segs = [{"start": 0.0, "end": 2.0, "text": "Hi."}]
    report = triage.build_report(info, segs, "captions (en)", [(1.0, "/tmp/f.jpg")], tmp_path)
    assert "Title:    T" in report
    assert "Duration: 01:30" in report
    assert "[00:00] Hi." in report
    assert "t=00:01 /tmp/f.jpg" in report
    assert f"work_dir={tmp_path}" in report


def test_build_report_no_captions_gives_options(tmp_path):
    info = {"title": "T", "duration": 90, "webpage_url": "https://u"}
    report = triage.build_report(info, [], "none", [], tmp_path)
    assert "NONE AVAILABLE" in report
    assert "--frames" in report
