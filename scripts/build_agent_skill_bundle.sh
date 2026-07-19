#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
VERSION="$(PYTHONPATH="$ROOT/src" python3 -c 'from reporter import __version__; print(__version__)')"
OUTPUT_DIR="${1:-$ROOT/dist}"
OUTPUT="$OUTPUT_DIR/iread-agent-skill-$VERSION.zip"

command -v zip >/dev/null 2>&1 || {
  printf 'zip is required to build the Agent Skill bundle.\n' >&2
  exit 2
}

install -d "$OUTPUT_DIR"
rm -f "$OUTPUT"
(cd "$ROOT/skills" && zip -qr "$OUTPUT" iread)
printf '%s\n' "$OUTPUT"
