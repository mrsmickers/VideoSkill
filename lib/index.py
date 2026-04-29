import json
import re
from pathlib import Path

BEGIN_MARKER = "<!-- BEGIN AUTO-INDEX -->"
END_MARKER = "<!-- END AUTO-INDEX -->"


def scan_library(library_root: Path) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    if not library_root.exists():
        return grouped
    for sub in sorted(p for p in library_root.iterdir() if p.is_dir()):
        videos = []
        for slug_dir in sorted(p for p in sub.iterdir() if p.is_dir()):
            meta_path = slug_dir / "meta.json"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text())
            videos.append({
                "slug": slug_dir.name,
                "subfolder": sub.name,
                "title": meta.get("title", slug_dir.name),
                "channel": meta.get("channel", ""),
                "url": meta.get("url", ""),
                "ingest_date": meta.get("ingest_date", ""),
            })
        if videos:
            grouped[sub.name] = videos
    return grouped


def render_index_section(grouped: dict[str, list[dict]]) -> str:
    if not grouped:
        return "## Library\n\n*Empty. Run an ingest to populate.*\n"
    lines = ["## Library", ""]
    for sub, videos in grouped.items():
        lines.append(f"### {sub}")
        lines.append("")
        for v in videos:
            lines.append(f"- `{sub}/{v['slug']}/` — {v['title']}")
        lines.append("")
    return "\n".join(lines)


def regenerate(*, claude_md_path: Path, library_root: Path) -> None:
    grouped = scan_library(library_root)
    section = render_index_section(grouped)

    if not claude_md_path.exists():
        claude_md_path.write_text(_default_template(section))
        return

    text = claude_md_path.read_text()
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )
    replacement = f"{BEGIN_MARKER}\n{section}\n{END_MARKER}"
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        text = text.rstrip() + f"\n\n{replacement}\n"
    claude_md_path.write_text(text)


def _default_template(section: str) -> str:
    return (
        "# VideoSkill library\n"
        "\n"
        "Library of expert video content. Each video lives in `library/<creator-or-topic>/<slug>/`\n"
        "with `meta.json`, `transcript.md`, `summary.md`, `extracted.md`, and `frames/`.\n"
        "\n"
        "When the user asks about a creator's content, scan their subfolder's `summary.md`\n"
        "and `extracted.md` files first; only open transcripts for exact quotes.\n"
        "\n"
        f"{BEGIN_MARKER}\n{section}\n{END_MARKER}\n"
    )
