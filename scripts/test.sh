#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

python3 -m compileall -q "$ROOT/src"
python3 -m unittest discover -s "$ROOT/tests" -p 'test_*.py'
"$ROOT/bin/iread" doctor --surface cli
