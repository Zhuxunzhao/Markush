#!/bin/bash
# Start the GLM-5.1 claim-text + first-image infringement dataset run in the background.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/outputs/results/molpatent-240/final"
LOG_DIR="$ROOT_DIR/outputs/runtime/logs"
PID_DIR="$ROOT_DIR/outputs/runtime/pid"
mkdir -p "$OUTPUT_DIR" "$LOG_DIR" "$PID_DIR"

RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
OUTPUT="${OUTPUT:-$OUTPUT_DIR/molpatent-240.glm5_1_claim_text_first_image_infringement.json}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/glm_claim_text_first_image_${RUN_ID}.nohup.log}"
PID_FILE="${PID_FILE:-$PID_DIR/glm_claim_text_first_image_${RUN_ID}.pid}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-240}"

CMD=(
    "$ROOT_DIR/run_glm_first_image_infringement.sh"
    --output "$OUTPUT" \
    --text-source claim \
    --request-timeout "$REQUEST_TIMEOUT" \
    "$@"
)

setsid bash -c 'cd "$1"; shift; exec "$@"' _ "$ROOT_DIR" "${CMD[@]}" >"$LOG_FILE" 2>&1 &

PID="$!"
echo "$PID" >"$PID_FILE"

echo "Started GLM claim-text first-image run."
echo "PID: $PID"
echo "PID file: $PID_FILE"
echo "Log file: $LOG_FILE"
echo "Output JSON: $OUTPUT"
echo "Output JSONL: ${OUTPUT%.*}.jsonl"
echo
echo "Follow log:"
echo "  tail -f '$LOG_FILE'"
echo
echo "Check process:"
echo "  ps -p $PID -o pid,etime,cmd"
