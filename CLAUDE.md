# VideoSkill library

Library of expert video content. Each video lives in `library/<creator-or-topic>/<slug>/`
with `meta.json`, `transcript.md`, `summary.md`, `extracted.md`, and `frames/`.

## How to use this library

When the user asks about a creator's content (e.g. "what would Daniel Priestly say about
LinkedIn posts"):

1. Skim the auto-index below to spot the relevant subfolder.
2. `grep -l <topic> library/<sub>/*/summary.md library/<sub>/*/extracted.md` to find
   matching videos quickly. `extracted.md` is where frameworks, templates, and quotes live;
   `summary.md` is the lighter overview.
3. Read the matching `summary.md` and `extracted.md` files.
4. Open `transcript.md` only if you need exact wording — quote with the `[mm:ss]` timestamp.
5. If the question is visual, look at `frames/` for the relevant timestamp.
6. Answer with citations like `(daniel-priestly/kpoi-five-ps, 14:32)` so the user can jump
   back to source.

## How to ingest new content

1. `source ./load-secrets.sh` to load `GROQ_API_KEY` from bws.
2. `source .venv/bin/activate`.
3. Tell Claude in this folder, e.g. *"ingest these URLs into daniel-priestly: <URLs>"*.

The Python helpers do mechanical work; Claude does summarisation and frame-timestamp
selection. See `docs/superpowers/specs/2026-04-29-videoskill-design.md` for the design
and `docs/superpowers/plans/2026-04-29-videoskill-implementation.md` for the build.

<!-- BEGIN AUTO-INDEX -->
## Library

*Empty. Run an ingest to populate.*

<!-- END AUTO-INDEX -->
