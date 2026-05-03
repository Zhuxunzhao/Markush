#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/outputs/markushgrapher_service.pid"
LOG_FILE="$ROOT_DIR/outputs/markushgrapher_service.log"

mkdir -p "$ROOT_DIR/outputs"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "MarkushGrapher service already running (pid $(cat "$PID_FILE"))."
    exit 0
fi

setsid "$ROOT_DIR/run_markushgrapher_service.sh" > "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"
echo "Started MarkushGrapher service (pid $(cat "$PID_FILE"))."
echo "Log: $LOG_FILE"
