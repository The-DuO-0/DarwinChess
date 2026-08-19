#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first (Homebrew or python.org), then rerun."
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ required; found {sys.version.split()[0]}")
print("Python", sys.version.split()[0])
PY

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,studio]"
python -m pytest

echo
echo "dog_matist 2.0 installed. Running hardware/state doctor..."
dog-matist --mode normal doctor

echo
echo "Existing ~/.darwinchess state is intentionally reused, so your champion lineage is preserved."
echo "Start Studio with:"
echo "  ./run_studio.command"
echo "Start an overnight evolution run with:"
echo "  ./run_night.command 8"
