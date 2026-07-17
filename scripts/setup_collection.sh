#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/prepare_runtime.sh"
CURL_BIN="$(command -v curl || true)"
if [[ -z "$CURL_BIN" ]]; then
  printf 'curl is required to check the local We-MP-RSS service.\n' >&2
  exit 2
fi

if "$CURL_BIN" -fsS --max-time 2 http://127.0.0.1:8001/ >/dev/null 2>&1; then
  printf 'We-MP-RSS is already running at http://127.0.0.1:8001.\n'
  exit 0
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker compose -f "$ROOT/compose.yaml" --env-file "$ROOT/.env" up -d we-mp-rss
  MODE="docker"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  "$ROOT/scripts/bootstrap_werss_native.sh"
  PID_FILE="$ROOT/data/state/werss.pid"
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    :
  else
    nohup "$ROOT/scripts/start_werss_native.sh" \
      >>"$ROOT/logs/werss.out.log" \
      2>>"$ROOT/logs/werss.err.log" &
    printf '%s\n' "$!" > "$PID_FILE"
  fi
  MODE="native"
else
  printf 'Docker is required for We-MP-RSS on this operating system.\n' >&2
  exit 2
fi

for _ in $(seq 1 120); do
  if "$CURL_BIN" -fsS --max-time 2 http://127.0.0.1:8001/ >/dev/null 2>&1; then
    printf 'We-MP-RSS is ready in %s mode at http://127.0.0.1:8001.\n' "$MODE"
    exit 0
  fi
  sleep 1
done

printf 'We-MP-RSS did not become ready within 120 seconds. Check %s/logs/werss.err.log.\n' "$ROOT" >&2
exit 1
