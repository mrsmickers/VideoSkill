# VideoSkill

Personal library of expert YouTube content, ingested into searchable folders.

See `docs/superpowers/specs/2026-04-29-videoskill-design.md` for the design.

## Quick start

```bash
# 1. Load secrets
source ./load-secrets.sh

# 2. Activate venv
source .venv/bin/activate

# 3. Open Claude Code in this folder, then ask it to ingest URLs
claude
```

## Layout

- `ingest.py` — two-phase CLI (`prepare`, `finalize`)
- `lib/` — Python helpers (download, transcribe, frames, meta, index)
- `library/<creator-or-topic>/<slug>/` — ingested content (gitignored)
- `CLAUDE.md` — auto-generated library index, loaded by Claude Code on chat open
