#!/usr/bin/env bash
# Source this script (don't execute it) to populate the env with secrets fetched from bws.
# Usage:  source ./load-secrets.sh

if ! command -v bws >/dev/null 2>&1; then
  echo "ERROR: bws CLI not on PATH. Install: https://bitwarden.com/help/secrets-manager-cli/" >&2
  return 1 2>/dev/null || exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq not on PATH. brew install jq" >&2
  return 1 2>/dev/null || exit 1
fi

# Transcription is fully local (parakeet-mlx) — no API key needed to ingest.
# This script only loads publishing secrets (R2, Notion).

# --- R2 access keys (single bws entry 'VIDEOSKILL R2 secrets' with two lines:
#       R2_ACCESS_KEY_ID: <hex>
#       R2_SECRET_ACCESS_KEY: <hex>
#     Note: each `bws secret list | jq` is a fresh pipe — capturing bws output in
#     a shell variable and re-emitting breaks because bws emits literal newlines
#     inside the JSON string value, which is invalid JSON when re-parsed.)
_r2_blob=$(bws secret list --output json | jq -r '.[] | select(.key=="VIDEOSKILL R2 secrets") | .value' | head -n 5)
if [ -n "${_r2_blob:-}" ]; then
  _r2_ak=$(printf '%s\n' "$_r2_blob" | awk -F': *' '$1=="R2_ACCESS_KEY_ID"{print $2}')
  _r2_sk=$(printf '%s\n' "$_r2_blob" | awk -F': *' '$1=="R2_SECRET_ACCESS_KEY"{print $2}')
  if [ -n "${_r2_ak:-}" ] && [ -n "${_r2_sk:-}" ]; then
    export VIDEOSKILL_R2_ACCESS_KEY_ID="$_r2_ak"
    export VIDEOSKILL_R2_SECRET_ACCESS_KEY="$_r2_sk"
    _r2_loaded=1
  else
    echo "WARN: 'VIDEOSKILL R2 secrets' entry found but couldn't parse R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY out of it." >&2
  fi
fi
unset _r2_blob _r2_ak _r2_sk

# --- Notion internal-integration token (entry name 'Notion') ---
_notion_value=$(bws secret list --output json | jq -r '.[] | select(.key=="Notion") | .value' | head -n 1)
if [ -n "${_notion_value:-}" ]; then
  export VIDEOSKILL_NOTION_API_KEY="$_notion_value"
  _notion_loaded=1
fi
unset _notion_value

# --- summary ---
_loaded=""
[ "${_r2_loaded:-0}" = "1" ] && _loaded="VIDEOSKILL_R2_ACCESS_KEY_ID, VIDEOSKILL_R2_SECRET_ACCESS_KEY"
if [ "${_notion_loaded:-0}" = "1" ]; then
  [ -n "$_loaded" ] && _loaded="$_loaded, "
  _loaded="${_loaded}VIDEOSKILL_NOTION_API_KEY"
fi
if [ -n "$_loaded" ]; then
  echo "Loaded from bws: $_loaded."
else
  echo "Nothing loaded from bws — R2/Notion entries not found."
fi

# Hint on what's missing (only if it actually is):
if [ "${_r2_loaded:-0}" != "1" ]; then
  echo "  (R2 secrets not found — scripts/upload-frames-to-r2.py won't work until 'VIDEOSKILL R2 secrets' is added.)"
fi
if [ "${_notion_loaded:-0}" != "1" ]; then
  echo "  (Notion token not found — scripts/upload-frames-to-notion.py won't work until 'Notion' entry is added.)"
fi
unset _loaded _r2_loaded _notion_loaded
