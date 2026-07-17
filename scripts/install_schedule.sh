#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" != "--config-dir" || -z "${2:-}" || $# -ne 2 ]]; then
  printf 'Usage: %s --config-dir <subscription-config-dir>\n' "$0" >&2
  exit 2
fi
CONFIG_DIR="$(cd "$2" && pwd)"

case "$(uname -s)" in
  Darwin)
    exec "$ROOT/scripts/install_launchd.sh" --config-dir "$CONFIG_DIR"
    ;;
  Linux)
    exec "$ROOT/scripts/install_cron.sh" --config-dir "$CONFIG_DIR"
    ;;
  *)
    printf 'Automatic scheduling currently supports macOS launchd and Linux cron.\n' >&2
    exit 2
    ;;
esac
