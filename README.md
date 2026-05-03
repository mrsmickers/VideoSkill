# VideoSkill

Build a personal library of expert YouTube content, ingested into per-video
folders that a fresh Claude Code chat can browse and quote from.

Each video lives at `library/<creator-or-topic>/<slug>/` with:

- `meta.json` — url, title, channel, duration, ingest date
- `transcript.md` — full timestamped transcript
- `summary.md` — short overview + key points
- `extracted.md` — frameworks, templates, quotes, do's/don'ts
- `frames/` — JPG frames at the timestamps that mattered

The mechanical work (download, transcribe, frame extract) is Python. The
cognitive work (write the summary, pick frame timestamps) is done by the
calling Claude Code session — meaning it's covered by your Claude subscription
rather than metered API calls.

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

## Optional — host frames publicly + publish to Notion

`scripts/upload-frames-to-r2.py` uploads a slug folder's `frames/*.jpg` to a
Cloudflare R2 bucket and prints a JSON map of `filename -> public URL` ready to
paste into a Notion page (or anywhere else). To use it:

1. Create an R2 bucket in your Cloudflare account, enable the managed `r2.dev`
   public domain (or attach a custom one), and create an R2 API token with
   read+write on the bucket.
2. Fill the `VIDEOSKILL_R2_*` vars in `.env`.
3. Run:
   ```bash
   .venv/bin/python scripts/upload-frames-to-r2.py library/<creator>/<slug>
   ```

Ingestion works fine without this — it's only for sharing.

## Layout

- `ingest.py` — two-phase CLI (`prepare`, `finalize`)
- `lib/` — Python helpers (download, transcribe, frames, meta, index)
- `scripts/upload-frames-to-r2.py` — optional frame-hosting helper
- `library/<creator-or-topic>/<slug>/` — ingested content (gitignored)
- `CLAUDE.md` — auto-generated library index, loaded by Claude Code on chat open
- `docs/superpowers/specs/` — original design doc
- `docs/superpowers/plans/` — implementation plan used to scaffold the project

## Notes

- `library/` is gitignored on purpose — transcripts and frames are
  copyright-sensitive, keep them local.
- `load-secrets.sh` is the maintainer's bws-based shortcut for loading the same
  env vars from Bitwarden Secrets Manager. You don't need it; `.env` works fine.
