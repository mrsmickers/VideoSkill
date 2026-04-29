# VideoSkill — design

**Date:** 2026-04-29
**Status:** Awaiting implementation plan
**Owner:** Simon Smyth

## Goal

Build a personal library of expert YouTube content (Daniel Priestly, PPC experts, etc.) that is searchable, queryable in fresh Claude Code chats, and usable as raw material for creating new skills. Aim for batches of ~30 videos at a time.

## Non-goals

- Cron-driven unattended ingestion. Ingestion is driven from a Claude Code session for now; headless mode can come later.
- Cross-machine sync of the library. Local disk only.
- Public sharing of transcripts/summaries (copyright-sensitive).
- Vector search / embeddings. Filesystem + grep + Claude reading is sufficient at this scale.

## Architecture

Three pieces:

1. **Upstream `/watch` skill** (`bradautomates/claude-video`) — installed via Claude Code plugin marketplace. Used for ad-hoc single-video Q&A. Not part of the library workflow but worth having.
2. **`ingest.py`** (Python CLI) — does the mechanical work: download via `yt-dlp`, transcribe via Groq `whisper-large-v3`, extract frames via `ffmpeg`. Does **not** call Claude or the Anthropic API directly.
3. **Top-level `CLAUDE.md`** in `~/Projects/VideoSkill/` — auto-loaded library index. Lets a fresh Claude Code chat in this folder see the whole library without explanation.

The cognitive work (summarisation, methodology extraction, frame timestamp picking) is done by the **calling Claude Code session** (or a subagent it dispatches per-video). This keeps the work covered by Claude Code subscription rather than metered API calls.

**Implementation note:** because mechanical and cognitive steps interleave, the Python side will not be a single CLI that runs end-to-end. It will either be (a) `lib/` modules with their own thin CLIs that Claude invokes turn-by-turn, or (b) a two-phase `ingest.py` that exits after transcription and is re-invoked with frame timestamps to finalise. Either is acceptable; the choice belongs in the implementation plan, not the spec. Below, "ingest.py" refers to whatever orchestration the plan settles on.

## Folder layout

```
~/Projects/VideoSkill/
├── CLAUDE.md                   # Library index (auto-loaded by Claude Code)
├── README.md
├── ingest.sh                   # bws wrapper -> ingest.py
├── ingest.py                   # Orchestrator
├── requirements.txt
├── .venv/                      # Python venv (gitignored)
├── .gitignore
├── .logs/                      # Per-run logs (gitignored)
├── lib/                        # Python helpers
│   ├── __init__.py
│   ├── download.py             # yt-dlp wrapper
│   ├── transcribe.py           # Groq whisper wrapper
│   ├── frames.py               # ffmpeg frame extraction
│   ├── paths.py                # Slug + folder logic
│   └── index.py                # Rebuilds CLAUDE.md from disk
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-29-videoskill-design.md
└── library/                    # Gitignored — copyright-sensitive
    ├── daniel-priestly/
    │   └── kpoi-five-ps/
    │       ├── meta.json       # url, title, channel, duration, ingest_date, source_hash
    │       ├── transcript.md   # Full timestamped transcript
    │       ├── summary.md      # 200-word overview + 5-10 timestamped key points
    │       ├── extracted.md    # Frameworks, steps, templates, quote bank
    │       └── frames/         # Frames at the timestamps that mattered
    │           ├── 00-30.jpg
    │           └── 02-15.jpg
    └── ppc/
        └── ...
```

## Per-video ingestion flow

For each URL:

1. Wrapper script `ingest.sh` fetches `Grok_API_Key` via `bws` → exports as `GROQ_API_KEY` for the run.
2. Hash the URL → check `library/<subfolder>/<slug>/meta.json`. If present, skip (idempotence / resume).
3. `yt-dlp` → download mp4 + JSON metadata into a temp dir.
4. `ffmpeg` → extract audio as 16kHz mono wav.
5. Groq `whisper-large-v3` → timestamped transcript. Write `transcript.md`.
6. **Calling Claude session** (or subagent) reads the transcript and produces:
   - `summary.md` — 200-word overview + 5-10 timestamped key points.
   - `extracted.md` — named frameworks, step-by-step processes, verbatim templates/scripts, verbatim quotes (with timestamps), explicit do's/don'ts.
   - List of 5-15 frame timestamps worth keeping.
7. `ffmpeg` → extract frames at those timestamps into `frames/`.
8. Write `meta.json` (url, title, channel, duration, ingest_date, source_hash).
9. `lib/index.py` → regenerate top-level `CLAUDE.md` from all `meta.json` + `summary.md` files.
10. Delete the source mp4 and wav. Audio + transcript are already captured; full video isn't worth ~500MB × 30.

## Batch interface

```bash
# Single video, interactive
~/Projects/VideoSkill/ingest.sh "https://youtu.be/VIDEO_ID" --to daniel-priestly

# Batch from a URL list (one URL per line, # for comments, blank lines ignored)
~/Projects/VideoSkill/ingest.sh --from urls.txt --to daniel-priestly
```

