# VideoSkill

[![Tests](https://github.com/mrsmickers/VideoSkill/actions/workflows/test.yml/badge.svg)](https://github.com/mrsmickers/VideoSkill/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Build a personal library from anyone's public video corpus, then talk to
them through Claude Code — or generate fully-cited SOPs from any single
video. Plain markdown + JPGs you own outright.

## Two main uses

### 1. Chat with a virtual creator

Ingest two years of someone's YouTube/Vimeo/podcast output. Open Claude
Code in this folder and say *"act as Daniel Priestley"*. Claude reads the
library — every framework, recurring story, verbatim quote, do/don't —
and stays in character. When you ask about something they actually
covered on camera, the persona quotes them with a citation. When you ask
something they haven't covered, the persona flags that explicitly and
falls back to general public knowledge. **Never invents quotes** — those
only ever come from the library.

This is closer to having a coffee with someone than to reading their
books.

### 2. Generate a Notion SOP from a single video

Like Loom's AI SOP feature, with two differences:

- **You don't record the video — you give it a URL.** Works on most
  public video sources, not just YouTube: Vimeo, Twitter/X, TikTok,
  LinkedIn, Twitch, conference recordings. Anything `yt-dlp` can fetch.
- **Output is plain markdown + JPGs you own.** No SaaS lock-in. Pages
  can publish to Notion (frames hosted privately in your workspace, by
  default) or render anywhere else.

## What an ingested video looks like

Each video lives at `library/<creator-or-topic>/<slug>/`:

- `transcript.md` — full timestamped transcript (local Parakeet ASR)
- `summary.md` — short overview + 5–10 timestamped key points
- `extracted.md` — frameworks, templates, verbatim quotes with timestamps,
  explicit do's/don'ts. *This is the file the persona reads most.*
- `frames/` — JPG frames at the timestamps that mattered (auto-capped at
  1600px so Claude can review many in one go)
- `meta.json` — url, title, channel, duration, ingest date

The mechanical work (download, transcribe, extract frames) is Python. The
cognitive work (write the summary + extraction, pick frame timestamps,
hold the persona, compose SOPs) runs inside your Claude Code session —
covered by your subscription, not metered API calls.

## What it costs

- **Transcription is free and local** — NVIDIA `parakeet-tdt-0.6b-v2`
  running on Apple Silicon via parakeet-mlx (~1 minute per audio-hour,
  one-time ~1.2 GB model download, English-only).
- **Your existing Claude Code subscription** covers the cognitive work —
  summary, methodology extraction, frame selection, SOP authoring. No
  metered API calls.
- **Optional storage**: any free-tier public bucket. R2's free tier (10GB
  + unlimited egress on the managed domain) is what's wired up; alternatives
  below.

For comparison: Loom Business is $15/seat/month and the AI-generated SOPs
live inside Loom. VideoSkill's output is plain markdown + JPGs you own
outright — grep them, version-control them, fork them into new skills,
embed them in any tool.

## Prerequisites

- Python 3.12+
- `ffmpeg` and `yt-dlp` on your PATH (e.g. `brew install ffmpeg yt-dlp` on macOS)
- Transcription runs locally via
  [parakeet-mlx](https://github.com/senstella/parakeet-mlx) (no API key;
  the ~1.2 GB model downloads on first use). Fastest on Apple Silicon —
  MLX also ships Linux (CPU/CUDA) and Windows wheels, just expect slower
  CPU transcription off-Apple
- Claude Code installed (the cognitive work runs inside a Claude Code session)

## Setup

```bash
# 1. Install Python deps in a venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) Configure publishing secrets (Notion/R2) — not needed to ingest
cp .env.example .env
$EDITOR .env
set -a; source .env; set +a

# 3. Open Claude Code in this folder
claude
```

Then in Claude Code: *"ingest these URLs into daniel-priestley: <URLs>"*. Claude
runs `ingest.py prepare` for each URL, reads the transcripts, writes
`summary.md` + `extracted.md`, picks frame timestamps, and runs `ingest.py
finalize`.

After ingesting, the top-level `CLAUDE.md` is regenerated as an index of the
library so a future Claude Code session sees the whole library on chat open.

## Using the library

### Question-answering mode

Open Claude Code in this folder and ask, e.g.
*"what would Daniel Priestley say about LinkedIn posts?"* Claude reads
the index in `CLAUDE.md`, greps `summary.md` / `extracted.md` for matches,
opens the relevant files, and answers with citations like
`(daniel-priestley/<slug>, 14:32)`. The questions stay yours, the answers
stay attributed.

### Persona / "act as" mode

Tell Claude *"act as Daniel Priestley"*, *"role-play as <creator>"*, or
similar. Claude reads every `extracted.md` and `summary.md` under that
creator's subfolder — frameworks, vocabulary, recurring stories — and
stays in character.

Behaviour rules baked into `CLAUDE.md`:

- **The library is the primary source of truth.** Specific claims —
  frameworks, statistics, anecdotes, quotes — must come from a video and
  be cited as `(creator/slug, mm:ss)`.
- **Never invent quotes.** If the library doesn't contain it, the persona
  doesn't say it. Fabricated quotes attributed to a real person are the
  one thing that ruins the mode.
- **Flag fallbacks explicitly.** When the user asks something the library
  doesn't cover, the persona says so in character — *"I haven't covered
  this on camera, but…"* — then answers from general public knowledge of
  the person.

This is closer to having a coffee with the person than to reading their
books.

### Skill / SOP / asset creation

When a creator has 30+ videos in the library, ask Claude to package
their methodology as a Claude Code skill (using the
`anthropic-skills:skill-creator` skill, if installed) or as a Notion SOP
(see the next section). Both work off the same `extracted.md` files the
persona mode uses.

## /watch-worth-it — triage before you ingest

`skills/watch-worth-it/` is a self-contained, host-agnostic agent skill that
answers "is this video worth a full ingest?" using metadata + captions only
(no video download; optional `--frames N` low-res visual pass). It needs just
`yt-dlp` and `ffmpeg` — no venv, no API keys.

Install by symlink into whichever agents you use:

```bash
ln -s "$(pwd)/skills/watch-worth-it" ~/.claude/skills/watch-worth-it   # Claude Code
ln -s "$(pwd)/skills/watch-worth-it" ~/.codex/skills/watch-worth-it    # Codex
# Hermes / other agentskills.io hosts: symlink the same folder into their skills dir
```

Then: `/watch-worth-it <url>` → **INGEST** / **PARTIAL** / **SKIP** with
timestamped reasons, a library-overlap check, and a ready-to-run
`ingest.py prepare` command when it's a yes.

## /publish-sop — video in, Notion page out

`skills/publish-sop/` completes the pipeline: hand it a video URL (or an
already-ingested slug folder) and it produces a Notion SOP/Playbook page —
running the full library ingest first if needed, then composing the page
with `extracted.md` as the spine and only the informative frames embedded
(concept cards, whiteboards, screens — never talking heads). Frames are
Notion-hosted via the private file-uploads API; no public URLs required.

Install the same way (this one does need the repo, since it ingests):

```bash
ln -s "$(pwd)/skills/publish-sop" ~/.claude/skills/publish-sop   # Claude Code
ln -s "$(pwd)/skills/publish-sop" ~/.codex/skills/publish-sop    # Codex
```

It can also attach **interactive HTML blocks** (Notion 3.6+) — when a video's
content *is* a tool (a calculator, a scoring rubric), the skill can rebuild
it as a self-contained sandboxed HTML block instead of screenshotting it.

Set two things in `.env` (see `.env.example`): `VIDEOSKILL_NOTION_API_KEY`
(an internal integration token) and `VIDEOSKILL_NOTION_PARENT_ID` (the page
your SOPs should live under, shared with that integration).

The full pipeline: `/watch-worth-it <url>` (should I?) → `/publish-sop <url>`
(ingest + write it up in Notion with images).

## Optional — publish a slug folder as a Notion SOP

**The `/publish-sop` skill (previous section) automates this whole flow** —
including a stdlib Notion client for page creation and private image
uploads, so the recipes below are only needed if you want to drive the
pieces manually or host frames at public URLs. Either way the composition is
the same: `extracted.md` becomes the spine, frames slot in next to the
relevant step. Two frame-upload paths ship with the project, chosen by
privacy:

|                          | `upload-frames-to-notion.py` (recommended) | `upload-frames-to-r2.py` |
|--------------------------|--------------------------------------------|--------------------------|
| Storage                  | Notion's private workspace storage         | Cloudflare R2 public domain |
| Who can fetch the frame  | Authenticated members of your Notion workspace | Anyone with the URL |
| Suitable for             | **Public *and* private** source videos     | Public source videos only |
| Reusable URL outside Notion | No (URLs are workspace-bound) | Yes — embed in blog posts, Slack, GitHub |
| Setup                    | One Notion integration token (1 min) | A Cloudflare R2 bucket + API token (5 min) |

If you're unsure, start with the Notion path — it's faster to set up,
covers private content, and the Markdown SOP draft Claude composes can
embed images either way.

> **Caveat for agents on a Notion MCP** (e.g. Claude Cowork's bundled
> Notion connector, or the standard Notion MCP server): the MCPs available
> today only expose the pages / blocks API, which embeds images via
> Markdown `![alt](url)` and so needs a public URL. They don't surface
> Notion's `/v1/file_uploads` endpoint. If your agent environment can run
> Python locally (e.g. Claude Code from a terminal), `scripts/upload-frames-to-notion.py`
> bypasses the MCP and uses file_uploads directly. If it can't (most hosted
> agent environments), you're on Recipe B (R2) — and remember that means
> the source video has to be public.

