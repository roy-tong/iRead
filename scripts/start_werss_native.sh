#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WERSS="$ROOT/.runtime/we-mp-rss"

if [ ! -x "$WERSS/.venv/bin/python" ]; then
  echo "Run scripts/bootstrap_werss_native.sh first" >&2
  exit 1
fi

if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi

export DB="sqlite:///data/we_mp_rss.db"
export USERNAME="${WERSS_USERNAME:-admin}"
export PASSWORD="${WERSS_PASSWORD:?WERSS_PASSWORD is required in .env}"
export SECRET_KEY="${WERSS_SECRET_KEY:?WERSS_SECRET_KEY is required in .env}"
export ENABLE_JOB=True
export WERSS_AUTH_WEB=False
export WERSS_SEND_CODE=True
export MAX_PAGE=80
export RSS_BASE_URL=http://127.0.0.1:8001/
export RSS_FULL_CONTEXT=True
export RSS_PAGE_SIZE=100
export SPAN_INTERVAL=15
export THREADS=1
export BROWSER_TYPE=webkit
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/.runtime/playwright"
export TZ=Asia/Shanghai

cd "$WERSS"
exec /usr/bin/env \
  'GATHER.CONTENT=True' \
  'GATHER.MODEL=web' \
  'GATHER.CONTENT_AUTO_CHECK=True' \
  'GATHER.CONTENT_AUTO_INTERVAL=59' \
  'GATHER.CONTENT_MODE=web' \
  "$WERSS/.venv/bin/python" main.py -job True -init True
