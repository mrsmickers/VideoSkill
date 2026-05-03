# VideoSkill

Turn almost any public video into a fully-cited knowledge artifact:
timestamped transcript, structured summary, extracted methodology with
verbatim quotes, and key frames at the moments that mattered.

Think of it as Loom's AI SOP feature with two big differences:

1. **You don't record the video — you give it a URL.** Works on most public
   video sources, not just YouTube: Vimeo, Twitter/X, TikTok, LinkedIn,
   Twitch, conference recordings. Anything `yt-dlp` can fetch.
2. **The output is plain markdown + JPGs you own.** No SaaS lock-in. Future
   Claude Code sessions in this folder can grep across the library to answer
   questions, write SOPs, build new skills, or publish straight to Notion
   (with frames hosted on your own Cloudflare R2 bucket — one shell command).

Each ingested video lives at `library/<creator-or-topic>/<slug>/` with:

- `transcript.md` — full timestamped transcript (Whisper-large-v3)
- `summary.md` — short overview + key points
- `extracted.md` — frameworks, templates, verbatim quotes, do's/don'ts
- `frames/` — JPG frames at the timestamps that mattered (auto-capped at
  1600px so Claude can review many in one go)
- `meta.json` — url, title, channel, duration, ingest date

The mechanical work (download, transcribe, extract frames) is Python. The
cognitive work (write the summary, pick frame timestamps, compose SOPs)
runs inside your Claude Code session — covered by your subscription, not
metered API calls.

## What it costs

- **Groq Whisper-large-v3** for transcription: ~$0.04 per audio-hour. A
  30-video batch averaging an hour each is roughly £1.
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
- A Groq API key for `whisper-large-v3` transcription (sign up at
  [console.groq.com](https://console.groq.com))
- Claude Code installed (the cognitive work runs inside a Claude Code session)

## Setup

```bash
# 1. Install Python deps in a venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure secrets — copy the template and fill in GROQ_API_KEY
cp .env.example .env
$EDITOR .env

# 3. Load env vars into your current shell
set -a; source .env; set +a

# 4. Open Claude Code in this folder
claude
```

Then in Claude Code: *"ingest these URLs into daniel-priestley: <URLs>"*. Claude
runs `ingest.py prepare` for each URL, reads the transcripts, writes
`summary.md` + `extracted.md`, picks frame timestamps, and runs `ingest.py
finalize`.

After ingesting, the top-level `CLAUDE.md` is regenerated as an index of the
library so a future Claude Code session sees the whole library on chat open.

## Asking the library questions

Open Claude Code in this folder and ask, e.g. *"what would Daniel Priestley say
about LinkedIn posts?"* Claude reads the index in `CLAUDE.md`, greps
`summary.md` / `extracted.md` for matches, opens the relevant files, and
answers with citations like `(daniel-priestley/<slug>, 14:32)`.

## Optional — publish a slug folder as a Notion SOP

Once a library entry exists, you can ask Claude Code in this folder to
compose a Notion SOP from it: `extracted.md` becomes the spine, frames
slot in next to the relevant step. Two upload paths ship with the project,
chosen by privacy:

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

The *Daniel Priestley — Why You Must Build a YouTube Channel* SOP page in
the maintainer's Notion workspace was authored end-to-end this way: 12
frames embedded at their correct SOP steps, all citations linked back to
the library entry. Roughly 5 minutes from URL to published page once the
library entry was ingested.

## Layout

- `ingest.py` — two-phase CLI (`prepare`, `finalize`)
- `lib/` — Python helpers (download, transcribe, frames, meta, index)
- `scripts/upload-frames-to-notion.py` — frames → Notion private storage (default)
- `scripts/upload-frames-to-r2.py` — frames → public URLs (alternative)
- `library/<creator-or-topic>/<slug>/` — ingested content (gitignored)
- `CLAUDE.md` — auto-generated library index, loaded by Claude Code on chat open
- `docs/superpowers/specs/` — original design doc
- `docs/superpowers/plans/` — implementation plan used to scaffold the project

## Notes

- `library/` is gitignored on purpose — transcripts and frames are
  copyright-sensitive, keep them local.
- `load-secrets.sh` is the maintainer's bws-based shortcut for loading the same
  env vars from Bitwarden Secrets Manager. You don't need it; `.env` works fine.
