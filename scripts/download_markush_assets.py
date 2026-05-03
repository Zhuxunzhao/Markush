#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from urllib.request import urlretrieve

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MG_ROOT = ROOT / "third_party" / "MarkushGrapher"
MODELS_DIR = MG_ROOT / "models"
MOLSCRIBE_CKPT = MG_ROOT / "external" / "MolScribe" / "ckpts" / "swin_base_char_aux_1m680k.pth"
VOCAB_SRC = MG_ROOT / "external" / "MarkushGenerator" / "markushgenerator" / "data" / "vocabulary"
VOCAB_DST = MG_ROOT / "data" / "vocabulary"

MARKUSH_PATTERNS = [
    "config.json",
    "generation_config.json",
    "pytorch_model.bin",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer_config.json",
]

CHEMOCR_PATTERNS = [
    "added_tokens.json",
    "chat_template.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "preprocessor_config.json",
    "processor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
]


def ensure_snapshot(repo_id: str, local_dir: Path, allow_patterns: list[str]) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        allow_patterns=allow_patterns,
        local_dir_use_symlinks=False,
    )


def ensure_molscribe() -> None:
    if MOLSCRIBE_CKPT.exists():
        return
    MOLSCRIBE_CKPT.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(
        "https://huggingface.co/yujieq/MolScribe/resolve/main/swin_base_char_aux_1m680k.pth",
        str(MOLSCRIBE_CKPT),
    )


def ensure_vocabulary() -> None:
    """Install Markush tokenizer vocabulary files expected by MarkushGrapher."""
    if not VOCAB_SRC.exists():
        raise FileNotFoundError(f"Missing vendored vocabulary source: {VOCAB_SRC}")
    VOCAB_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(VOCAB_SRC, VOCAB_DST, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download minimal inference assets for vendored MarkushGrapher.")
    parser.add_argument(
        "--skip-molscribe",
        action="store_true",
        help="Skip MolScribe checkpoint download.",
    )
    args = parser.parse_args()

    ensure_snapshot(
        repo_id="docling-project/MarkushGrapher-2",
        local_dir=MODELS_DIR / "markushgrapher-2",
        allow_patterns=MARKUSH_PATTERNS,
    )
    ensure_snapshot(
        repo_id="docling-project/ChemicalOCR",
        local_dir=MODELS_DIR / "chemicalocr",
        allow_patterns=CHEMOCR_PATTERNS,
    )
    if not args.skip_molscribe:
        ensure_molscribe()
    ensure_vocabulary()

    print("Downloaded minimal inference assets into:")
    print(f"  {MODELS_DIR / 'markushgrapher-2'}")
    print(f"  {MODELS_DIR / 'chemicalocr'}")
    if not args.skip_molscribe:
        print(f"  {MOLSCRIBE_CKPT}")
    print(f"  {VOCAB_DST}")


if __name__ == "__main__":
    main()
