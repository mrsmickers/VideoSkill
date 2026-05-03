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

# --- Groq whisper key (entry name 'Groq API Key', with spaces) ---
_groq_value=$(bws secret list --output json | jq -r '.[] | select(.key=="Groq API Key") | .value' | head -n 1)
if [ -z "${_groq_value:-}" ]; then
  echo "ERROR: secret 'Groq API Key' not found in bws" >&2
  unset _groq_value
  return 1 2>/dev/null || exit 1
fi
export GROQ_API_KEY="$_groq_value"
unset _groq_value

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

if [ "${_r2_loaded:-0}" = "1" ]; then
  unset _r2_loaded
  echo "Loaded from bws: GROQ_API_KEY, VIDEOSKILL_R2_ACCESS_KEY_ID, VIDEOSKILL_R2_SECRET_ACCESS_KEY."
else
  echo "Loaded from bws: GROQ_API_KEY.  (R2 secrets not found — scripts/upload-frames-to-r2.py won't work until 'VIDEOSKILL R2 secrets' is added.)"
fi
