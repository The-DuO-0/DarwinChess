#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

candidates=()
while IFS= read -r -d '' f; do
  d="$(dirname "$f")"
  if [ -f "$d/README.md" ] && grep -qi "DarwinChess" "$d/README.md" 2>/dev/null; then
    candidates+=("$d")
  fi
done < <(find "$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents" -maxdepth 4 -type f -name 'setup_mac.sh' -print0 2>/dev/null || true)

if [ -d "$HERE/.venv" ] && [ -f "$HERE/setup_mac.sh" ]; then
  target="$HERE"
elif [ ${#candidates[@]} -eq 1 ]; then
  target="${candidates[0]}"
elif [ ${#candidates[@]} -gt 1 ]; then
  echo "I found several DarwinChess folders:"
  for i in "${!candidates[@]}"; do echo "$((i+1))) ${candidates[$i]}"; done
  echo
  read -r -p "Choose a number: " pick
  idx=$((pick-1))
  target="${candidates[$idx]}"
else
  echo "I couldn't automatically find the DarwinChess project folder."
  echo "Drag the DarwinChess folder into this Terminal window, then press Return:"
  read -r target
  target="${target%/}"
  target="${target#\'}"; target="${target%\'}"
  target="${target#\"}"; target="${target%\"}"
fi

if [ ! -d "$target/.venv" ] || [ ! -f "$target/setup_mac.sh" ]; then
  echo "That does not look like the installed DarwinChess project folder: $target"
  exit 1
fi

# Never delete the source Studio folder if the package itself is already inside the project.
if [ "$HERE" != "$target" ]; then
  rm -rf "$target/studio"
  cp -R "$HERE/studio" "$target/studio"
  cp "$HERE/setup_studio_deps.command" "$target/setup_studio_deps.command"
  cp "$HERE/run_studio.command" "$target/run_studio.command"
  cp "$HERE/STUDIO_README.md" "$target/STUDIO_README.md"
fi
chmod +x "$target/setup_studio_deps.command" "$target/run_studio.command"

echo "Installing Studio into: $target"
cd "$target"
./setup_studio_deps.command
