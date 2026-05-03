#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MG_ROOT="$ROOT_DIR/third_party/MarkushGrapher"
PYTHON_BIN="${PYTHON_BIN:-python3.10}"
VENV_DIR="${VENV_DIR:-$MG_ROOT/.venvs/markushgrapher}"

echo "==> Creating MarkushGrapher virtualenv: $VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel

echo "==> Installing vendored MarkushGrapher package"
PIP_USE_PEP517=0 python -m pip install -e "$MG_ROOT"

echo "==> Installing vendored MolScribe and transformers fork"
python -m pip install -e "$MG_ROOT/external/MolScribe" --no-deps
python -m pip install "numpy<2" "pyonmttok==1.37.1" "OpenNMT-py==2.2.0"
python -m pip install -e "$MG_ROOT/external/transformers"
python -m pip install "fastapi>=0.115" "uvicorn>=0.30"

echo
echo "MarkushGrapher environment ready."
echo "Activate with:"
echo "  source \"$VENV_DIR/bin/activate\""
echo
echo "Then download inference assets with:"
echo "  \"$VENV_DIR/bin/python\" \"$ROOT_DIR/scripts/download_markush_assets.py\""
