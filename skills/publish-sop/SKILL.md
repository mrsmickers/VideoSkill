---
name: publish-sop
version: "0.1.0"
description: Hand it a video URL (or an existing library slug) and get a Notion SOP/Playbook page with key info and frame images. Runs the full VideoSkill ingest if the video isn't in the library yet, then composes the page — extracted.md as the spine, concept-card frames embedded at the right sections, verbatim quotes with timestamps.
argument-hint: "<video-url-or-slug-path> [--parent <notion-page-id>]"
allowed-tools: Bash, Read
license: MIT
user-invocable: true
---

# /publish-sop

Turn a video into a Notion document with images. Primary flow: the user hands
you a URL; you ingest it into the VideoSkill library (if it isn't already
there), then write it up as a Notion page. Works in any agent host.

## Resolve paths (before any command)

`SKILL_DIR` = the absolute directory containing THIS SKILL.md. This skill
lives inside the VideoSkill repo, so the repo root is two levels up from the
*resolved* skill folder (symlink installs resolve to the real location):

```bash
SKILL_DIR="<absolute dir of the SKILL.md you just read>"
REPO_ROOT="$(cd "$(dirname "$(readlink -f "$SKILL_DIR/SKILL.md")")/../.." && pwd)"
[ -f "$REPO_ROOT/ingest.py" ] || echo "ERROR: VideoSkill repo not found at $REPO_ROOT"
```

The Notion helper is `SKILL_DIR/scripts/notion_sop.py` (pure stdlib; key from
`VIDEOSKILL_NOTION_API_KEY` or `~/.config/notion/api_key`).

## Step 1 — ensure the video is in the library

- Given a **slug path** (`library/<creator>/<slug>/` with `extracted.md`
  present): skip to Step 2.
- Given a **URL**: check whether it's already ingested —
  `grep -rl "<url>" "$REPO_ROOT"/library/*/*/meta.json`. If not, run the full
  ingest per the repo's CLAUDE.md "How to ingest new content":
  `prepare` → read transcript → write `summary.md` + `extracted.md` →
  `propose-frames` + transcript deictic cues → `finalize --frames …`.
  (Needs the repo venv — transcription is local Parakeet, ~1 min per
  audio-hour. If unsure whether it's worth ingesting at all, run
  `/watch-worth-it` first.)

## Step 2 — pick the frames that earn a place on the page

Read every JPG in the slug's `frames/` folder (they render as images).
Classify each:

- **Embed:** concept cards, whiteboards, diagrams, slides, on-screen text,
  app/config screens — anything that carries information.
- **Skip:** talking heads, b-roll without text, near-duplicates of an
  already-chosen frame.

A talking-head video may yield only 4–6 embeddable frames from 10 extracted —
that's normal. Never pad the page with face shots.

## Step 3 — compose the body (markdown chunks)

Write chunk files to a scratch dir. Structure (mirrors the exemplar pages):

1. **Lead** — nothing before the first image: the strongest concept-card frame.
2. **`## Source`** — video link, channel, duration, ingest date, and the
   library path in backticks.
3. **`## TL;DR`** — one tight paragraph; bold the key frameworks.
4. **Body** — `extracted.md` is the spine. One `##` section per framework or
   phase, with `(mm:ss)` timestamps in headings and claims:
   - verbatim quotes as `>` blocks
   - application actions as `- [ ]` to-dos (make 1–2 specific to the user's
     business where obvious)
   - keep numbers and named concepts exactly as spoken
5. **Footer** — divider + italic line linking back to the library entry.

Rules: UK English prose. Never paste the whole transcript. Chunk boundaries
go exactly where images will sit.

## Step 4 — assemble the page

Default parent: **📹 YouTube & Content** (`2dc7f185-0b11-80ed-b789-f4fbf355179e`)
unless `--parent` or `VIDEOSKILL_NOTION_PARENT_ID` says otherwise.

```bash
python3 "$SKILL_DIR/scripts/notion_sop.py" create <parent_id> "<Creator> — <Title> (SOP|Playbook)" --icon 🧠
# then alternate, in reading order:
python3 "$SKILL_DIR/scripts/notion_sop.py" image  <page_id> <frame.jpg> --caption "<what it shows> (mm:ss)"
python3 "$SKILL_DIR/scripts/notion_sop.py" append <page_id> <chunk.md>
```

Title suffix: **(SOP)** for procedural content (setup guides, how-tos),
**(Playbook)** for frameworks/mental models. Images are Notion-hosted
(private file uploads) — no public URLs involved; use
`scripts/upload-frames-to-r2.py` only if the user wants frames embeddable
outside Notion.

## Step 5 — verify and hand over

```bash
python3 "$SKILL_DIR/scripts/notion_sop.py" read <page_id>
```

Confirm headings, images and to-dos all landed, then give the user the page
URL plus a 2–3 bullet note of what's on it. Clean up the scratch chunks.

## Exemplars (match their shape)

- `3557f185-0b11-81a9-ae87-c200b3351b76` — "Why You Must Build a YouTube
  Channel (SOP)" — procedural, phases with whiteboard frames.
- `39c7f185-0b11-81cf-abd4-ef9910648f85` — "What I Learned From Being Around
  The Top 0.01% (Playbook)" — nine mental models with concept-card frames.