### Recipe A — Notion file uploads (default)

1. Create an internal Notion integration at
   [notion.so/profile/integrations](https://www.notion.so/profile/integrations).
   Copy the secret token (starts with `ntn_` or `secret_`).
2. Open the parent Notion page where the SOP will live, click *Connections*
   in the top-right, and add your new integration so it has access.
3. Put the token in `.env` as `VIDEOSKILL_NOTION_API_KEY=…`, then re-source.
4. In Claude Code, ask: *"create a Notion SOP under <parent-page> from
   library/<creator>/<slug>"*. Claude writes the page (using its
   Notion MCP if present, or by direct API call), then runs:
   ```bash
   .venv/bin/python scripts/upload-frames-to-notion.py \
       library/<creator>/<slug> --page-id <new-page-id>
   ```
   …which uploads each frame and appends it as an image block on the page.

Frames end up on `prod-files-secure.s3.us-west-2.amazonaws.com` — Notion's
private CDN. Only authenticated members of your workspace can fetch them.

### Recipe B — Cloudflare R2 (for public-URL hosting)

Use this if you specifically want the frames at *public* URLs (e.g. for
embedding in a blog post or external doc, not just Notion). Only suitable
for ingesting public videos.

1. Create an R2 bucket in your Cloudflare account, enable the managed
   `r2.dev` public domain (or attach a custom one), and create an R2 API
   token with read+write on the bucket.
