#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
VERSION="$(PYTHONPATH="$ROOT/src" python3 -c 'from reporter import __version__; print(__version__)')"
OUTPUT_DIR="${1:-$ROOT/dist}"

command -v zip >/dev/null 2>&1 || {
  printf 'zip is required to build the Agent Skill bundle.\n' >&2
  exit 2
}

install -d "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd -P)"
OUTPUT="$OUTPUT_DIR/iread-agent-skill-$VERSION.zip"
rm -f "$OUTPUT"
(cd "$ROOT/skills" && zip -qr "$OUTPUT" iread)
if command -v shasum >/dev/null 2>&1; then
  (cd "$OUTPUT_DIR" && shasum -a 256 "$(basename "$OUTPUT")" > SHA256SUMS)
fi
printf '%s\n' "$OUTPUT"
