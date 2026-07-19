#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SURFACE="${1:-}"
EXPLICIT_TARGET="${2:-}"
IREAD_HOME="${IREAD_HOME:-$HOME/.config/iread}"

case "$SURFACE" in
  claude-code)
    TARGET="${EXPLICIT_TARGET:-${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/iread}"
    ;;
  doubao)
    TARGET="${EXPLICIT_TARGET:-${DOUBAO_SKILLS_DIR:-$HOME/.agents/skills}/iread}"
    ;;
  *)
    printf 'Usage: %s <claude-code|doubao> [skill-target]\n' "$0" >&2
    exit 2
    ;;
esac

"$ROOT/scripts/prepare_runtime.sh" >/dev/null
install -d "$IREAD_HOME" "$TARGET/references" "$TARGET/scripts"
printf '%s\n' "$ROOT" > "$IREAD_HOME/repository-root"
install -m 0644 "$ROOT/skills/iread/SKILL.md" "$TARGET/SKILL.md"
install -m 0644 "$ROOT/skills/iread/references/onboarding.md" "$TARGET/references/onboarding.md"
install -m 0644 "$ROOT/skills/iread/references/management.md" "$TARGET/references/management.md"
install -m 0755 "$ROOT/skills/iread/scripts/iread" "$TARGET/scripts/iread"
install -m 0755 "$ROOT/skills/iread/scripts/install-runtime" "$TARGET/scripts/install-runtime"

if [[ "$SURFACE" == "claude-code" ]]; then
  DOCTOR_RESULT="$(CLAUDE_SKILLS_DIR="$(dirname "$TARGET")" "$ROOT/bin/iread" doctor --surface "$SURFACE")"
else
  DOCTOR_RESULT="$(DOUBAO_SKILLS_DIR="$(dirname "$TARGET")" "$ROOT/bin/iread" doctor --surface "$SURFACE")"
fi
printf '%s' "$DOCTOR_RESULT" | "${IREAD_PYTHON_BIN:-${PYTHON_BIN:-python3}}" "$ROOT/scripts/doctor_summary.py"

printf 'iRead %s skill installed: %s\n' "$SURFACE" "$TARGET"
if [[ "$SURFACE" == "claude-code" ]]; then
  printf 'Run /iread. Restart Claude Code only if ~/.claude/skills did not exist when this session started.\n'
else
  printf 'Import this SKILL.md in Doubao if the current version does not discover ~/.agents/skills automatically.\n'
fi