2. Fill the `VIDEOSKILL_R2_*` vars in `.env` (see `.env.example` for the list).
3. Upload:
   ```bash
   .venv/bin/python scripts/upload-frames-to-r2.py library/<creator>/<slug>
   ```
   The script prints a JSON map of `filename → public URL` you can paste
   into Notion's Markdown image syntax (`![alt](url)`) anywhere.

The provided script targets R2 because its free tier is generous, but the
upload step is just "put JPGs at a public URL". Drop-in alternatives:

- **AWS S3** with a public bucket policy — battle-tested, costs pennies.
- **Backblaze B2** with a public bucket — free 10GB, S3-compatible.
- **DigitalOcean Spaces** — S3-compatible, paid.
- **GitHub raw URLs** — commit frames to a public repo and reference
  `raw.githubusercontent.com/...`. No service to manage, slow-ish at scale.

Google Drive is *technically* possible via public-share links, but Google
has been progressively restricting direct image hotlinking from Drive —
not recommended.

The only requirements for any swap-in: URL must be (a) fetchable without
auth and (b) stable.

### A worked example

*"Daniel Priestley — Why You Must Build a YouTube Channel (SOP)"* was
authored end-to-end with this flow from Daniel Priestley's
[*Why You Must Build a YouTube Channel*](https://www.youtube.com/watch?v=RoXlS4S0WeA)
(21 min): a Source block, a TL;DR, then the SOP in three phases with 12
whiteboard frames embedded at their correct steps via Notion file_uploads,
every claim citation-linked back to the library entry. Roughly 5 minutes
from URL to published page once the library entry was ingested. (The page
lives in the maintainer's private workspace; the exact structure it follows
is codified in `skills/publish-sop/SKILL.md`, so your output will match.)

## Layout

- `ingest.py` — CLI (`prepare`, `propose-frames`, `finalize`)
- `lib/` — Python helpers (download, transcribe, frames, meta, index)
- `skills/watch-worth-it/` — cross-agent triage skill (INGEST/PARTIAL/SKIP)
- `skills/publish-sop/` — cross-agent skill: video URL in → Notion page out
- `scripts/upload-frames-to-notion.py` — manual: frames → Notion private storage
- `scripts/upload-frames-to-r2.py` — manual: frames → public URLs
- `library/<creator-or-topic>/<slug>/` — ingested content (gitignored)
- `CLAUDE.md` — agent instructions + auto-generated library index
- `tests/` — pytest suite (no network; ffmpeg-synthesised clips)
- `docs/superpowers/` — design specs and implementation plans

## Notes

- `library/` is gitignored on purpose — transcripts and frames are
  copyright-sensitive, keep them local.
- `load-secrets.sh` is the maintainer's bws-based shortcut for loading the same
  env vars from Bitwarden Secrets Manager. You don't need it; `.env` works fine.
