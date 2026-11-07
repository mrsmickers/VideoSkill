#!/usr/bin/env bash
# VideoSkill SessionStart hook.
#
# library/ is gitignored, so worktrees start empty. This script symlinks each
# library/<creator>/ subfolder from the main checkout into the worktree, so
# grep/Read/lib.index see the same content as main.

case "$PWD" in
  */VideoSkill/.claude/worktrees/*) ;;
  *) exit 0 ;;
esac

MAIN_LIB="${PWD%%/.claude/worktrees/*}/library"
[ -d "$MAIN_LIB" ] || exit 0

for entry in "$MAIN_LIB"/*/; do
  [ -d "$entry" ] || continue
  name=$(basename "$entry")
  target="library/$name"
  if [ ! -e "$target" ]; then
    ln -s "$entry" "$target"
  fi
done

listing=$(ls library 2>/dev/null | grep -v '^\.gitkeep$' | tr '\n' ' ')
if [ -n "$listing" ] && command -v jq >/dev/null 2>&1; then
  jq -n --arg ctx "VideoSkill library symlinked from main checkout. Subfolders available: ${listing}. Use ./library/ as normal for grep/Read. The auto-index in CLAUDE.md may be stale — \`python -m lib.index\` regenerates it." \
    '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
fi
exit 0
