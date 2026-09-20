#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${MAJABOT_PID_FILE:-$SCRIPT_DIR/majabot.pid}"

if [[ ! -f "$PID_FILE" ]]; then
    echo "Maja is not running."
    exit 0
fi

read -r pid < "$PID_FILE"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    echo "Invalid PID file: $PID_FILE" >&2
    exit 1
fi

if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Maja was not running."
    exit 0
fi

kill "$pid"
for _ in {1..50}; do
    if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "Maja stopped."
        exit 0
    fi
    sleep 0.1
done

echo "Maja did not stop within 5 seconds (PID $pid)." >&2
exit 1
