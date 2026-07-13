---
name: watch-worth-it
version: "0.1.0"
description: Triage a video URL before ingesting it into the VideoSkill library. Fetches metadata + captions with no video download (optionally a few low-res frames), then judges whether the video is worth a full ingest — INGEST / PARTIAL / SKIP.
argument-hint: "<video-url> [--frames N]"
allowed-tools: Bash, Read
license: MIT
user-invocable: true
---

# /watch-worth-it

Decide cheaply whether a video deserves a full VideoSkill library ingest
(download → local Parakeet transcription → summary/extraction/frames), before
spending the time. Works in any agent host (Claude Code, Codex, Hermes, …).

## Resolve SKILL_DIR (before any command)

Set `SKILL_DIR` to the absolute directory containing THIS SKILL.md (your
harness reported the path when you read it). The script is always at
`SKILL_DIR/scripts/triage.py`, in every install layout — including symlinked
installs. Guard once:

```bash
SKILL_DIR="<absolute dir of the SKILL.md you just read>"
[ -f "$SKILL_DIR/scripts/triage.py" ] || echo "ERROR: triage.py not found under $SKILL_DIR"
```

## Step 0 — prerequisites (self-checking)

The script needs only `yt-dlp` and `ffmpeg` on PATH — no venv, no API keys.
It checks for them itself: **exit code 3** means something's missing and
stderr lists the exact install command per OS. Relay that to the user — or,
on macOS with Homebrew present, offer to run `brew install ffmpeg yt-dlp`
for them and re-run. Don't debug tracebacks that a missing binary would
never produce; check exit 3 first.

## Step 1 — run the triage script

```bash
python3 "$SKILL_DIR/scripts/triage.py" "<url>"
``` Default is
captions-only (no video download, a few seconds). Add `--frames 6` to also
pull a 480p copy and extract ~6 scene-change frames (use when the creator is
whiteboard/diagram-heavy and visuals decide the value). If frames were
produced, Read each listed path — they render as images.

## Step 2 — check overlap with the existing library

The report prints `library_index=` and `library_root=` lines when the skill
lives inside a VideoSkill repo (symlinks resolve to the real location). Read
the index and grep for topic overlap:

```bash
grep -il "<topic>" "<library_root>"/*/*/summary.md "<library_root>"/*/*/extracted.md
```

## Step 3 — judge

Score the transcript against four dials:

- **Framework density** — named models, numbered steps, templates, scripts.
  High density → high extract value.
- **Novelty vs library** — does the index/grep show we already cover this?
  Same creator saying the same thing again → SKIP.
- **Specificity vs fluff** — sponsor reads, recycled intros, "smash that
  like button", vague motivation → discount heavily.
- **Visual payload** — does the speaker keep referencing things on screen
  ("as you can see", "this diagram")? That raises ingest value (frames) and
  is a reason to re-run with `--frames`.

## Step 4 — verdict

Answer with exactly one of:

- **INGEST** — worth it. Give the suggested subfolder and the ready-to-run
  command: `.venv/bin/python ingest.py prepare "<url>" --to <subfolder>`
- **PARTIAL** — only sections are valuable. List the `mm:ss–mm:ss` ranges
  and what each contains; ingest is still all-or-nothing today, so say
  whether the good sections justify a full ingest anyway.
- **SKIP** — one line on why (overlap, fluff, too thin).

Always give 2–4 bullet reasons with timestamps. Never paste the full
transcript back at the user.

## Step 5 — clean up

The report's last line prints `work_dir=…`. Unless the user wants follow-ups
(e.g. an ingest next, which re-downloads anyway), `rm -rf` it.

## No captions?

The report says so explicitly. Options, in order: re-run with `--frames 6`
(visual-only triage), or — if metadata + your knowledge of the creator already
look promising — recommend going straight to a full `prepare` (local Parakeet
transcription doesn't need captions).
