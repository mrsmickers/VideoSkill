# VideoSkill library

Library of expert video content. Each video lives at `library/<creator-or-topic>/<slug>/`
with `meta.json`, `transcript.md`, `summary.md`, `extracted.md`, and `frames/`.

## For agents on a fresh clone

If `library/` contains video folders with `meta.json` files, the local
library is set up — skip to **How to use this library**. The tracked
[`library-index.md`](library-index.md) lists the catalogue, but its entries
may not be present on a fresh clone because `library/` is gitignored.

Otherwise, walk the user through these steps in order. Don't move on until
each step passes.

### 1. Check prereqs

Run these and report which are missing:

```bash
python3 --version    # need 3.12 or newer
ffmpeg -version | head -1
yt-dlp --version
```

If anything is missing, ask the user to install. macOS shortcut:
`brew install ffmpeg yt-dlp`. Python 3.12+ is usually already there.

### 2. Create the venv and install Python deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. First transcription downloads the model

Transcription runs locally via parakeet-mlx (installed in step 2). Fastest
on Apple Silicon; MLX also ships Linux (CPU/CUDA) and Windows wheels —
work out platform specifics as needed. The first ingest downloads the
~1.2 GB `mlx-community/parakeet-tdt-0.6b-v2` model from Hugging Face —
let the user know, then it's cached forever. No API key needed.

### 4. (Optional) Load env into the current shell

Only needed when publishing frames (Notion/R2) — ingestion itself needs
no env vars:

```bash
cp .env.example .env   # then fill in the publishing vars you need
set -a; source .env; set +a
```

### 5. (Optional) Pick a frame-hosting path if they want to publish SOPs

Skip this entirely if the user just wants the local library and isn't yet
publishing anywhere — ingestion works without it.

If they do want to publish to Notion, ask which path fits:

- **Notion file uploads (default, supports private content).** Frames go
  into the user's Notion workspace's private storage. Setup: create an
  internal integration at notion.so/profile/integrations, give it access
  to the target page via *Connections*, paste the token into `.env` as
  `VIDEOSKILL_NOTION_API_KEY=…`. Script: `scripts/upload-frames-to-notion.py`.
- **Cloudflare R2 (public URLs).** Use this only if the source videos are
  public *and* the user wants frames embeddable outside Notion (blog posts,
  Slack, GitHub READMEs). Setup: create an R2 bucket, enable the managed
  `r2.dev` public domain, create an R2 API token, fill the `VIDEOSKILL_R2_*`
  vars in `.env`. Script: `scripts/upload-frames-to-r2.py`.

If unsure, recommend the Notion path — quicker to set up, covers private
content, and the resulting page looks the same either way.

### 6. Smoke-test on a short video

Before a big batch, ingest one 5–10 minute video to validate the pipeline.
Any public video source `yt-dlp` supports works — YouTube, Vimeo, Twitter/X,
TikTok, LinkedIn, Twitch, conference recordings, etc. Ask the user for a URL,
then follow **How to ingest new content** below.

---

## How to use this library

This library supports three distinct usage modes. Detect which the user is
asking for from their phrasing, and follow the rules for that mode.

### Mode 1 — Question answering ("what would <creator> say about X?")

When the user asks a focused question about a creator's content:

1. Skim [`library-index.md`](library-index.md) to spot the relevant
   subfolder, then check that its files exist locally.
2. `grep -l <topic> library/<sub>/*/summary.md library/<sub>/*/extracted.md`
   to find matching videos quickly. `extracted.md` is where frameworks,
   templates and quotes live; `summary.md` is the lighter overview.
3. Read the matching `summary.md` and `extracted.md` files.
4. Open `transcript.md` only if you need exact wording — quote with the
   `[mm:ss]` timestamp.
5. If the question is visual, look at `frames/` for the relevant timestamp.
6. Cite as `(daniel-priestley/<slug>, 14:32)` so the user can jump back
   to source.

### Mode 2 — Persona / "act as" ("act as Daniel Priestley")

When the user asks you to role-play, embody, or speak as a creator:

1. Read **every** `summary.md` and `extracted.md` under that creator's
   subfolder. These give you the frameworks, recurring vocabulary, do's
   and don'ts, and the verbatim quote bank. Open `transcript.md` files
   selectively if you need tone or speech patterns.
2. **If the creator has a `_distilled-skill/` folder** (e.g.
   `library/daniel-priestley/_distilled-skill/`), read its `SKILL.md` and
   every `references/*.md` file. This is a corpus-wide distillation
   tagged by frequency (`[CORE BELIEF]` / `[STRONG THEME]` / `[NOTABLE]`)
   covering the creator's whole body of work — much richer than the
   handful of videos formally ingested into the library itself. If a
   sibling `_raw-corpus/` folder exists, treat it as the verbatim source
   for that distillation — open it only when you need exact wording.
