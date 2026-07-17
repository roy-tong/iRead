#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${IREAD_PYTHON_BIN:-${PYTHON_BIN:-$(command -v python3 || true)}}"

if [[ -z "$PYTHON_BIN" ]]; then
  printf 'Python 3 is required to prepare the iRead runtime.\n' >&2
  exit 2
fi

"$PYTHON_BIN" - "$ROOT/.env" <<'PY'
from pathlib import Path
import secrets
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
values = {}
for line in lines:
    if line and not line.lstrip().startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

defaults = {
    "WERSS_BASE_URL": "http://127.0.0.1:8001",
    "WERSS_USERNAME": "admin",
    "WERSS_PASSWORD": "iread-" + secrets.token_urlsafe(24),
    "WERSS_SECRET_KEY": secrets.token_urlsafe(48),
    "WERSS_DB_PATH": "data/we-mp-rss/we_mp_rss.db",
}
missing = []
for key, generated in defaults.items():
    value = values.get(key, "")
    if not value or value.startswith("replace-with-"):
        values[key] = generated
        missing.append(key)

if missing:
    retained = [
        line
        for line in lines
        if not (
            line
            and not line.lstrip().startswith("#")
            and "=" in line
            and line.split("=", 1)[0].strip() in defaults
        )
    ]
    retained.extend(["", "# iRead local collector"] if retained else ["# iRead local collector"])
    retained.extend(f"{key}={values[key]}" for key in defaults)
    path.write_text("\n".join(retained).rstrip() + "\n", encoding="utf-8")
path.chmod(0o600)
PY

install -d "$ROOT/data/state" "$ROOT/logs"
printf 'iRead local runtime is prepared. Credentials remain in %s/.env.\n' "$ROOT"