All videos in a single run go to the same `--to` subfolder. For a mixed run, do two runs.

A batch of 30 takes ~3-5 hours wall-clock. The Claude Code session must remain open while it runs, since cognitive work happens in-session — Simon can leave the laptop running but cannot fully detach. Truly unattended (`nohup` / `claude -p` headless / cron) is a future enhancement.

Resume: re-running the same command after interruption picks up where it left off (step 2 idempotence check).

## Retrieval pattern

Open Claude Code in `~/Projects/VideoSkill/`. The top-level `CLAUDE.md` auto-loads.

When the user asks "what would Priestly say about LinkedIn posts":

1. Scan the index in `CLAUDE.md` to identify likely-relevant videos.
2. `grep -l linkedin library/daniel-priestly/*/summary.md library/daniel-priestly/*/extracted.md`.
3. Read matching `summary.md` and `extracted.md` files (small, fast).
4. Open relevant `transcript.md` at timestamps from the summary if exact quotes are needed.
5. If the question is visual, read frames from `frames/`.
6. Synthesise with citations like `(daniel-priestly/kpoi-five-ps, 14:32)`.

**No bespoke retrieval skill needed.** Standard Claude Code grep/read tools handle this once `CLAUDE.md` is in place.

## Skill creation workflow

User says: *"create a skill from Priestly's LinkedIn material called `priestly-linkedin-posts`"*.

1. Read every `extracted.md` under `library/daniel-priestly/` matching LinkedIn topics.
2. Distil into a coherent methodology (frameworks, hooks, post structures, do's/don'ts).
3. Invoke the existing `anthropic-skills:skill-creator` skill to package as a `.skill`.
4. User decides whether to install locally or share via skill-share.

The library produces well-organised raw material; `skill-creator` does the packaging. No bespoke "skill builder" infra needed.

The quality bar for `extracted.md` is high because of this workflow — the per-video subagent prompt is tuned for: named frameworks, verbatim templates/scripts, verbatim quotes with timestamps, explicit do's/don'ts. Not generic summaries.

## Costs

- **Groq `whisper-large-v3`**: ~$0.04 per audio-hour. 30 hours of video ≈ **$1.20**.
- **Claude (cognitive work)**: covered by Simon's Claude Code subscription. £0 metered.
- **yt-dlp / ffmpeg / disk**: free.
- **Total per 30-video batch**: ~£1 metered.
- **Disk per video**: ~5-10MB (transcript + summary + extracted + ~10 frames). 30 videos ≈ 150-300MB.

## Prerequisites

Already in place:
- `yt-dlp 2026.03.17` (Homebrew)
- `ffmpeg 8.1` (Homebrew)
- `python3` (Homebrew)
- `~/Projects/VideoSkill/` directory

To verify or install:
- `bws` CLI installed and authenticated (`which bws`, `bws --version`).
- bws secret named `Grok_API_Key` retrievable. **Note: spelled "Grok" not "Groq" in bws — preserved as-is.**
- Python venv + `groq` SDK in `~/Projects/VideoSkill/.venv/`.
- Upstream `/watch` skill via `/plugin marketplace add bradautomates/claude-video` then `/plugin install watch@claude-video`.

## Install order

1. Verify `bws` access — fetch `Grok_API_Key`. Fix the secret name if needed before continuing.
2. Scaffold project — `requirements.txt`, `.venv/`, `lib/` package, empty `CLAUDE.md` skeleton, `library/` directory, `.gitignore`, `.logs/`, local `git init`.
3. Build `lib/` helpers (`download.py`, `transcribe.py`, `frames.py`, `paths.py`, `index.py`).
4. Build the orchestration layer (single CLI with phases, or thin per-helper CLIs called by Claude — implementation plan to choose).
5. Build the bws wrapper that fetches `Grok_API_Key` and exports `GROQ_API_KEY` for the run.
6. Write top-level `CLAUDE.md` skeleton (rebuilt from disk after each ingest).
7. (Optional) Tiny `/ingest-video` Claude Code skill at `~/Projects/VideoSkill/.claude/skills/ingest-video/` for interactive single-video use from any chat.
8. Smoke test on one short (~5-10 min) video. Inspect all four output files + frames. Iterate on summary/extraction prompt.
9. First real batch (Priestly first — easiest test case). Leave the session running. Review output.
10. Run remaining creators.

## Open items

- bws CLI install status — verify before scaffolding.
- First smoke-test video URL — Simon to provide a short Priestly clip, or implementer picks one.
- Prompt tuning for `summary.md` and `extracted.md` generation — done iteratively at step 8 of install.
- Subagent vs same-context for per-video cognitive work — start with subagents (clean context, parallel-friendly), measure, fall back to inline if subagent overhead is high.

## Decisions deferred

- Headless / cron-driven ingestion. Future enhancement.
- Cross-machine library sync (iCloud, syncthing, etc.). Future.
- Vector search. Not needed at current scale.
- Library-wide tagging schema. Let it emerge from usage; metadata fields can be added to `meta.json` later without breaking existing entries.
