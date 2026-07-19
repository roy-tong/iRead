#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" != "--config-dir" || -z "${2:-}" || $# -ne 2 ]]; then
  printf 'Usage: %s --config-dir <subscription-config-dir>\n' "$0" >&2
  exit 2
fi
CONFIG_DIR="$(cd "$2" && pwd)"

service_root() {
  if [ -n "${IREAD_SERVICE_ROOT:-}" ]; then
    printf '%s\n' "$IREAD_SERVICE_ROOT"
  elif [ -n "${REPORTER_SERVICE_ROOT:-}" ]; then
    printf '%s\n' "$REPORTER_SERVICE_ROOT"
  elif [ -L "$ROOT/data" ]; then
    dirname "$(cd "$ROOT/data" && pwd -P)"
  else
    printf '%s\n' "$HOME/Library/Application Support/ResearchReporter"
  fi
}

remove_active_pointer() {
  local pointer
  pointer="$(service_root)/active-config-dir"
  if [ -f "$pointer" ] && [ "$(/bin/cat "$pointer")" = "$CONFIG_DIR" ]; then
    /bin/rm "$pointer"
  fi
}

case "$(uname -s)" in
  Darwin)
    TARGET="$HOME/Library/LaunchAgents"
    UID_VALUE="$(/usr/bin/id -u)"
    LABEL_PREFIX="${IREAD_LABEL_PREFIX:-${REPORTER_LABEL_PREFIX:-com.local.research-reporter}}"
    if [ -z "${IREAD_LABEL_PREFIX:-}" ] && [ -z "${REPORTER_LABEL_PREFIX:-}" ] && [ -f "$TARGET/com.roy.wechat-research.sync.plist" ]; then
      LABEL_PREFIX="com.roy.wechat-research"
    fi
    for template in "$ROOT"/launchd/*.plist.template; do
      template_name="$(basename "$template" .plist.template)"
      suffix="${template_name#com.local.research-reporter.}"
      destination="$TARGET/$LABEL_PREFIX.$suffix.plist"
      if [ -f "$destination" ]; then
        /bin/launchctl bootout "gui/$UID_VALUE" "$destination" >/dev/null 2>&1 || true
        /bin/rm "$destination"
      fi
    done
    remove_active_pointer
    printf 'Removed iRead launchd schedule for %s. Local data was preserved.\n' "$CONFIG_DIR"
    ;;
  Linux)
    command -v crontab >/dev/null 2>&1 || {
      printf 'crontab is not installed.\n' >&2
      exit 2
    }
    PROFILE_ID="$(basename "$CONFIG_DIR")"
    MARKER="iread:${PROFILE_ID//[^A-Za-z0-9_.-]/-}"
    CURRENT="$(crontab -l 2>/dev/null || true)"
    printf '%s\n' "$CURRENT" | awk -v start="# BEGIN $MARKER" -v end="# END $MARKER" '
      $0 == start {skip=1; next}
      $0 == end {skip=0; next}
      !skip {print}
    ' | crontab -
    remove_active_pointer
    printf 'Removed iRead cron schedule for %s. Local data was preserved.\n' "$CONFIG_DIR"
    ;;
  *)
    printf 'Automatic scheduling currently supports macOS launchd and Linux cron.\n' >&2
    exit 2
    ;;
esac
