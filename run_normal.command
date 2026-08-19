#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/darwinchess ]; then
  echo "Run ./setup_mac.sh first."
  exit 1
fi
.venv/bin/darwinchess --mode normal evolve --cycles "${1:-1}"
