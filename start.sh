#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${MAJABOT_VENV:-$HOME/zulip-bot}"
CONFIG_FILE="${MAJABOT_CONFIG:-$SCRIPT_DIR/zuliprc}"
PID_FILE="${MAJABOT_PID_FILE:-$SCRIPT_DIR/majabot.pid}"
LOG_FILE="${MAJABOT_LOG_FILE:-$SCRIPT_DIR/majabot.log}"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

cd "$SCRIPT_DIR"

if [[ ! -x "$VENV_DIR/bin/zulip-run-bot" ]]; then
    echo "Could not find zulip-run-bot at $VENV_DIR/bin/zulip-run-bot" >&2
    echo "Create the virtual environment and install requirements.txt first." >&2
    exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Could not find Zulip configuration file: $CONFIG_FILE" >&2
    exit 1
fi

if [[ -f "$PID_FILE" ]]; then
    read -r pid < "$PID_FILE"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        echo "Maja is already running (PID $pid)."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

nohup "$VENV_DIR/bin/zulip-run-bot" majabot.maja \
    --config-file "$CONFIG_FILE" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Maja started (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
