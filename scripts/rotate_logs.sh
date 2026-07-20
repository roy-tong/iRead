#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${IREAD_LOGS_DIR:-${REPORTER_LOGS_DIR:-$ROOT/logs}}"
MAX_BYTES="${IREAD_LOG_MAX_BYTES:-67108864}"
KEEP="${IREAD_LOG_KEEP:-2}"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--dry-run]\n' "$0" >&2
  exit 2
fi

if ! [[ "$MAX_BYTES" =~ ^[0-9]+$ && "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
  printf 'IREAD_LOG_MAX_BYTES and IREAD_LOG_KEEP must be positive integers.\n' >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
LOG_DIR="$(cd "$LOG_DIR" && pwd -P)"
LOCK_DIR="$LOG_DIR/.rotate.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  printf 'Log rotation is already running.\n' >&2
  exit 0
fi
trap 'rm -rf "$LOCK_DIR"' EXIT

rotate_file() {
  local path="$1"
  local size index scratch
  size="$(stat -f '%z' "$path")"
  if (( size <= MAX_BYTES )); then
    return
  fi

  printf '%s\t%s bytes\n' "$path" "$size"
  if (( DRY_RUN )); then
    return
  fi

  rm -f "$path.$KEEP.gz"
  index=$((KEEP - 1))
  while (( index >= 1 )); do
    if [[ -f "$path.$index.gz" ]]; then
      mv "$path.$index.gz" "$path.$((index + 1)).gz"
    fi
    index=$((index - 1))
  done

  scratch="$path.rotate.$$"
  cp -p "$path" "$scratch"
  : > "$path"
  gzip -1 "$scratch"
  mv "$scratch.gz" "$path.1.gz"
}

while IFS= read -r -d '' path; do
  rotate_file "$path"
done < <(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' -print0)
