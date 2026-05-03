#!/bin/bash
# 启动脚本 - Multi-Agent for Markush

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 优先使用项目本地 .venv，其次尝试 conda markush，最后回退到当前 python
if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.venv/bin/activate"
elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    conda activate markush
fi

# 加载环境变量
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.env"
    set +a
fi

# 运行主程序
python "$ROOT_DIR/main.py" "$@"
