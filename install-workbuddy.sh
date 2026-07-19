#!/bin/bash
set -euo pipefail

REPOSITORY_URL="${IREAD_REPOSITORY_URL:-https://github.com/roy-tong/iRead.git}"
INSTALL_ROOT="${IREAD_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/iread}"
EXPLICIT_WORKBUDDY_ROOT="${1:-${WORKBUDDY_ROOT:-}}"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P || true)"

fail() {
  printf 'iRead installation stopped: %s\n' "$1" >&2
  exit 2
}

is_workbuddy_root() {
  [[ -d "$1/knowledge/store" && -d "$1/.claude/commands" ]]
}

add_candidate() {
  local candidate="$1"
  local existing
  [[ -n "$candidate" && -d "$candidate" ]] || return 0
  candidate="$(cd "$candidate" 2>/dev/null && pwd -P)" || return 0
  is_workbuddy_root "$candidate" || return 0
  for existing in "${WORKBUDDY_CANDIDATES[@]:-}"; do
    [[ "$existing" == "$candidate" ]] && return 0
  done
  WORKBUDDY_CANDIDATES+=("$candidate")
}

find_workbuddy_root() {
  local cursor="$PWD"
  local parent
  local base
  local store

  if [[ -n "$EXPLICIT_WORKBUDDY_ROOT" ]]; then
    is_workbuddy_root "$EXPLICIT_WORKBUDDY_ROOT" \
      || fail "the selected folder is not a WorkBuddy project: $EXPLICIT_WORKBUDDY_ROOT"
    cd "$EXPLICIT_WORKBUDDY_ROOT" && pwd -P
    return
  fi

  while :; do
    add_candidate "$cursor"
    parent="$(dirname "$cursor")"
    [[ "$parent" == "$cursor" ]] && break
    cursor="$parent"
  done

  for base in \
    "$HOME/work-buddy" \
    "$HOME/WorkBuddy" \
    "$HOME/Documents/work-buddy" \
    "$HOME/Projects/work-buddy" \
    "$HOME/Developer/work-buddy" \
    "$HOME/Code/work-buddy" \
    "$HOME/src/work-buddy"; do
    add_candidate "$base"
  done

  for base in "$HOME/Documents" "$HOME/Projects" "$HOME/Developer" "$HOME/Code" "$HOME/src"; do
    [[ -d "$base" ]] || continue
    while IFS= read -r store; do
      add_candidate "${store%/knowledge/store}"
    done < <(find "$base" -type d -path '*/knowledge/store' -prune 2>/dev/null)
  done

  if [[ ${#WORKBUDDY_CANDIDATES[@]} -eq 1 ]]; then
    printf '%s\n' "${WORKBUDDY_CANDIDATES[0]}"
    return
  fi
  if [[ ${#WORKBUDDY_CANDIDATES[@]} -gt 1 ]]; then
    printf 'More than one WorkBuddy project was found:\n' >&2
    printf '  %s\n' "${WORKBUDDY_CANDIDATES[@]}" >&2
    fail 'rerun with: curl -fsSL https://raw.githubusercontent.com/roy-tong/iRead/main/install-workbuddy.sh | bash -s -- "/path/to/work-buddy"'
  fi
  fail 'WorkBuddy was not found. Open its project folder in WorkBuddy and run the install sentence again.'
}

command -v git >/dev/null 2>&1 || fail 'Git is required.'
command -v python3 >/dev/null 2>&1 || fail 'Python 3 is required.'

WORKBUDDY_CANDIDATES=()
WORKBUDDY_ROOT_RESOLVED="$(find_workbuddy_root)"

if [[ -n "${IREAD_SOURCE_ROOT:-}" ]]; then
  IREAD_ROOT="$(cd "$IREAD_SOURCE_ROOT" && pwd -P)"
  [[ -x "$IREAD_ROOT/scripts/install.sh" ]] || fail "invalid IREAD_SOURCE_ROOT: $IREAD_ROOT"
elif [[ -x "$SCRIPT_ROOT/scripts/install.sh" ]]; then
  IREAD_ROOT="$SCRIPT_ROOT"
elif [[ -d "$INSTALL_ROOT/.git" ]]; then
  IREAD_ROOT="$(cd "$INSTALL_ROOT" && pwd -P)"
  if ! git -C "$IREAD_ROOT" diff --quiet \
    || ! git -C "$IREAD_ROOT" diff --cached --quiet; then
    fail "the managed iRead installation has local changes: $IREAD_ROOT"
  fi
  printf 'Updating iRead...\n'
  git -C "$IREAD_ROOT" pull --ff-only --quiet
elif [[ -e "$INSTALL_ROOT" ]]; then
  fail "the install location exists but is not an iRead Git repository: $INSTALL_ROOT"
else
  printf 'Downloading iRead...\n'
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  git clone --depth 1 --quiet "$REPOSITORY_URL" "$INSTALL_ROOT"
  IREAD_ROOT="$(cd "$INSTALL_ROOT" && pwd -P)"
fi

"$IREAD_ROOT/scripts/install.sh" workbuddy "$WORKBUDDY_ROOT_RESOLVED" --force

printf '\niRead is ready in WorkBuddy.\n'
printf 'Open a new WorkBuddy task and run /iread.\n'
printf 'No repository analysis or full knowledge-index rebuild is required.\n'
