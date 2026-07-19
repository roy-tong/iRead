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
    DOCTOR_RESULT="$("$ROOT/bin/iread" doctor --surface workbuddy)"
    "${IREAD_PYTHON_BIN:-${PYTHON_BIN:-python3}}" -c '
import json
import sys

result = json.load(sys.stdin)
summary = result.get("summary", {})
if result.get("status") == "ready":
    passed = summary.get("passed", 0)
    warnings = summary.get("warnings", 0)
    warning_label = "warning" if warnings == 1 else "warnings"
    print(f"iRead check passed: {passed} passed, {warnings} {warning_label}.")
    raise SystemExit(0)
print("iRead check failed:", file=sys.stderr)
for check in result.get("checks", []):
    if check.get("status") == "fail":
        name = check.get("name")
        detail = check.get("detail")
        print(f"- {name}: {detail}", file=sys.stderr)
raise SystemExit(1)
' <<<"$DOCTOR_RESULT"
    ;;
  *)
    usage
    exit 2
    ;;
esac
