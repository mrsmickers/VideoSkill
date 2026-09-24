import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib import download, frames, index, meta, paths, transcribe


def _cmd_prepare(args: argparse.Namespace) -> int:
    library_root = Path(args.library).resolve()
    url = args.url
    subfolder = args.to

    # Idempotence: check if any existing slug folder under this subfolder has matching url in meta.json.
    sub_dir = library_root / subfolder
    if sub_dir.exists():
        for existing in sub_dir.iterdir():
            if not existing.is_dir():
                continue
            mp = existing / "meta.json"
            if mp.exists():
                existing_meta = json.loads(mp.read_text())
                if existing_meta.get("url") == url:
                    print(f"already ingested: {existing}")
                    print(f"slug_folder={existing}")
                    return 0

    # Initial download into a temp basename; the final slug uses the title from yt-dlp info.
    sub_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = sub_dir / ".staging"
    tmp_dir.mkdir(exist_ok=True)
    tmp_basename = "incoming"

    try:
        dl = download.download_video(url=url, out_dir=tmp_dir, out_basename=tmp_basename)
    except download.DownloadError as e:
        print(f"ERROR: download failed: {e}", file=sys.stderr)
        return 2

    info = dl["info"]
    title = info.get("title", "untitled")
    channel = info.get("channel") or info.get("uploader") or ""
    duration = int(info.get("duration") or 0)

    slug_folder = paths.slug_folder(library_root=library_root, subfolder=subfolder, title=title)
    slug_folder.mkdir(parents=True, exist_ok=True)

    # Move source files into slug folder with hidden names.
    source_video = slug_folder / ".source.mp4"
    source_audio = slug_folder / ".audio.mp3"
    dl["video_path"].rename(source_video)

    try:
        transcribe.extract_audio(video_path=source_video, audio_path=source_audio)
    except transcribe.TranscribeError as e:
        print(f"ERROR: audio extract failed: {e}", file=sys.stderr)
        return 3

    try:
        segments = transcribe.transcribe_audio(audio_path=source_audio)
    except transcribe.TranscribeError as e:
        print(f"ERROR: transcription failed: {e}", file=sys.stderr)
        return 4

    transcript_md = transcribe.format_transcript(segments)
    (slug_folder / "transcript.md").write_text(transcript_md)

    # Persist work state for the finalize step.
    state = {
        "url": url,
        "title": title,
        "channel": channel,
        "duration_seconds": duration,
        "subfolder": subfolder,
        "source_video": str(source_video),
        "source_audio": str(source_audio),
    }
    (slug_folder / ".work-state.json").write_text(json.dumps(state, indent=2))

    # Cleanup staging.
    for p in tmp_dir.glob("*"):
        p.unlink()
    tmp_dir.rmdir()

    print(f"slug_folder={slug_folder}")
    print(f"transcript={slug_folder / 'transcript.md'}")
    print("Now: read the transcript, write summary.md and extracted.md, then call:")
    print(f"  python ingest.py finalize {slug_folder} --frames \"<comma-separated mm:ss list>\"")
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    slug_folder = Path(args.slug_folder).resolve()
    state_path = slug_folder / ".work-state.json"
    if not state_path.exists():
        print(f"ERROR: no .work-state.json at {state_path} — was prepare run?", file=sys.stderr)
        return 5

    state = json.loads(state_path.read_text())
    source_video = Path(state["source_video"])
    source_audio = Path(state["source_audio"])

    raw = (args.frames or "").strip()
    timestamps = [t.strip() for t in raw.split(",") if t.strip()] if raw else []

    if timestamps:
        try:
            written = frames.extract_frames(
                video_path=source_video,
                timestamps=timestamps,
                out_dir=slug_folder / "frames",
            )
        except (frames.FrameExtractError, ValueError) as e:
            print(f"ERROR: frame extraction failed: {e}", file=sys.stderr)
            return 6
        for a, b in frames.near_duplicate_pairs(written):
            print(f"WARNING: near-identical frames: {a.name} and {b.name} — consider replacing one")

    meta.write(
        folder=slug_folder,
        url=state["url"],
        title=state["title"],
        channel=state["channel"],
        duration_seconds=int(state["duration_seconds"]),
        ingest_date=datetime.now(timezone.utc),
        source_hash=meta.hash_url(state["url"]),
    )

    # Cleanup.
    for p in (source_video, source_audio, state_path):
        if p.exists():
            p.unlink()

    # Regenerate the standalone library index.
    library_root = Path(args.library).resolve()
    index_path = Path(args.index_path).resolve()
    index.regenerate(index_path=index_path, library_root=library_root)

    print(f"finalized: {slug_folder}")
    return 0


def _cmd_propose_frames(args: argparse.Namespace) -> int:
    slug_folder = Path(args.slug_folder).resolve()
    state_path = slug_folder / ".work-state.json"
    source = slug_folder / ".source.mp4"
    if not state_path.exists() or not source.exists():
        print(
            f"ERROR: no .source.mp4/.work-state.json in {slug_folder} — "
            "run prepare first (propose-frames only works before finalize)",
            file=sys.stderr,
        )
        return 7

    try:
        timestamps = frames.detect_scene_timestamps(video_path=source)
    except frames.FrameExtractError as e:
        print(f"ERROR: scene detection failed: {e}", file=sys.stderr)
        return 8

    # Sub-second cuts round to the same mm:ss — dedupe, then thin noisy lists
    # (fast-cut edits produce hundreds of cuts) by even-sampling down to 40.
    seen: dict[str, None] = {}
    for t in timestamps:
        mm, ss = divmod(int(t), 60)
        seen.setdefault(f"{mm:02d}:{ss:02d}")
    stamps = list(seen)
    cap = 40
    if len(stamps) > cap:
        idx = [round(i * (len(stamps) - 1) / (cap - 1)) for i in range(cap)]
        picked = [stamps[i] for i in dict.fromkeys(idx)]
        print(f"{len(timestamps)} scene changes detected — showing {len(picked)} of {len(stamps)} distinct seconds:")
    else:
        picked = stamps
        print(f"{len(stamps)} candidate frame timestamps (scene changes):")
    for stamp in picked:
        print(f"  {stamp}")
    print(
        "\nThese are candidates only — cross-reference the transcript (deictic cues"
        ' like "as you can see" / "look here") and prefer the END of animated'
        " whiteboard sections. Pick 8-15 and pass them to finalize --frames."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="download, transcribe, write transcript.md")
    p.add_argument("url")
    p.add_argument("--to", required=True, help="subfolder name under library/")
    p.add_argument("--library", default=str(Path(__file__).parent / "library"))
    p.set_defaults(func=_cmd_prepare)

    pf = sub.add_parser("propose-frames", help="print scene-change candidate timestamps for a prepared slug")
    pf.add_argument("slug_folder")
    pf.set_defaults(func=_cmd_propose_frames)

    f = sub.add_parser("finalize", help="extract frames, write meta.json, regenerate index, cleanup")
    f.add_argument("slug_folder")
    f.add_argument("--frames", default="", help="comma-separated mm:ss timestamps")
    f.add_argument("--library", default=str(Path(__file__).parent / "library"))
    f.add_argument("--index", dest="index_path", default=str(Path(__file__).parent / "library-index.md"))
    f.set_defaults(func=_cmd_finalize)

    return parser


def run(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
