# Rental GPU Deployment

This repository is prepared for migration to a fresh GPU rental machine without
losing the benchmark dataset or patent image cache.

## What is already inside the repo

- `data/molpatent-240.json`: 240-row benchmark dataset
- `cache/google_patent.tar.gz`: patent text/image cache archive
- `third_party/MarkushGrapher/`: vendored MarkushGrapher inference source

## What is intentionally not checked in

GitHub cannot host the original multi-GB training/inference checkpoints as
normal git objects. The repository therefore omits:

- `third_party/MarkushGrapher/models/markushgrapher-2/pytorch_model.bin` source repo extras such as `optimizer.pt`
- `third_party/MarkushGrapher/models/chemicalocr/model.safetensors` source repo extras such as `optimizer.pt`
- `third_party/MarkushGrapher/external/MolScribe/ckpts/swin_base_char_aux_1m680k.pth`

The included download script fetches only the minimal inference assets, not the
training checkpoints.

## Recommended machine

- Ubuntu 20.04/22.04
- CUDA-capable NVIDIA GPU with at least 24 GB VRAM preferred
- Python 3.10 for MarkushGrapher
- Python 3.12 for the main app recommended

## 1. Clone the branch

```bash
git clone -b codex/project-cleanup-20260425 <YOUR_REPO_URL>
cd Muti-Agent-for-Murkush
```

## 2. Create the main environment

```bash
bash scripts/setup_main_env.sh
source .venv/bin/activate
```

If `python3.12` is unavailable:

```bash
PYTHON_BIN=python3.11 bash scripts/setup_main_env.sh
source .venv/bin/activate
```

## 3. Create the vendored MarkushGrapher environment

```bash
PYTHON_BIN=python3.10 bash scripts/setup_markushgrapher_env.sh
```

This creates:

- `third_party/MarkushGrapher/.venvs/markushgrapher`

## 4. Download inference-only model assets

```bash
third_party/MarkushGrapher/.venvs/markushgrapher/bin/python scripts/download_markush_assets.py
```

This downloads:

- `third_party/MarkushGrapher/models/markushgrapher-2`
- `third_party/MarkushGrapher/models/chemicalocr`
- `third_party/MarkushGrapher/external/MolScribe/ckpts/swin_base_char_aux_1m680k.pth`

## 5. Extract patent image/text cache

```bash
bash scripts/extract_patent_cache.sh
```

After extraction, the runtime cache is available at:

- `cache/google_patent/`

## 6. Configure API keys

Create `.env` with at least:

```bash
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 7. Run the CLI

```bash
./run.sh infringement --patent_id US10676478 --smiles "CC(=O)Oc1ccccc1C(=O)O"
```

## 8. Run the web app

```bash
source .venv/bin/activate
./run_web.sh
```

## Notes

- `config.yaml` now points to repo-relative vendored paths under `third_party/MarkushGrapher/`.
- `tools/markush_grapher.py` also supports overriding the vendored interpreter/root with:
  - `MARKUSHGRAPHER_ROOT`
  - `MARKUSHGRAPHER_PYTHON_BIN`
- If GPU memory is occupied by other jobs, local inference may fall back to CPU automatically.

