#!/bin/bash
set -euo pipefail

caffeinate_pid=""

stop_assertion() {
  if [ -n "$caffeinate_pid" ] && kill -0 "$caffeinate_pid" 2>/dev/null; then
    kill "$caffeinate_pid" 2>/dev/null || true
    wait "$caffeinate_pid" 2>/dev/null || true
  fi
  caffeinate_pid=""
}

is_locked() {
  /usr/sbin/ioreg -n Root -d1 | /usr/bin/grep -q '"CGSSessionScreenIsLocked" = Yes'
}

trap stop_assertion EXIT INT TERM

while true; do
  if is_locked; then
    stop_assertion
  elif [ -z "$caffeinate_pid" ] || ! kill -0 "$caffeinate_pid" 2>/dev/null; then
    /usr/bin/caffeinate -d -i &
    caffeinate_pid=$!
  fi
  /bin/sleep 5
done
