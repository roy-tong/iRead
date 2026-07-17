#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IREAD_HOME="${IREAD_HOME:-$HOME/.config/iread}"
CODEX_BIN="${CODEX_BIN:-}"

if [[ -z "$CODEX_BIN" && -x "/Applications/ChatGPT.app/Contents/Resources/codex" ]]; then
  CODEX_BIN="/Applications/ChatGPT.app/Contents/Resources/codex"
fi
if [[ -z "$CODEX_BIN" ]]; then
  CODEX_BIN="$(command -v codex || true)"
fi
if [[ -z "$CODEX_BIN" || ! -x "$CODEX_BIN" ]]; then
  printf 'Codex CLI not found. Install Codex or set CODEX_BIN.\n' >&2
  exit 2
fi

install -d "$IREAD_HOME"
printf '%s\n' "$ROOT" > "$IREAD_HOME/repository-root"

"$CODEX_BIN" plugin marketplace add "$ROOT/integrations/codex" --json
"$CODEX_BIN" plugin add iread@iread --json
"$ROOT/bin/iread" doctor --surface codex

printf '\niRead is installed for Codex. Start a new Codex task before using it.\n'
