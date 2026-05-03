#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-9100}"
NUM_BEAMS="${NUM_BEAMS:-1}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/third_party/MarkushGrapher/.venvs/markushgrapher/bin/python}"

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/third_party/MarkushGrapher:${PYTHONPATH:-}"
export MARKUSHGRAPHER_NUM_BEAMS="$NUM_BEAMS"
export PYTHONUNBUFFERED=1

exec "$PYTHON_BIN" "$ROOT_DIR/tools/markushgrapher_service.py" \
  --host "$HOST" \
  --port "$PORT" \
  --model_dir "$ROOT_DIR/third_party/MarkushGrapher/models/markushgrapher-2" \
  --ocr_model_dir "$ROOT_DIR/third_party/MarkushGrapher/models/chemicalocr" \
  --num_beams "$NUM_BEAMS"
