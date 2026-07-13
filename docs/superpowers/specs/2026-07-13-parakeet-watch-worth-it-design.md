# VideoSkill: local Parakeet transcription, claude-video raids, and /watch-worth-it triage skill

**Date:** 2026-07-13
**Status:** Approved pending review
**Context:** Review of [bradautomates/claude-video](https://github.com/bradautomates/claude-video) (MIT) identified raid-worthy mechanics. Simon's decisions: replace Groq entirely with local Parakeet v2; triage skill is transcript-first with optional frames; library ingests always use Parakeet (captions never substitute).

## Goals

1. **Local transcription.** Drop the Groq API dependency; transcribe with NVIDIA `parakeet-tdt-0.6b-v2` running locally on Apple Silicon via [parakeet-mlx](https://github.com/senstella/parakeet-mlx). Free, fast (~1 min per audio-hour), English-only (sufficient), punctuation + timestamps included.
2. **Raid claude-video mechanics** into our pipeline: download hardening, capped-resolution downloads, scene-change frame proposals, VTT caption parsing.
3. **`/watch-worth-it`** — a self-contained, cross-agent (Claude Code / Codex / Hermes) triage skill that answers "is this video worth a full library ingest?" cheaply, without downloading video by default.

## Non-goals

- No general-purpose "/watch any video and answer questions" clone — triage only (extend later if wanted).
- No skill-share/marketplace packaging.
- No captions-as-transcript for library ingests (quality bar: Parakeet only).
- No multi-language support (Parakeet v2 is English-only by design choice).

## Workstream A — transcription backend swap (Groq → parakeet-mlx)

**`lib/transcribe.py`:**
- Remove the `groq` SDK import, retry helpers, and `TranscribeError` Groq paths.
- `transcribe_audio(audio_path)` uses `parakeet_mlx.from_pretrained(MODEL)` with a module-level lazy singleton (model loads once per process). Long audio is handled with parakeet-mlx's chunking parameters (`chunk_duration`/`overlap_duration` — exact values confirmed against the library API during implementation; target ~120 s chunks, ~15 s overlap).
- Sentence-level results map to the existing `Segment(start, end, text)` NamedTuple; `format_transcript()` unchanged, so `transcript.md` output format is identical.
- Model: `mlx-community/parakeet-tdt-0.6b-v2` (constant), overridable via `VIDEOSKILL_PARAKEET_MODEL` env var. ~1.2 GB one-time download to the Hugging Face cache on first run.
- `extract_audio()` unchanged (mono 16 kHz mp3 — parakeet-mlx accepts it).
- Missing-dependency handling: `ImportError` → `TranscribeError` with the exact fix command (`.venv/bin/pip install parakeet-mlx`).

**Packaging/docs:**
- `requirements.txt`: remove `groq`, add `parakeet-mlx` with environment marker `; sys_platform == "darwin" and platform_machine == "arm64"` so installs don't break on other platforms (transcription simply unavailable there — accepted trade-off of removing Groq).
- `.env.example`: remove `GROQ_API_KEY`; `load-secrets.sh` and CLAUDE.md/README setup steps updated (no API key needed for transcription; note the one-time model download).
- CI (`.github/workflows`): tests must pass on Linux runners — parakeet is mocked in tests (see Testing).

## Workstream B — download raid (`lib/download.py`)

- **Hardening** (their issue #2 fix): insert `--` before the URL in the yt-dlp argv; reject sources starting with `-`.
- **Speed:** format selector `bv*[height<=1080]+ba/b[height<=1080]/bv+ba/b` (frames are capped at 1600 px anyway; 1080p is ample for whiteboard text) and `-N 8` concurrent fragment downloads.
- Behaviour otherwise unchanged (`--write-info-json`, mp4 merge, restricted filenames).

## Workstream C — frame-picking assist

- **`ingest.py propose-frames <slug_folder>`** — new subcommand. Runs ffmpeg scene-change detection (`select='gt(scene,0.20)'` + `showinfo`, timestamps parsed from stderr — raided from their `frames.py`) against `.source.mp4` and prints candidate timestamps as `mm:ss` with scene scores. No files written; purely advisory. Works only between `prepare` and `finalize` (while `.source.mp4` exists); clear error otherwise.
- **Near-duplicate warning in `finalize`:** after extracting chosen frames, a dedup pass (16×16 grayscale thumbnails via one ffmpeg call, mean-absolute-difference vs last kept, threshold 2.0 — raided from their `frames.py`) prints a warning listing near-identical pairs. Warning only; frames are never dropped (curation stays with Claude).
- **CLAUDE.md step 5 guidance:** add scanning the transcript for deictic cues ("as you can see", "look here", "notice this") and running `propose-frames` as inputs to timestamp picking.

## Workstream D — `/watch-worth-it` skill (`skills/watch-worth-it/`)

Self-contained folder, agentskills-style, so one symlink installs it on any host:

```
skills/watch-worth-it/
├── SKILL.md            # harness-agnostic contract (SKILL_DIR resolved from where SKILL.md was Read)
└── scripts/
    └── triage.py       # pure stdlib — needs only yt-dlp + ffmpeg binaries, no venv
```

**`triage.py` flow (default, no video download):**
1. `yt-dlp --skip-download --write-info-json --write-subs --write-auto-subs --sub-langs "en.*" --sub-format vtt` (captions-first raid, incl. `--` hardening).
2. Parse VTT → segments; collapse YouTube rolling-duplicate cues (parser raided from their `transcribe.py`, MIT attribution in the file header).
3. Print a report: metadata (title, channel, duration, upload date, view count if present), transcript stats (word count, words/min), and the full timestamped transcript.
4. No captions available → say so explicitly and suggest `--frames` or a full `prepare` (which uses Parakeet). No Whisper fallback here — triage stays dependency-free.

**`--frames N` (optional visual pass):** downloads video capped at 480p, extracts N (default 6) scene-change frames at 512 px into a temp dir, prints paths with `t=mm:ss` markers for the agent to Read. Used when visual density matters (whiteboard-heavy creators).

**SKILL.md judgment rubric (the agent's job, not the script's):**
- Read the report; skim the library index (`CLAUDE.md` at repo root) and grep `summary.md`/`extracted.md` for topic overlap.
- Score: framework density (named models, step-by-steps, templates), novelty vs library, specificity vs fluff (sponsor reads, recycled intros), visual payload (does the transcript reference diagrams/whiteboards?).
- Verdict: **INGEST** (+ suggested `--to` subfolder) / **PARTIAL** (specific timestamp ranges worth it) / **SKIP** (+ one-line reason).
- Cleanup: remove the temp working dir unless follow-ups are expected.

**Cross-agent install:** README section with one-liners — `ln -s <repo>/skills/watch-worth-it ~/.claude/skills/watch-worth-it` (Claude Code) and `~/.codex/skills/` (Codex); Hermes per its skills directory. SKILL.md uses the "resolve SKILL_DIR from the path of the SKILL.md you just read" pattern (raided from their SKILL.md) rather than any harness-specific env var.

## Testing

- Existing pytest suite extended; no network in tests.
- Parakeet: `transcribe_audio` tested with a mocked `parakeet_mlx` module (injected via `sys.modules`) — asserts segment mapping and error paths. CI never downloads the model.
- Download: argv assertions (hardening flags, format cap) on a mocked `subprocess.run`.
- propose-frames / dedup: ffmpeg-synthesised clips (raid their `tests/conftest.py` fixture approach) — a colour-bars clip with a hard cut for scene detection; identical-frame sequences for dedup.
- triage.py: VTT fixtures for parser + rolling-dedupe; report formatting golden test.

## Rollback

Single branch, small logical commits per workstream. Groq removal is one commit — revert restores API transcription if Parakeet disappoints.

## Verification

1. `pytest -q` green.
2. End-to-end: re-ingest one short public video (`prepare` → transcript quality check vs an existing Groq-era transcript → `propose-frames` → `finalize`).
3. `/watch-worth-it` run against one YouTube URL with captions (no-download path) and once with `--frames`.
4. Codex smoke test: invoke the skill from Codex against the symlinked folder.
