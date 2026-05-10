#!/usr/bin/env python3
"""Standalone MarkushGrapher inference script.

Must be executed with the markushgrapher conda env's Python interpreter.
PYTHONPATH must include /home/mclab/MarkushGrapher.

Usage:
    python markushgrapher_infer.py \
        --model_dir  /path/to/markushgrapher-2 \
        --ocr_model_dir /path/to/chemicalocr \
        /path/img1.png /path/img2.png ...

stdout: JSON list, one entry per input image:
    [{"path": "...", "caption": "SMILES<sep>...", "smi": "SMILES",
      "is_markush": true, "score": 1.0}, ...]
"""

from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import warnings
from copy import copy
from pathlib import Path

_DEFAULT_MG_ROOT = Path(__file__).resolve().parents[1] / "third_party" / "MarkushGrapher"
_MG_ROOT = os.environ.get("MG_ROOT", str(_DEFAULT_MG_ROOT))
if _MG_ROOT not in sys.path:
    sys.path.insert(0, _MG_ROOT)

import torch
import yaml
from datasets import Dataset, DatasetDict, load_from_disk
from PIL import Image
from transformers import HfArgumentParser, TrainingArguments

import markushgrapher.core.common.begin as begin
from markushgrapher.core.common.arguments import DataTrainingArguments, ModelArguments
from markushgrapher.core.common.markush_tokenizer import MarkushTokenizer
from markushgrapher.core.datasets.dataset_chain import DatasetChain
from markushgrapher.ocr.chemical_ocr import Chemical_OCR
from markushgrapher.utils.common import read_yaml_file
from markushgenerator.text_generation.image_text_merging import ImageTextMerger


_INLINE_RGROUP_RE = re.compile(r"<r>.*?</r>", re.IGNORECASE)


def _caption_has_markush_signal(caption: str) -> bool:
    caption = (caption or "").strip()
    return bool(caption) and (
        "<sep>" in caption or _INLINE_RGROUP_RE.search(caption) is not None
    )


# ---------------------------------------------------------------------------
# Stage 1: HF dataset creation + OCR
# ---------------------------------------------------------------------------

def _generate_hf_dataset(image_paths: list[str], output_dir: str, split: str = "test") -> None:
    merger = ImageTextMerger()
    samples = []
    for img_path in image_paths:
        with Image.open(img_path) as img:
            image = img.convert("RGB")
        pil_image, cells = merger.crop_resize_pad(
            image, [], output_page_width=1024, output_page_height=1024
        )
        samples.append({
            "id": os.path.splitext(os.path.basename(img_path))[0],
            "page_image_path": os.path.abspath(img_path),
            "description": "",
            "annotation": "",
            "mol": "",
            "cxsmiles_dataset": "",
            "cxsmiles": "",
            "cxsmiles_opt": "",
            "keypoints": "",
            "cells": cells,
            "page_image": pil_image,
        })
    DatasetDict({split: Dataset.from_list(samples)}).save_to_disk(output_dir)


def _apply_ocr(hf_dir: str, ocr_model_path: str, split: str = "test") -> None:
    """Run ChemicalOCR on the HF dataset, updating the split in-place."""
    ocr = Chemical_OCR(model_path=ocr_model_path)
    _apply_ocr_with_model(hf_dir, ocr, split=split)


