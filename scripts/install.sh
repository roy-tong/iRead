#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  printf 'Usage:\n' >&2
  printf '  %s codex\n' "$0" >&2
  printf '  %s workbuddy <work-buddy-root> [--force]\n' "$0" >&2
}

case "${1:-}" in
  codex)
    [[ $# -eq 1 ]] || { usage; exit 2; }
    if [[ -n "${CODEX_BIN:-}" ]]; then
      [[ -x "$CODEX_BIN" ]] || {
        printf 'Installation stopped: CODEX_BIN is not executable: %s\n' "$CODEX_BIN" >&2
        exit 2
      }
    elif [[ ! -x "/Applications/ChatGPT.app/Contents/Resources/codex" ]] \
      && ! command -v codex >/dev/null 2>&1; then
      printf 'Installation stopped: Codex CLI was not found. Open/install Codex, then rerun this command.\n' >&2
      exit 2
    fi
    "$ROOT/scripts/prepare_runtime.sh"
    exec "$ROOT/scripts/install_codex_plugin.sh"
    ;;
  workbuddy)
    [[ $# -ge 2 && $# -le 3 ]] || { usage; exit 2; }
    "$ROOT/scripts/prepare_runtime.sh"
    "$ROOT/integrations/work-buddy/install.sh" "$2" "${3:-}"
    "$ROOT/bin/iread" doctor --surface workbuddy
    ;;
  *)
    usage
    exit 2
    ;;
esac
