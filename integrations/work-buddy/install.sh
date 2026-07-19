#!/bin/bash
set -euo pipefail

usage() {
  printf 'Usage: %s <work-buddy-root> [--force]\n' "$0" >&2
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

WORK_BUDDY_ROOT="$(cd "$1" && pwd)"
FORCE="${2:-}"
if [[ -n "$FORCE" && "$FORCE" != "--force" ]]; then
  usage
  exit 2
fi

SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SOURCE_ROOT/../.." && pwd)"
STORE_TARGET="$WORK_BUDDY_ROOT/knowledge/store/iread"
COMMAND_TARGET="$WORK_BUDDY_ROOT/.claude/commands/iread.md"

if [[ ! -d "$WORK_BUDDY_ROOT/knowledge/store" || ! -d "$WORK_BUDDY_ROOT/.claude/commands" ]]; then
  printf 'Not a WorkBuddy source tree: %s\n' "$WORK_BUDDY_ROOT" >&2
  exit 2
fi

if [[ "$FORCE" != "--force" && ( -e "$STORE_TARGET" || -e "$COMMAND_TARGET" ) ]]; then
  printf 'Adapter already exists. Re-run with --force to replace it.\n' >&2
  exit 1
fi

install -d "$STORE_TARGET"
install -m 0644 "$SOURCE_ROOT/knowledge/store/iread/batch-onboard.md" "$STORE_TARGET/multi-domain-onboard.md"
install -m 0644 "$SOURCE_ROOT/knowledge/store/iread/batch-onboard-directions.md" "$STORE_TARGET/multi-domain-onboard-directions.md"
install -m 0644 "$SOURCE_ROOT/.claude/commands/iread.md" "$COMMAND_TARGET"
printf '%s\n' "$REPO_ROOT" > "$STORE_TARGET/repository-root.txt"

printf 'Installed iRead workflow into %s\n' "$WORK_BUDDY_ROOT"
printf 'Open a new WorkBuddy task and run /iread. No knowledge-index rebuild is required.\n'
