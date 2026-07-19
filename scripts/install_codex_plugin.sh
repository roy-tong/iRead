#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IREAD_HOME="${IREAD_HOME:-$HOME/.config/iread}"
CODEX_BIN="${CODEX_BIN:-}"

printf 'Installing iRead for Codex...\n'

if [[ -z "$CODEX_BIN" && -x "/Applications/ChatGPT.app/Contents/Resources/codex" ]]; then
  CODEX_BIN="/Applications/ChatGPT.app/Contents/Resources/codex"
fi
if [[ -z "$CODEX_BIN" ]]; then
  CODEX_BIN="$(command -v codex || true)"
fi
if [[ -z "$CODEX_BIN" || ! -x "$CODEX_BIN" ]]; then
  printf 'Installation stopped: Codex CLI was not found. Open/install Codex, then rerun this command.\n' >&2
  exit 2
fi

if [[ -n "${CODEX_HOME:-}" ]]; then
  install -d "$CODEX_HOME"
fi
install -d "$IREAD_HOME"
printf '%s\n' "$ROOT" > "$IREAD_HOME/repository-root"

run_codex_step() {
  local label="$1"
  shift
  local output
  if ! output=$("$@" 2>&1); then
    printf '\nInstallation stopped while %s.\n%s\n' "$label" "$output" >&2
    printf 'No collection or schedule was activated. Fix the error and rerun: scripts/install.sh codex\n' >&2
    exit 1
  fi
  printf '  [ok] %s\n' "$label"
}

run_codex_step "registering the local iRead marketplace" \
  "$CODEX_BIN" plugin marketplace add "$ROOT/integrations/codex" --json
run_codex_step "installing the iRead plugin" \
  "$CODEX_BIN" plugin add iread@iread --json

doctor_json=$("$ROOT/bin/iread" doctor --surface codex)
if ! printf '%s' "$doctor_json" | python3 "$ROOT/scripts/doctor_summary.py"; then
  printf 'Run scripts/install.sh codex again after resolving the check above.\n' >&2
  exit 1
fi

printf '\niRead is ready. This installation did not add any example domain or source.\n'
printf 'Open a new Codex task and say, for example:\n'
printf '  Use iRead to follow battery recycling and urban climate adaptation.\n'
printf '\nCodex will show the proposed sources and report plan before anything is collected.\n'
