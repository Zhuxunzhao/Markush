"""ChemicalOCR 封装 — 从化学结构图片中提取文字标签和位置

支持三种后端:
- remote: 调用远程 HTTP 服务
- local_vllm: 本地 vllm (NVIDIA GPU)
- local_transformers: 本地 transformers (CPU/MPS fallback)
"""

from __future__ import annotations
from typing import Optional

from schemas.types import OCRCell


class ChemicalOCRTool:
    def __init__(self, config: dict):
        ocr_cfg = config["tools"]["chemical_ocr"]
        self.mode = ocr_cfg.get("mode", "remote")
        self.endpoint = ocr_cfg.get("endpoint", "")
        self.model_dir = ocr_cfg.get("model_dir", "")
        self._ocr = None

    def _load_local_model(self):
        if self._ocr is not None:
            return
        from markushgrapher.ocr.chemical_ocr import Chemical_OCR
        self._ocr = Chemical_OCR(model_path=self.model_dir)

    def extract(self, image_path: str) -> list[OCRCell]:
        """从单张图片提取 OCR cells"""
        if self.mode == "remote":
            return self._extract_remote(image_path)
        else:
            return self._extract_local(image_path)

    def _extract_remote(self, image_path: str) -> list[OCRCell]:
        """调用远程 ChemicalOCR 服务"""
        import base64, io, requests
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        response = requests.post(
            self.endpoint,
            json={"image": b64},
            timeout=60,
        )
        cells_data = response.json().get("cells", [])
        return [OCRCell(text=c["text"], bbox=c["bbox"]) for c in cells_data]

    def _extract_local(self, image_path: str) -> list[OCRCell]:
        """本地推理 — 需要对应环境"""
        self._load_local_model()
        # TODO: 实现单张图片的本地 OCR
        # Chemical_OCR.predict() 目前只支持 HF dataset 批量处理
        # 需要封装单图接口
        raise NotImplementedError(
            "本地 ChemicalOCR 单图推理待实现，"
            "当前 Chemical_OCR.predict() 仅支持 HF dataset 批量模式"
        )

    def extract_batch(self, image_paths: list[str]) -> list[list[OCRCell]]:
        """批量提取"""
        return [self.extract(p) for p in image_paths]
