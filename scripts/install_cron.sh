#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" != "--config-dir" || -z "${2:-}" || $# -ne 2 ]]; then
  printf 'Usage: %s --config-dir <subscription-config-dir>\n' "$0" >&2
  exit 2
fi
CONFIG_DIR="$(cd "$2" && pwd)"
command -v crontab >/dev/null 2>&1 || {
  printf 'crontab is not installed.\n' >&2
  exit 2
}

PROFILE_ID="$(basename "$CONFIG_DIR")"
MARKER="iread:${PROFILE_ID//[^A-Za-z0-9_.-]/-}"
ROOT_Q="$(printf '%q' "$ROOT")"
CLI_Q="$(printf '%q' "$ROOT/bin/iread")"
CONFIG_Q="$(printf '%q' "$CONFIG_DIR")"
CURRENT="$(crontab -l 2>/dev/null || true)"
CLEANED="$(printf '%s\n' "$CURRENT" | awk -v start="# BEGIN $MARKER" -v end="# END $MARKER" '
  $0 == start {skip=1; next}
  $0 == end {skip=0; next}
  !skip {print}
')"

{
  printf '%s\n' "$CLEANED"
  printf '# BEGIN %s\n' "$MARKER"
  printf '*/10 * * * * cd %s && %s --config-dir %s collect --recent-accounts 3 --backfill-accounts 1\n' "$ROOT_Q" "$CLI_Q" "$CONFIG_Q"
  printf '*/15 * * * * cd %s && %s --config-dir %s enrich --max-batches 2\n' "$ROOT_Q" "$CLI_Q" "$CONFIG_Q"
  printf '0 18 * * * cd %s && %s --config-dir %s run\n' "$ROOT_Q" "$CLI_Q" "$CONFIG_Q"
  printf '0 19 * * * cd %s && %s --config-dir %s export --output-dir public/archive\n' "$ROOT_Q" "$CLI_Q" "$CONFIG_Q"
  printf '# END %s\n' "$MARKER"
} | crontab -

printf 'Installed iRead cron schedule for %s.\n' "$CONFIG_DIR"
