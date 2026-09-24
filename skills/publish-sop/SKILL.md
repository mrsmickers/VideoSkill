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
[ -f "$REPO_ROOT/ingest.py" ] || echo "VideoSkill repo not found at $REPO_ROOT — see Step 0 (clone it first)"
```

The Notion helper is `SKILL_DIR/scripts/notion_sop.py` (pure stdlib; key from
`VIDEOSKILL_NOTION_API_KEY` or `~/.config/notion/api_key`).

## Step 0 — first-run setup gate

Three prerequisites; check them in order and walk the user through whatever
is missing. Once all three pass on a machine they stay passed — skip this
on later runs.

**1. The VideoSkill repo.** This skill cannot run from a bare copy of its
folder — it ingests into the repo's `library/` and uses its `ingest.py`.
If the `REPO_ROOT` check above failed:

```bash
git clone https://github.com/mrsmickers/VideoSkill.git
ln -s "$(pwd)/VideoSkill/skills/publish-sop" ~/.claude/skills/publish-sop
```

**2. Ingestion dependencies** (skip when publishing an already-ingested
slug — composing the page needs none of this):

- `ffmpeg` + `yt-dlp` on PATH (macOS: `brew install ffmpeg yt-dlp`).
- The repo venv with parakeet-mlx:
  ```bash
  "$REPO_ROOT/.venv/bin/python" -c "import parakeet_mlx" 2>/dev/null || {
    python3 -m venv "$REPO_ROOT/.venv"
    "$REPO_ROOT/.venv/bin/pip" install -r "$REPO_ROOT/requirements.txt"
  }
  ```
- Tell the user up front: transcription is **local and free** — fastest on
  Apple Silicon, but MLX also ships Linux (CPU/CUDA) and Windows wheels, so
  work out platform specifics as needed (CPU-only transcription is slower
  but functional). The first ingest downloads the ~1.2 GB
  `parakeet-tdt-0.6b-v2` model from Hugging Face, then it's cached forever.

**3. Notion access.** If no key is found at `VIDEOSKILL_NOTION_API_KEY` or
`~/.config/notion/api_key`, walk the user through it (one-time, ~2 min):

1. Create an internal integration at
   [notion.so/profile/integrations](https://www.notion.so/profile/integrations)
   and copy the secret (`ntn_…`).
2. In Notion, open (or create) the parent page where SOPs should live →
   `⋯` menu → *Connections* → add the integration.
3. Store both values in the repo's `.env` (gitignored — see `.env.example`):
   `VIDEOSKILL_NOTION_API_KEY=…` and `VIDEOSKILL_NOTION_PARENT_ID=<page UUID
   from its URL>`, then `set -a; source .env; set +a`.

## Step 1 — ensure the video is in the library

- Given a **slug path** (`library/<creator>/<slug>/` with `extracted.md`
  present): skip to Step 2.
- Given a **URL**: check whether it's already ingested —
  `grep -rl "<url>" "$REPO_ROOT"/library/*/*/meta.json`. If not, run the full
  ingest per the repo's AGENTS.md "How to ingest new content":
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

Resolve the parent page, in order: an explicit `--parent <page-id>` from the
user → the `VIDEOSKILL_NOTION_PARENT_ID` env var (set it in the repo's `.env`;
`set -a; source .env; set +a`) → otherwise ask the user which page SOPs
should live under. The parent must be shared with your Notion integration
(page ⋯ menu → Connections). Same-named pages can be found with the API
search endpoint if you have a title but no ID.

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

## Optional — interactive HTML blocks (Notion 3.6+)

When the video's content *is* a tool — a calculator, a scoring rubric, an
interactive framework — don't screenshot it, rebuild it:

```bash
python3 "$SKILL_DIR/scripts/notion_sop.py" html <page_id> <tool.html> --caption "<what it does>"
```

Write the `.html` fully self-contained (inline CSS/JS): it renders in a
sandboxed iframe with **no external network access and no access to Notion
data**, so CDN scripts, fonts, and fetch calls will silently fail. Good
candidates: formula calculators (e.g. the AdWords-course calculator lessons),
ROI/pricing tools, interactive diagrams. Don't use it for static content —
markdown blocks search and export better.

## Step 5 — verify and hand over

```bash
python3 "$SKILL_DIR/scripts/notion_sop.py" read <page_id>
```

Confirm headings, images and to-dos all landed, then give the user the page
URL plus a 2–3 bullet note of what's on it. Clean up the scratch chunks.

## Exemplars (match their shape)

Two reference pages exist in the maintainer's workspace (search your own
parent page for them if you have access; the structure is fully described in
Step 3 either way):

- *"Daniel Priestley — Why You Must Build a YouTube Channel (SOP)"* —
  procedural: three phases, whiteboard frames at the relevant steps.
- *"Daniel Priestley — What I Learned From Being Around The Top 0.01%
  (Playbook)"* — nine mental models, concept-card frames, application to-dos.
