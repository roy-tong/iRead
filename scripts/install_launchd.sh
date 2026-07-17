#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="$ROOT/config"
if [[ $# -gt 0 ]]; then
  if [[ "${1:-}" != "--config-dir" || -z "${2:-}" || $# -ne 2 ]]; then
    printf 'Usage: %s [--config-dir <subscription-config-dir>]\n' "$0" >&2
    exit 2
  fi
  CONFIG_DIR="$(cd "$2" && pwd)"
fi
CONFIG_STAGE="$(mktemp -d /tmp/iread-config.XXXXXX)"
trap '/bin/rm -rf "$CONFIG_STAGE"' EXIT
/usr/bin/rsync -a "$CONFIG_DIR/" "$CONFIG_STAGE/"
TARGET="$HOME/Library/LaunchAgents"
if [ -n "${IREAD_SERVICE_ROOT:-}" ]; then
  SERVICE_ROOT="$IREAD_SERVICE_ROOT"
elif [ -n "${REPORTER_SERVICE_ROOT:-}" ]; then
  SERVICE_ROOT="$REPORTER_SERVICE_ROOT"
elif [ -L "$ROOT/data" ]; then
  SERVICE_ROOT="$(dirname "$(cd "$ROOT/data" && pwd -P)")"
else
  SERVICE_ROOT="$HOME/Library/Application Support/ResearchReporter"
fi
APP_ROOT="$SERVICE_ROOT/app"
UID_VALUE="$(/usr/bin/id -u)"
LABEL_PREFIX="${IREAD_LABEL_PREFIX:-${REPORTER_LABEL_PREFIX:-com.local.research-reporter}}"
ACTIVE_CONFIG_FILE="$SERVICE_ROOT/active-config-dir"

if [ -f "$ACTIVE_CONFIG_FILE" ]; then
  ACTIVE_CONFIG_DIR="$(/bin/cat "$ACTIVE_CONFIG_FILE")"
  if [ "$ACTIVE_CONFIG_DIR" != "$CONFIG_DIR" ] && [ "${IREAD_ALLOW_CONFIG_SWITCH:-0}" != "1" ]; then
    printf 'Refusing to replace active iRead config %s with %s.\n' \
      "$ACTIVE_CONFIG_DIR" "$CONFIG_DIR" >&2
    printf 'Use a separate IREAD_SERVICE_ROOT/IREAD_LABEL_PREFIX, or set IREAD_ALLOW_CONFIG_SWITCH=1 for an intentional switch.\n' >&2
    exit 3
  fi
fi

if [ -z "${IREAD_LABEL_PREFIX:-}" ] && [ -z "${REPORTER_LABEL_PREFIX:-}" ] && [ -f "$TARGET/com.roy.wechat-research.sync.plist" ]; then
  LABEL_PREFIX="com.roy.wechat-research"
fi

mkdir -p "$TARGET" "$SERVICE_ROOT" "$APP_ROOT"

migrate_directory() {
  local name="$1"
  local source="$ROOT/$name"
  local destination="$SERVICE_ROOT/$name"
  if [ -L "$source" ]; then
    return
  fi
  if [ -d "$source" ] && [ ! -e "$destination" ]; then
    /bin/mv "$source" "$destination"
  elif [ -d "$source" ]; then
    /usr/bin/rsync -a "$source/" "$destination/"
    /bin/mv "$source" "$source.pre-launchd"
  else
    mkdir -p "$destination"
  fi
  /bin/ln -s "$destination" "$source"
}

migrate_directory data
migrate_directory logs

if [ ! -L "$ROOT/.runtime" ]; then
  if [ -d "$ROOT/.runtime" ] && [ ! -e "$SERVICE_ROOT/runtime" ]; then
    /bin/mv "$ROOT/.runtime" "$SERVICE_ROOT/runtime"
  elif [ ! -e "$SERVICE_ROOT/runtime" ]; then
    mkdir -p "$SERVICE_ROOT/runtime"
  fi
  /bin/ln -s "$SERVICE_ROOT/runtime" "$ROOT/.runtime"
fi

mkdir -p "$SERVICE_ROOT/data/we-mp-rss" "$SERVICE_ROOT/logs" "$SERVICE_ROOT/runtime/we-mp-rss"
if [ -L "$SERVICE_ROOT/runtime/we-mp-rss/data" ]; then
  /bin/rm "$SERVICE_ROOT/runtime/we-mp-rss/data"
elif [ -d "$SERVICE_ROOT/runtime/we-mp-rss/data" ]; then
  /bin/mv "$SERVICE_ROOT/runtime/we-mp-rss/data" "$SERVICE_ROOT/runtime/we-mp-rss/data.upstream-backup"
fi
/bin/ln -s "$SERVICE_ROOT/data/we-mp-rss" "$SERVICE_ROOT/runtime/we-mp-rss/data"

"$ROOT/scripts/apply_werss_patches.sh" "$SERVICE_ROOT/runtime/we-mp-rss"

for directory in src prompts schemas bin scripts patches; do
  mkdir -p "$APP_ROOT/$directory"
  /usr/bin/rsync -a --delete "$ROOT/$directory/" "$APP_ROOT/$directory/"
done
mkdir -p "$APP_ROOT/config"
/usr/bin/rsync -a --delete "$CONFIG_STAGE/" "$APP_ROOT/config/"
if [ -f "$ROOT/.env" ]; then
  /bin/cp "$ROOT/.env" "$APP_ROOT/.env"
  /bin/chmod 600 "$APP_ROOT/.env"
fi
/bin/ln -sfn "$SERVICE_ROOT/data" "$APP_ROOT/data"
/bin/ln -sfn "$SERVICE_ROOT/logs" "$APP_ROOT/logs"
/bin/ln -sfn "$SERVICE_ROOT/runtime" "$APP_ROOT/.runtime"
/bin/chmod +x "$APP_ROOT"/bin/* "$APP_ROOT"/scripts/*.sh

for template in "$ROOT"/launchd/*.plist.template; do
  template_name="$(basename "$template" .plist.template)"
  suffix="${template_name#com.local.research-reporter.}"
  name="$LABEL_PREFIX.$suffix.plist"
  destination="$TARGET/$name"
  /usr/bin/sed \
    -e "s|__PROJECT_ROOT__|$APP_ROOT|g" \
    -e "s|com.local.research-reporter|$LABEL_PREFIX|g" \
    "$template" > "$destination"
  /bin/chmod 600 "$destination"
  /bin/launchctl bootout "gui/$UID_VALUE" "$destination" >/dev/null 2>&1 || true
  /bin/launchctl bootstrap "gui/$UID_VALUE" "$destination"
done

printf '%s\n' "$CONFIG_DIR" > "$ACTIVE_CONFIG_FILE"

echo "Installed background runtime at $SERVICE_ROOT"
echo "Active subscription config: $CONFIG_DIR"
echo "Installed WeRSS, unified library, sync, backfill, and report LaunchAgents."
