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

# bws stores the Groq whisper key under the entry name 'Groq API Key' (with spaces).
_groq_value=$(bws secret list --output json | jq -r '.[] | select(.key=="Groq API Key") | .value' | head -n 1)

if [ -z "${_groq_value:-}" ]; then
  echo "ERROR: secret 'Groq API Key' not found in bws" >&2
  unset _groq_value
  return 1 2>/dev/null || exit 1
fi

export GROQ_API_KEY="$_groq_value"
unset _groq_value

echo "GROQ_API_KEY loaded from bws (Groq API Key)."