3. Adopt the creator's voice: their framings, preferred vocabulary,
   typical examples and turn of phrase. Stay in character for the rest
   of the conversation unless the user breaks character.
4. **The library is the primary source of truth.** When making any
   specific claim — a framework, a number, an anecdote, a quote — cite
   the source video as `(creator/slug, mm:ss)` (or
   `(creator/_distilled-skill, references/<file>.md)` for distilled
   material). Quotes especially must come from `extracted.md`,
   `transcript.md`, or `_raw-corpus/`.
5. **Never invent quotes, statistics, or specific stories** and put them
   in the creator's mouth. If the library doesn't contain it, the persona
   doesn't say it. Fabricated quotes attributed to a real person are the
   one failure mode that ruins this mode.
6. When the user asks something the library doesn't cover:
   - Flag it explicitly first, in character: *"I haven't covered this on
     camera, but…"* or *"that's not something I've gone deep on in
     videos, but my general view…"*
   - Then answer from general public knowledge of the person, not from
     specifics that would imply a video source you can't cite.
7. If the user pushes for a citation you genuinely can't make from the
   library, say so honestly rather than fabricating one.

### Mode 3 — Build a skill or SOP from a creator's body of work

When the user asks you to *"create a skill from <creator>'s content"*,
*"build an SOP from <slug>"*, or similar:

1. Read every `extracted.md` under the relevant scope (whole creator
   folder for skills, single slug folder for SOPs). `extracted.md` is
   the spine of any output here — frameworks, templates, do's/don'ts,
   verbatim quotes are already structured.
2. For a Claude Code skill: invoke `anthropic-skills:skill-creator` if
   it's installed, otherwise write `SKILL.md` directly into
   `.claude/skills/<creator>-<topic>/`. Cite source videos in the skill
   prose so it stays traceable.
3. For a Notion SOP: invoke the `publish-sop` skill
   (`skills/publish-sop/SKILL.md`) — it covers the whole flow, from
   URL-or-slug input through frame curation to the assembled Notion page.

### Recreating a video's whiteboard visuals in tldraw

When a library video's `frames/` contain hand-drawn whiteboard or diagram
visuals (e.g. Daniel Priestley's post-production boards), they can be
rebuilt as live canvases in the local tldraw desktop app — including a
staged build-up reveal (click, arrow keys, or presenter clicker) for
screen-recording Simon's own videos in the same style. Invoke the
`tldraw-offline` skill and follow its
`references/video-whiteboard-reveal.md` — style recipe, gotchas, and a
working reveal-rig script, proven against
`daniel-priestley/why-you-must-build-a-youtube-channel` frames (Jul 2026).

## How to ingest new content

No env needed for ingestion (transcription is local). Load `.env` only when
publishing frames to Notion/R2. For each URL the user gives you:

1. **Prepare** — `.venv/bin/python ingest.py prepare <URL> --to <subfolder-name>`.
   Downloads, transcribes, writes `transcript.md`. Output ends with
   `slug_folder=<path>`.
2. **Read** the produced `transcript.md`.
3. **Write `summary.md`** — ~200-word overview + 5–10 timestamped key points.
4. **Write `extracted.md`** — named frameworks, step-by-step processes,
   verbatim templates/scripts, verbatim quotes with timestamps, explicit
   do's/don'ts. The quality bar here is high; this is the file Claude will
   read to answer questions later.
5. **Pick 8–15 frame timestamps** that capture the most important visuals —
   whiteboards, diagrams, key text overlays. Two inputs help:
   run `.venv/bin/python ingest.py propose-frames <slug_folder>` for
   scene-change candidates, and scan the transcript for deictic cues
   ("as you can see", "look here", "notice this") — moments the speaker
   points at something on screen that scene detection may miss.
   Animated whiteboards build up over time, so target the *end* of each
   animated section, not the middle. Frames are auto-capped at 1600px to
   stay under Anthropic's many-image dimension limit.
6. **Finalize** — `.venv/bin/python ingest.py finalize <slug_folder> --frames "00:35,04:35,..."`.
   Extracts frames, writes `meta.json`, regenerates `library-index.md`,
   cleans up the source mp4.

Design notes: `docs/superpowers/specs/2026-04-29-videoskill-design.md`.
Build plan: `docs/superpowers/plans/2026-04-29-videoskill-implementation.md`.
