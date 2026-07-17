#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WERSS="${1:-$ROOT/.runtime/we-mp-rss}"
MODE="${2:-apply}"
PATCHES=(
  "$ROOT/patches/we-mp-rss-macos-qr.patch"
  "$ROOT/patches/we-mp-rss-malformed-publish-info.patch"
  "$ROOT/patches/we-mp-rss-existing-content-repair.patch"
)

if [ "$MODE" = "remove" ]; then
  for patch in "${PATCHES[@]}"; do
    name="$(basename "$patch")"
    if /usr/bin/git -C "$WERSS" apply --ignore-space-change --ignore-whitespace --reverse --check "$patch" >/dev/null 2>&1; then
      /usr/bin/git -C "$WERSS" apply --ignore-space-change --ignore-whitespace --reverse "$patch"
      echo "Removed $name before update."
    else
      echo "$name was not applied."
    fi
  done
else
  for patch in "${PATCHES[@]}"; do
    name="$(basename "$patch")"
    if /usr/bin/git -C "$WERSS" apply --ignore-space-change --ignore-whitespace --reverse --check "$patch" >/dev/null 2>&1; then
      echo "$name is already applied."
    elif /usr/bin/git -C "$WERSS" apply --ignore-space-change --ignore-whitespace --check "$patch"; then
      /usr/bin/git -C "$WERSS" apply --ignore-space-change --ignore-whitespace "$patch"
      echo "Applied $name."
    else
      echo "We-MP-RSS changed and $name no longer applies cleanly." >&2
      exit 1
    fi
  done
fi
