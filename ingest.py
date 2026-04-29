import argparse
import json
import sys
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
    except Exception as e:
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
    # Implemented in Task 10.
    raise NotImplementedError("finalize subcommand pending Task 10")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="download, transcribe, write transcript.md")
    p.add_argument("url")
    p.add_argument("--to", required=True, help="subfolder name under library/")
    p.add_argument("--library", default=str(Path(__file__).parent / "library"))
    p.set_defaults(func=_cmd_prepare)

    f = sub.add_parser("finalize", help="extract frames, write meta.json, regenerate index, cleanup")
    f.add_argument("slug_folder")
    f.add_argument("--frames", default="", help="comma-separated mm:ss timestamps")
    f.set_defaults(func=_cmd_finalize)

    return parser


def run(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
