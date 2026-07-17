#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime"
UV="$RUNTIME/bin/uv"
WERSS="$RUNTIME/we-mp-rss"
ARCHIVE="$RUNTIME/uv.tar.gz"

mkdir -p "$RUNTIME/bin" "$ROOT/data/we-mp-rss" "$ROOT/logs"

if [ ! -x "$UV" ]; then
  case "$(uname -m)" in
    arm64) UV_ARCHIVE="uv-aarch64-apple-darwin.tar.gz" ;;
    x86_64) UV_ARCHIVE="uv-x86_64-apple-darwin.tar.gz" ;;
    *) echo "Unsupported macOS architecture: $(uname -m)" >&2; exit 2 ;;
  esac
  /usr/bin/curl -fL --retry 3 \
    "https://ghfast.top/https://github.com/astral-sh/uv/releases/latest/download/$UV_ARCHIVE" \
    -o "$ARCHIVE" || \
  /usr/bin/curl -fL --retry 3 \
    "https://github.com/astral-sh/uv/releases/latest/download/$UV_ARCHIVE" \
    -o "$ARCHIVE"
  /usr/bin/tar -xzf "$ARCHIVE" -C "$RUNTIME/bin" --strip-components=1
  /bin/rm -f "$ARCHIVE"
fi

if [ ! -d "$WERSS/.git" ]; then
  /usr/bin/git clone --depth 1 https://github.com/rachelos/we-mp-rss.git "$WERSS"
else
  "$ROOT/scripts/apply_werss_patches.sh" "$WERSS" remove
  /usr/bin/git -C "$WERSS" pull --ff-only
fi

"$ROOT/scripts/apply_werss_patches.sh" "$WERSS"

if [ -e "$WERSS/data" ] && [ ! -L "$WERSS/data" ]; then
  /bin/mv "$WERSS/data" "$WERSS/data.upstream-backup"
fi
if [ ! -L "$WERSS/data" ]; then
  /bin/ln -s "$ROOT/data/we-mp-rss" "$WERSS/data"
fi
if [ ! -f "$WERSS/config.yaml" ]; then
  /bin/cp "$WERSS/config.example.yaml" "$WERSS/config.yaml"
fi

"$UV" python install 3.13
"$UV" venv --python 3.13 "$WERSS/.venv"
"$UV" pip install --python "$WERSS/.venv/bin/python" -r "$WERSS/requirements.txt"
PLAYWRIGHT_BROWSERS_PATH="$RUNTIME/playwright" \
  "$WERSS/.venv/bin/python" -m playwright install webkit

echo "We-MP-RSS native runtime is ready at $WERSS"
