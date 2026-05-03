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

## Optional — host frames publicly + publish to Notion

For sharing SOPs with embedded frames (e.g. as Notion pages), the frames
need to live somewhere with public URLs. The provided
`scripts/upload-frames-to-r2.py` ships with Cloudflare R2 wired up because
its free tier covers this comfortably, but the upload step is just "put
JPGs somewhere they can be fetched by URL" — any public-bucket service
works.

### Recipe (using R2's free tier)

1. Create an R2 bucket in your Cloudflare account, enable the managed
   `r2.dev` public domain (or attach a custom one), and create an R2 API
   token with read+write on the bucket.
2. Fill the `VIDEOSKILL_R2_*` vars in `.env`.
3. Upload:
   ```bash
   .venv/bin/python scripts/upload-frames-to-r2.py library/<creator>/<slug>
   ```
4. The script prints a JSON map of `filename → public URL`. Pipe it into
   Claude Code and ask it to compose a Notion page with the frames embedded
   at the right SOP steps. The `extracted.md` file in the slug folder is the
   spine of the SOP; frames slot in next to the relevant whiteboard / step.

A worked example: the *Daniel Priestley — Why You Must Build a YouTube
Channel* SOP page in the maintainer's Notion workspace was authored end-to-end
this way — 12 frames embedded at their correct SOP steps, all citations linked
back to the library entry. Took roughly 5 minutes from URL to published page
once the library entry was ingested.

### Drop-in storage alternatives

The provided script targets R2 because the free tier is generous and the
managed `r2.dev` domain handles serving with no extra setup. Swap in any of
these by changing the endpoint URL (and the env var values):

- **AWS S3** with a public bucket policy — battle-tested, costs pennies.
- **Backblaze B2** with a public bucket — free 10GB, S3-compatible.
- **DigitalOcean Spaces** — S3-compatible, paid.

If you don't want to set up *any* bucket service, you can also commit
frames to a public GitHub repo and use the `raw.githubusercontent.com`
URLs — no service to manage, no API token to issue, slow-ish at scale but
fine for occasional SOPs. Google Drive is *technically* possible via
public-share links, but Google has been progressively restricting direct
image hotlinking from Drive — not recommended.

The only requirements: the URL must be (a) fetchable without auth and (b)
stable. Anything that satisfies those works.

### ⚠️ Privacy caveat — public videos only

**Frames uploaded to public storage are accessible to anyone with the URL.**
That's fine for ingesting public videos (you're republishing material that
was already public). It is *not* fine for private or proprietary content —
internal Loom recordings, paid courses you've licensed, client SOPs,
NDA-bound conference talks.

If you want VideoSkill on private content, two workarounds:

1. **Skip the public-URL flow entirely.** The library entry stays on your
   filesystem; future Claude Code sessions in this folder can still read
   `library/<slug>/frames/*.jpg` locally and answer questions about the
   content. You just don't get embedded images in published Notion pages.
2. **Upload frames directly into Notion via its API.** Notion's
   `/v1/file_uploads` endpoint accepts JPGs into your workspace's private
   file storage, where they're only accessible to authenticated workspace
   members. There isn't a built-in script for this in VideoSkill yet — PRs
   welcome, or ask Claude Code to write one for you in the moment using
   `scripts/upload-frames-to-r2.py` as the structural template.

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
