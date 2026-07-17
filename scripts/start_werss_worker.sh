#!/bin/bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 NODE_ID PORT REDIS_PORT" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NODE_ID="$1"
PORT_VALUE="$2"
REDIS_PORT_VALUE="$3"
SOURCE="$ROOT/.runtime/we-mp-rss"
WORKER="$ROOT/.runtime/we-mp-rss-worker-$NODE_ID"
DATA_DIR="$ROOT/data/we-mp-rss-worker-$NODE_ID"

if [ ! -x "$SOURCE/.venv/bin/python" ]; then
  echo "Primary WeRSS runtime is not ready" >&2
  exit 1
fi

mkdir -p "$WORKER" "$DATA_DIR" "$ROOT/logs"
/usr/bin/rsync -a --delete \
  --exclude '/.git/' \
  --exclude '/.venv/' \
  --exclude '/data' \
  --exclude '/static/wx_qrcode.png' \
  "$SOURCE/" "$WORKER/"

if [ -e "$WORKER/.venv" ] && [ ! -L "$WORKER/.venv" ]; then
  echo "Worker .venv must be a symlink" >&2
  exit 1
fi
/bin/ln -sfn "$SOURCE/.venv" "$WORKER/.venv"

if [ -e "$WORKER/data" ] && [ ! -L "$WORKER/data" ]; then
  echo "Worker data path must be a symlink" >&2
  exit 1
fi
/bin/ln -sfn "$DATA_DIR" "$WORKER/data"
/bin/rm -f "$WORKER/static/wx_qrcode.png"

if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi

export DB="sqlite:///data/we_mp_rss.db"
export PORT="$PORT_VALUE"
export USERNAME="${WERSS_USERNAME:-admin}"
export PASSWORD="${WERSS_PASSWORD:?WERSS_PASSWORD is required in .env}"
export SECRET_KEY="${WERSS_SECRET_KEY:?WERSS_SECRET_KEY is required in .env}-$NODE_ID"
export ENABLE_JOB=False
export WERSS_AUTH_WEB=False
export WERSS_SEND_CODE=True
export MAX_PAGE=10
export RSS_BASE_URL="http://127.0.0.1:$PORT_VALUE/"
export RSS_FULL_CONTEXT=True
export RSS_PAGE_SIZE=100
export SPAN_INTERVAL=15
export THREADS=1
export BROWSER_TYPE=webkit
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/.runtime/playwright"
export REDIS_URL="redis://127.0.0.1:$REDIS_PORT_VALUE/0"
export REDIS_SERVER_HOST=127.0.0.1
export REDIS_SERVER_PORT="$REDIS_PORT_VALUE"
export REDIS_SERVER_PASSWORD=""
export REDIS_SERVER_PERSISTENCE=true
export CASCADE_ENABLED=False
export TZ=Asia/Shanghai

cd "$WORKER"
exec /usr/bin/env \
  'GATHER.CONTENT=True' \
  'GATHER.MODEL=web' \
  'GATHER.CONTENT_AUTO_CHECK=False' \
  'GATHER.CONTENT_MODE=web' \
  "$WORKER/.venv/bin/python" main.py -job False -init True
