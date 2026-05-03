#!/usr/bin/env python3
"""Persistent MarkushGrapher HTTP service.

Run this with the vendored MarkushGrapher Python environment. The service keeps
ChemicalOCR and MarkushGrapher models loaded, so requests avoid repeated model
startup cost.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from markushgrapher_infer import MarkushGrapherEngine

DEFAULT_MODEL_DIR = ROOT / "third_party" / "MarkushGrapher" / "models" / "markushgrapher-2"
DEFAULT_OCR_MODEL_DIR = ROOT / "third_party" / "MarkushGrapher" / "models" / "chemicalocr"

app = FastAPI(title="MarkushGrapher Service")
_engine: MarkushGrapherEngine | None = None


class PredictRequest(BaseModel):
    batch_image: list[str]


def get_engine() -> MarkushGrapherEngine:
    global _engine
    if _engine is None:
        model_dir = os.environ.get("MARKUSHGRAPHER_MODEL_DIR", str(DEFAULT_MODEL_DIR))
        ocr_model_dir = os.environ.get("MARKUSHGRAPHER_OCR_MODEL_DIR", str(DEFAULT_OCR_MODEL_DIR))
        num_beams = int(os.environ.get("MARKUSHGRAPHER_NUM_BEAMS", "1"))
        _engine = MarkushGrapherEngine(
            model_dir=model_dir,
            ocr_model_dir=ocr_model_dir,
            num_beams=num_beams,
        )
    return _engine


@app.get("/health")
def health() -> dict[str, Any]:
    engine = get_engine()
    return {
        "status": "ok",
        "device": str(engine.device),
        "num_beams": engine.num_beams,
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    if not request.batch_image:
        raise HTTPException(status_code=400, detail="batch_image must not be empty")

    with tempfile.TemporaryDirectory(prefix="mg_service_images_") as tmpdir:
        image_paths: list[str] = []
        for idx, encoded in enumerate(request.batch_image):
            try:
                payload = base64.b64decode(encoded)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid base64 image at index {idx}") from exc
            path = Path(tmpdir) / f"image_{idx}.png"
            path.write_bytes(payload)
            image_paths.append(str(path))

        try:
            results = get_engine().predict(image_paths)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "data": {
            "smi": [item.get("smi", "") for item in results],
            "caption": [item.get("caption", "") for item in results],
            "score": [float(item.get("score", 0.0)) for item in results],
            "markush": [bool(item.get("is_markush", False)) for item in results],
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistent MarkushGrapher service.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "9100")))
    parser.add_argument("--model_dir", default=os.environ.get("MARKUSHGRAPHER_MODEL_DIR", str(DEFAULT_MODEL_DIR)))
    parser.add_argument("--ocr_model_dir", default=os.environ.get("MARKUSHGRAPHER_OCR_MODEL_DIR", str(DEFAULT_OCR_MODEL_DIR)))
    parser.add_argument("--num_beams", type=int, default=int(os.environ.get("MARKUSHGRAPHER_NUM_BEAMS", "1")))
    args = parser.parse_args()

    os.environ["MARKUSHGRAPHER_MODEL_DIR"] = args.model_dir
    os.environ["MARKUSHGRAPHER_OCR_MODEL_DIR"] = args.ocr_model_dir
    os.environ["MARKUSHGRAPHER_NUM_BEAMS"] = str(args.num_beams)

    # Eagerly load models so startup failure is visible before the port is served.
    get_engine()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
