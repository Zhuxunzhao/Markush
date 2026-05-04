#!/bin/bash
# 批量启动：LLM 先从 cache/google_patent 中按顺序选择主 Markush 图片，再用 GLM-5.1 判断侵权。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.venv/bin/activate"
elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    conda activate markush
fi

if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.env"
    set +a
fi

python "$ROOT_DIR/scripts/run_glm_first_image_infringement_dataset.py" "$@"
