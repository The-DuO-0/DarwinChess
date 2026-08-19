#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "DarwinChess .venv was not found in this folder."
  echo "Run INSTALL_STUDIO.command from the Studio package first."
  exit 1
fi

source .venv/bin/activate
python -m pip install --upgrade "PySide6>=6.7,<7" "matplotlib>=3.8"
python - <<'PY'
import chess
import PySide6
import matplotlib
from darwinchess.api import DarwinChessAgent
print("Studio dependencies OK")
PY
chmod +x run_studio.command setup_studio_deps.command

echo
echo "DarwinChess Studio is installed."
echo "Double-click run_studio.command to launch it."
