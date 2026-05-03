#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/outputs/markushgrapher_service.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "No MarkushGrapher service pid file found."
    exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Stopped MarkushGrapher service (pid $PID)."
else
    echo "MarkushGrapher service is not running (stale pid $PID)."
fi
