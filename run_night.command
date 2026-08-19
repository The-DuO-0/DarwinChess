#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
HOURS="${1:-8}"

if [ ! -x .venv/bin/darwinchess ]; then
  echo "DarwinChess is not installed yet. Run ./setup_mac.sh first."
  exit 1
fi

mkdir -p "$HOME/.darwinchess/logs"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$HOME/.darwinchess/logs/night_${STAMP}.log"

echo "DarwinChess NIGHT mode for about ${HOURS} hour(s) (stops at a safe cycle boundary)."
echo "Log: $LOG"
echo "You may close the lid only if your Mac/energy settings permit it; caffeinate prevents idle system sleep while this process is running."
echo "Ctrl-C stops safely; completed games/checkpoints stay on disk."

# -i prevents idle system sleep; the display can still sleep.
caffeinate -i .venv/bin/darwinchess --mode night evolve --hours "$HOURS" 2>&1 | tee "$LOG"
