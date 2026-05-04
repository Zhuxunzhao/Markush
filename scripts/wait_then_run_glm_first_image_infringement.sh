#!/bin/bash
# Wait for an existing process to finish, then run the GLM-5.1 LLM-selected-image workflow.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WAIT_PID="${1:-}"
shift || true

if [ -z "$WAIT_PID" ]; then
    echo "Usage: $0 <pid-to-wait-for> [run_glm_first_image_infringement.sh args...]" >&2
    exit 2
fi

LOG_DIR="$ROOT_DIR/outputs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/glm_first_image_infringement_wait_${WAIT_PID}.log"

echo "$(date -Is) waiting for PID $WAIT_PID" | tee -a "$LOG_FILE"
while kill -0 "$WAIT_PID" 2>/dev/null; do
    sleep 180
done
echo "$(date -Is) PID $WAIT_PID finished; starting GLM LLM-selected-image infringement run" | tee -a "$LOG_FILE"

exec "$ROOT_DIR/run_glm_first_image_infringement.sh" "$@" >>"$LOG_FILE" 2>&1
