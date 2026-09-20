#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${MAJABOT_VENV:-$HOME/zulip-bot}"

cd "$SCRIPT_DIR"

echo "Updating Maja..."

git pull --ff-only

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Could not find Python at $VENV_DIR/bin/python" >&2
    exit 1
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/python" -m pip install -r requirements.txt
"$VENV_DIR/bin/python" -m pip install --editable .

./stop.sh
./start.sh

echo "Maja updated and restarted."
