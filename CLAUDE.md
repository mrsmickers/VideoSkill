# VideoSkill library

Library of expert video content. Each video lives at `library/<creator-or-topic>/<slug>/`
with `meta.json`, `transcript.md`, `summary.md`, `extracted.md`, and `frames/`.

## For agents on a fresh clone

If the **Library** section at the bottom of this file lists any videos, the
project is set up — skip to **How to use this library**.

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

### 3. Get a Groq API key from the user

Required for transcription. Free account at
[console.groq.com](https://console.groq.com); ~$0.04 per audio-hour. Then:

```bash
cp .env.example .env
# write GROQ_API_KEY=<their-key> into .env
```

### 4. Load env into the current shell

```bash
set -a; source .env; set +a
```

Confirm with `echo $GROQ_API_KEY` — should print the key (not empty).

### 5. (Optional) Cloudflare R2 setup

Only needed if the user wants `scripts/upload-frames-to-r2.py` to host frame
JPGs publicly (e.g. for embedding in Notion). If they don't ask for this,
skip — ingestion works fine without it.

If they want it: they need a Cloudflare account, an R2 bucket with the managed
`r2.dev` public domain enabled (or a custom domain), and an R2 API token with
read+write on that bucket. Fill the `VIDEOSKILL_R2_*` vars in `.env` (see
`.env.example` for the list) and re-source.

### 6. Smoke-test on a short video

Before a big batch, ingest one 5–10 minute YouTube video to validate the
pipeline. Ask the user for a URL, then follow **How to ingest new content**
below.

---

## How to use this library

When the user asks about a creator's content (e.g. *"what would Daniel
Priestley say about LinkedIn posts"*):

1. Skim the auto-index at the bottom of this file to spot the relevant
   subfolder.
2. `grep -l <topic> library/<sub>/*/summary.md library/<sub>/*/extracted.md`
   to find matching videos quickly. `extracted.md` is where frameworks,
   templates and quotes live; `summary.md` is the lighter overview.
3. Read the matching `summary.md` and `extracted.md` files.
4. Open `transcript.md` only if you need exact wording — quote with the
   `[mm:ss]` timestamp.
5. If the question is visual, look at `frames/` for the relevant timestamp.
6. Cite as `(daniel-priestley/<slug>, 14:32)` so the user can jump back to
   source.

## How to ingest new content

Make sure env is loaded first: `set -a; source .env; set +a`. Then for each
URL the user gives you:

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
   whiteboards, diagrams, key text overlays. Animated whiteboards build up
   over time, so target the *end* of each animated section, not the middle.
   Frames are auto-capped at 1600px to stay under Anthropic's many-image
   dimension limit.
6. **Finalize** — `.venv/bin/python ingest.py finalize <slug_folder> --frames "00:35,04:35,..."`.
   Extracts frames, writes `meta.json`, regenerates this `CLAUDE.md`,
   cleans up the source mp4.

Design notes: `docs/superpowers/specs/2026-04-29-videoskill-design.md`.
Build plan: `docs/superpowers/plans/2026-04-29-videoskill-implementation.md`.

<!-- BEGIN AUTO-INDEX -->
## Library

*Empty. Run an ingest to populate.*
<!-- END AUTO-INDEX -->