def _apply_ocr_with_model(hf_dir: str, ocr: Chemical_OCR, split: str = "test") -> None:
    """Run a preloaded ChemicalOCR instance on the HF dataset."""
    tmp = tempfile.mkdtemp(prefix="chemocr_")
    try:
        ocr.predict(
            dataset_dir=os.path.join(hf_dir, split),
            output_dir=tmp,
            split=split,
        )
        split_dst = os.path.join(hf_dir, split)
        if os.path.exists(split_dst):
            shutil.rmtree(split_dst)
        shutil.move(os.path.join(tmp, split), split_dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stage 2: model loading + inference
# ---------------------------------------------------------------------------

def _make_configs(tmpdir: str, model_dir: str, hf_dir: str) -> tuple[str, str]:
    """Write temporary predict.yaml and datasets.yaml; return their paths."""
    ds_config = {
        "mdu_dataset": {
            "apply_ocr": False,
            "augment_test": False,
            "class_name": "MDU_Dataset",
            "condense_labels": True,
            "dataset_path": hf_dir,
            "encode_definition_group": False,
            "encode_index": True,
            "encode_position": False,
            "grounded_smiles": False,
            "load_from_cache": False,
            "mask_ratio": 1,
            "module_name": "mdu_dataset",
            "name": "mdu",
            "normalize_bbox": True,
            "splits": ["test"],
            "stream": False,
            "task": "Question Answering",
            "training_dataset_name": "mdu_3008_aug",
            "type": "supervised",
            "udop_tokenizer_only": False,
        }
    }
    ds_config_path = os.path.join(tmpdir, "datasets.yaml")
    with open(ds_config_path, "w") as f:
        yaml.dump(ds_config, f)

    predict_config = {
        "model_name_or_path": model_dir,
        "tokenizer_path": "auto",
        "output_dir": os.path.join(tmpdir, "output"),
        "datasets_config": ds_config_path,
        "max_seq_length": 512,
        "image_size": 512,
        "max_seq_length_decoder": 512,
        "model_type": "UdopUnimodel",
        "architecture_variant": "me-lf-stack-1",
        "beam_search": True,
        "normalize_bbox": True,
        "use_pretrained_molscribe": True,
        "freeze_ocsr_encoder": True,
        "freeze_vtl_decoder": False,
        "freeze_mlp_projector": False,
        "do_train": False,
        "do_eval": False,
        "do_predict": True,
        "dataloader_num_workers": 1,
        "log_level": "ERROR",
        "viz_out_dir": os.path.join(tmpdir, "viz"),
        "prediction_loss_only": True,
        "label_names": ["labels"],
        "unit": "word",
        "apply_ocr": False,
    }
    predict_config_path = os.path.join(tmpdir, "predict.yaml")
    with open(predict_config_path, "w") as f:
        yaml.dump(predict_config, f)

    return predict_config_path, ds_config_path


def _make_datasets_config(tmpdir: str, hf_dir: str) -> str:
    """Write a datasets.yaml for a request-specific HF dataset."""
    _, ds_config_path = _make_configs(tmpdir, "", hf_dir)
    return ds_config_path


class MarkushGrapherEngine:
    """Reusable MarkushGrapher engine that keeps OCR and model weights loaded."""

    def __init__(self, model_dir: str, ocr_model_dir: str, num_beams: int = 1):
        self.model_dir = model_dir
        self.ocr_model_dir = ocr_model_dir
        self.num_beams = num_beams
        self._lock = threading.Lock()
        self._engine_dir = tempfile.mkdtemp(prefix="mg_engine_")

        print("[startup] Loading ChemicalOCR…", file=sys.stderr)
        self.ocr = Chemical_OCR(model_path=ocr_model_dir)

        print("[startup] Loading MarkushGrapher model…", file=sys.stderr)
        placeholder_hf_dir = os.path.join(self._engine_dir, "hf_dataset")
        predict_cfg_path, ds_cfg_path = _make_configs(
            self._engine_dir, model_dir, placeholder_hf_dir
        )
        hf_parser = HfArgumentParser((ModelArguments, DataTrainingArguments, TrainingArguments))
        self.model_args, self.data_args, self.training_args = hf_parser.parse_yaml_file(
            yaml_file=os.path.abspath(predict_cfg_path)
        )
        if self.model_args.tokenizer_path == "auto":
            self.model_args.tokenizer_path = self.model_args.model_name_or_path

        self.device = begin.get_device()
        self.tokenizer, self.processors, self.model = begin.load_markushgrapher(
            self.model_args,
            self.data_args,
            self.training_args,
            self.device,
            use_pretrained_molscribe=True,
        )
        self.model.eval()

        ds_config = list(read_yaml_file(ds_cfg_path).values())[0]
        self.ds_config_template = ds_config
        self.markush_tokenizer = MarkushTokenizer(
            self.tokenizer,
            ds_config["dataset_path"],
            encode_position=ds_config["encode_position"],
            grounded_smiles=ds_config["grounded_smiles"],
            encode_index=ds_config["encode_index"],
            training_dataset_name=ds_config["training_dataset_name"],
        )
        print(f"[startup] MarkushGrapher ready on {self.device}", file=sys.stderr)

    def predict(self, image_paths: list[str]) -> list[dict]:
        """Run OCR + Markush prediction. Calls are serialized for GPU safety."""
        with self._lock:
            return self._predict_locked(image_paths)

    def _predict_locked(self, image_paths: list[str]) -> list[dict]:
        tmpdir = tempfile.mkdtemp(prefix="mg_infer_")
        try:
            hf_dir = os.path.join(tmpdir, "hf_dataset")

            print("[1/2] Creating HF dataset and running ChemicalOCR…", file=sys.stderr)
            _generate_hf_dataset(image_paths, hf_dir)
            _apply_ocr_with_model(hf_dir, self.ocr)

            print("[2/2] Running MarkushGrapher inference…", file=sys.stderr)
            ds_cfg_path = _make_datasets_config(tmpdir, hf_dir)
            data_args = copy(self.data_args)
            data_args.datasets_config = ds_cfg_path

            dataset_chain = DatasetChain(
                processors=self.processors,
                tokenizer=self.tokenizer,
                data_args=data_args,
                split="test",
            )
            dataset = dataset_chain._all_datasets["mdu"]
            hf_raw = load_from_disk(hf_dir)["test"]

            results: list[dict] = []
            with torch.no_grad():
                for idx in range(len(dataset)):
                    encoding = dataset.__getitem__(int(idx))

                    encoding["input_ids"] = (
                        encoding["input_ids"].type(torch.long).unsqueeze(0).to(self.device)
                    )
                    encoding["bbox"] = (
                        encoding["bbox"].type(torch.float).unsqueeze(0).to(self.device)
                    )
                    encoding["attention_mask"] = (
                        encoding["attention_mask"].type(torch.long).unsqueeze(0).to(self.device)
                    )
                    if "decoder_attention_mask" in encoding:
                        encoding["decoder_attention_mask"] = (
                            encoding["decoder_attention_mask"]
                            .type(torch.long)
                            .unsqueeze(0)
                            .to(self.device)
                        )
                    encoding["pixel_values"] = encoding["pixel_values"].unsqueeze(0).to(self.device)

                    for key in ("attention_mask", "decoder_attention_mask", "image", "labels"):
                        encoding.pop(key, None)

                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        predicted_ids = self.model.generate(
                            **encoding, num_beams=self.num_beams, max_length=512
                        )

                    predicted_text = self.markush_tokenizer.decode_plus_decode_other_tokens(
                        predicted_ids[0][1:-1]
                    )
                    m = re.search(r"<cxsmi>(.*?)</cxsmi>", predicted_text, re.DOTALL)
                    caption = m.group(1).replace(" ", "") if m else ""
                    smi = caption.split("<sep>")[0] if "<sep>" in caption else caption
                    is_markush = _caption_has_markush_signal(caption)

                    results.append({
                        "path": hf_raw[idx]["page_image_path"],
                        "caption": caption,
                        "smi": smi,
                        "is_markush": is_markush,
                        "score": 1.0,
                    })

            return results
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _run_inference(
    image_paths: list[str],
    model_dir: str,
    ocr_model_dir: str,
    num_beams: int,
) -> list[dict]:
    tmpdir = tempfile.mkdtemp(prefix="mg_infer_")
    try:
        hf_dir = os.path.join(tmpdir, "hf_dataset")

        # ── Stage 1 ──────────────────────────────────────────────────────────
        print("[1/2] Creating HF dataset and running ChemicalOCR…", file=sys.stderr)
        _generate_hf_dataset(image_paths, hf_dir)
        _apply_ocr(hf_dir, ocr_model_dir)

        # ── Stage 2 ──────────────────────────────────────────────────────────
        print("[2/2] Loading MarkushGrapher model and running inference…", file=sys.stderr)
        predict_cfg_path, ds_cfg_path = _make_configs(tmpdir, model_dir, hf_dir)

        hf_parser = HfArgumentParser((ModelArguments, DataTrainingArguments, TrainingArguments))
        model_args, data_args, training_args = hf_parser.parse_yaml_file(
            yaml_file=os.path.abspath(predict_cfg_path)
        )
        if model_args.tokenizer_path == "auto":
            model_args.tokenizer_path = model_args.model_name_or_path

        device = begin.get_device()
        tokenizer, processors, model = begin.load_markushgrapher(
            model_args, data_args, training_args, device, use_pretrained_molscribe=True
        )
        model.eval()

        ds_config = list(read_yaml_file(ds_cfg_path).values())[0]
        markush_tokenizer = MarkushTokenizer(
            tokenizer,
            ds_config["dataset_path"],
            encode_position=ds_config["encode_position"],
            grounded_smiles=ds_config["grounded_smiles"],
            encode_index=ds_config["encode_index"],
            training_dataset_name=ds_config["training_dataset_name"],
        )

        dataset_chain = DatasetChain(
            processors=processors,
            tokenizer=tokenizer,
            data_args=data_args,
            split="test",
        )
        dataset = dataset_chain._all_datasets["mdu"]

        # Original image paths in the same order as the HF dataset
        hf_raw = load_from_disk(hf_dir)["test"]

        results: list[dict] = []
        with torch.no_grad():
            for idx in range(len(dataset)):
                encoding = dataset.__getitem__(int(idx))

                # Prepare tensors (mirror eval.py logic)
                encoding["input_ids"] = (
                    encoding["input_ids"].type(torch.long).unsqueeze(0).to(device)
                )
                encoding["bbox"] = (
                    encoding["bbox"].type(torch.float).unsqueeze(0).to(device)
                )
                encoding["attention_mask"] = (
                    encoding["attention_mask"].type(torch.long).unsqueeze(0).to(device)
                )
                if "decoder_attention_mask" in encoding:
                    encoding["decoder_attention_mask"] = (
                        encoding["decoder_attention_mask"]
                        .type(torch.long)
                        .unsqueeze(0)
                        .to(device)
                    )
                encoding["pixel_values"] = (
                    encoding["pixel_values"].unsqueeze(0).to(device)
                )

                # Keys not used by generate()
                for key in ("attention_mask", "decoder_attention_mask", "image", "labels"):
                    encoding.pop(key, None)

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    predicted_ids = model.generate(
                        **encoding, num_beams=num_beams, max_length=512
                    )

                predicted_text = markush_tokenizer.decode_plus_decode_other_tokens(
                    predicted_ids[0][1:-1]
                )

                # Extract CXSMILES caption from model output
                m = re.search(r"<cxsmi>(.*?)</cxsmi>", predicted_text, re.DOTALL)
                caption = m.group(1).replace(" ", "") if m else ""
                smi = caption.split("<sep>")[0] if "<sep>" in caption else caption
                is_markush = _caption_has_markush_signal(caption)

                results.append({
                    "path": hf_raw[idx]["page_image_path"],
                    "caption": caption,
                    "smi": smi,
                    "is_markush": is_markush,
                    "score": 1.0,
                })

        return results

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MarkushGrapher local inference")
    parser.add_argument("--model_dir", required=True, help="MarkushGrapher model directory")
    parser.add_argument("--ocr_model_dir", required=True, help="ChemicalOCR model directory")
    parser.add_argument(
        "--num_beams",
        type=int,
        default=int(os.environ.get("MARKUSHGRAPHER_NUM_BEAMS", "1")),
        help="Beam count for MarkushGrapher decoding; lower is faster.",
    )
    parser.add_argument("images", nargs="+", help="Image file paths to process")
    args = parser.parse_args()

    results = _run_inference(args.images, args.model_dir, args.ocr_model_dir, args.num_beams)
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
