"""MarkushGrapher 封装 — 支持本地推理和远程 HTTP 调用

本地模式: 通过子进程调用 markushgrapher conda env 运行推理脚本
远程模式: 调用部署好的 HTTP 服务（兼容 patent_finder 的 image_parser 接口）
"""

from __future__ import annotations
import base64
import hashlib
import io
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

from schemas.types import MarkushStructure, OCRCell

logger = logging.getLogger("markush.tools.markush_grapher")
_INLINE_RGROUP_RE = re.compile(r"<r>.*?</r>", re.IGNORECASE)

# Paths resolved once at import time
_TOOLS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TOOLS_DIR.parent
_INFER_SCRIPT = str(_TOOLS_DIR / "markushgrapher_infer.py")
_MG_ROOT = str(_PROJECT_ROOT / "third_party" / "MarkushGrapher")
_VENDORED_PYTHON = str(Path(_MG_ROOT) / ".venvs" / "markushgrapher" / "bin" / "python")


class MarkushGrapherTool:
    def __init__(self, config: dict):
        mg_cfg = config["tools"]["markush_grapher"]
        self.mode = mg_cfg.get("mode", "remote")
        self.endpoint = mg_cfg.get("endpoint", "")
        self.request_timeout = int(mg_cfg.get("request_timeout", 1800))
        self.root_dir = self._resolve_path(
            mg_cfg.get("root_dir")
            or os.environ.get("MARKUSHGRAPHER_ROOT")
            or _MG_ROOT
        )
        self.python_bin = self._resolve_path(
            mg_cfg.get("python_bin")
            or os.environ.get("MARKUSHGRAPHER_PYTHON_BIN")
            or _VENDORED_PYTHON
        )
        self.model_dir = self._resolve_path(
            mg_cfg.get("model_dir")
            or os.path.join(self.root_dir, "models", "markushgrapher-2")
        )
        self.ocr_model_dir = mg_cfg.get(
            "ocr_model_dir",
            os.path.join(self.root_dir, "models", "chemicalocr"),
        )
        self.ocr_model_dir = self._resolve_path(self.ocr_model_dir)
        self.cache_dir = self._resolve_path(
            mg_cfg.get("cache_dir", "cache/markush_grapher")
        )
        self.num_beams = int(mg_cfg.get("num_beams", 1))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        image_path: str,
        ocr_cells: Optional[list[OCRCell]] = None,
    ) -> MarkushStructure:
        """Predict the Markush structure in a single image."""
        results = self.predict_batch([image_path])
        return results[0]

    def predict_batch(self, image_paths: list[str]) -> list[MarkushStructure]:
        """Predict Markush structures for multiple images.

        Local mode loads the model once for all images (efficient).
        """
        if self.mode == "remote":
            return self._predict_batch_remote(image_paths)
        return self._predict_local_batch(image_paths)

    def clear_cache(self, image_path: str) -> None:
        """Remove the cached prediction for one image if it exists."""
        try:
            cache_path = self._cache_path(image_path)
            if cache_path.exists():
                cache_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to clear MarkushGrapher cache for {image_path}: {e}")

    # ------------------------------------------------------------------
    # Local inference via subprocess
    # ------------------------------------------------------------------

    def _predict_local_batch(self, image_paths: list[str]) -> list[MarkushStructure]:
        """Call markushgrapher_infer.py in the markushgrapher conda env."""
        if not os.path.isfile(self.python_bin):
            raise RuntimeError(
                f"markushgrapher Python not found at {self.python_bin}. "
                "Run scripts/setup_markushgrapher_env.sh or set "
                "MARKUSHGRAPHER_PYTHON_BIN."
            )
        if not self.model_dir or not os.path.isdir(self.model_dir):
            raise RuntimeError(
                f"MarkushGrapher model_dir not found: {self.model_dir!r}. "
                "Run scripts/download_markush_assets.py or set "
                "tools.markush_grapher.model_dir."
            )
        if not os.path.isdir(self.ocr_model_dir):
            raise RuntimeError(
                f"ChemicalOCR model_dir not found: {self.ocr_model_dir!r}. "
                "Run scripts/download_markush_assets.py or set "
                "tools.markush_grapher.ocr_model_dir."
            )

        # Only pass images that exist on disk
        valid = [p for p in image_paths if os.path.exists(p)]
        if not valid:
            logger.warning("No valid image paths provided to MarkushGrapherTool.")
            return [_empty_structure(p) for p in image_paths]

        cached: dict[str, dict] = {}
        missing: list[str] = []
        for path in valid:
            cached_result = self._read_cache(path)
            if cached_result is None:
                missing.append(path)
            else:
                cached[os.path.abspath(path)] = cached_result

        cmd = [
            self.python_bin,
            _INFER_SCRIPT,
            "--model_dir", self.model_dir,
            "--ocr_model_dir", self.ocr_model_dir,
            "--num_beams", str(self.num_beams),
            *missing,
        ]

        raw: list[dict] = list(cached.values())
        if missing:
            logger.info(
                "Running local MarkushGrapher inference on "
                f"{len(missing)} image(s); cache hit {len(cached)}/{len(valid)}…"
            )
            proc = self._run_local_inference(cmd)

            if proc.returncode != 0 and self._is_cuda_oom(proc.stderr):
                logger.warning(
                    "MarkushGrapher hit CUDA OOM; retrying inference on CPU."
                )
                proc = self._run_local_inference(cmd, force_cpu=True)

            if proc.returncode != 0:
                raise RuntimeError(
                    f"MarkushGrapher inference failed (exit {proc.returncode}):\n"
                    f"stdout tail: {proc.stdout[-1000:]}\n"
                    f"stderr tail: {proc.stderr[-2000:]}"
                )

            fresh = self._parse_local_results(proc.stdout)
            for item in fresh:
                path = item.get("path", "")
                if path:
                    self._write_cache(path, item)
            raw.extend(fresh)
        else:
            logger.info(f"Using cached MarkushGrapher results for {len(valid)} image(s).")

        # Build a path→result map for ordering
        result_map: dict[str, dict] = {
            os.path.abspath(r["path"]): r for r in raw if r.get("path")
        }

        structures: list[MarkushStructure] = []
        for path in image_paths:
            abs_path = os.path.abspath(path)
            if abs_path not in result_map:
                structures.append(_empty_structure(path))
                continue
            r = result_map[abs_path]
            structures.append(
                MarkushStructure(
                    cxsmiles=r.get("smi", ""),
                    substituent_table={},
                    caption=r.get("caption", ""),
                    source_image_path=path,
                    score=float(r.get("score", 0.0)),
                    is_markush=_result_is_markush(r),
                )
            )
        return structures

    def _cache_path(self, image_path: str) -> Path:
        path = Path(image_path).resolve()
        stat = path.stat()
        payload = {
            "path": str(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "model_dir": self.model_dir,
            "ocr_model_dir": self.ocr_model_dir,
            "num_beams": self.num_beams,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return Path(self.cache_dir) / f"{digest}.json"

    def _read_cache(self, image_path: str) -> Optional[dict]:
        try:
            cache_path = self._cache_path(image_path)
            if not cache_path.exists():
                return None
            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data["path"] = os.path.abspath(image_path)
            return data
        except Exception as e:
            logger.warning(f"Failed to read MarkushGrapher cache for {image_path}: {e}")
            return None

    def _write_cache(self, image_path: str, result: dict) -> None:
        try:
            cache_path = self._cache_path(image_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {**result, "path": os.path.abspath(image_path)}
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to write MarkushGrapher cache for {image_path}: {e}")

    def _run_local_inference(
        self,
        cmd: list[str],
        *,
        force_cpu: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        env = self._subprocess_env(force_cpu=force_cpu)

        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=1800,
            )
        except subprocess.TimeoutExpired:
            mode = "CPU fallback" if force_cpu else "default mode"
            raise RuntimeError(f"MarkushGrapher inference timed out after 30 minutes ({mode}).")

    @staticmethod
    def _is_cuda_oom(stderr: str) -> bool:
        lowered = stderr.lower()
        return "cuda out of memory" in lowered or "runtimeerror: cuda error: out of memory" in lowered

    def _subprocess_env(self, *, force_cpu: bool) -> dict[str, str]:
        env = {**os.environ, "PYTHONPATH": self.root_dir, "MG_ROOT": self.root_dir}
        if force_cpu:
            # Hide CUDA devices so both ChemicalOCR and MarkushGrapher fall back to CPU.
            env["CUDA_VISIBLE_DEVICES"] = ""
        return env

    @staticmethod
    def _parse_local_results(stdout: str) -> list[dict]:
        # The inference subprocess may print transformers/torch progress lines
        # (e.g. "ChemicalOCR loaded…") to stdout before the JSON result.
        # Extract only the trailing JSON array to avoid parse failures.
        match = re.search(r'(\[\s*\{.*\}\s*\])\s*$', stdout, re.DOTALL)
        if not match:
            raise RuntimeError(
                f"No JSON array found in MarkushGrapher stdout:\n"
                f"stdout tail: {stdout[-1000:]}"
            )
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Could not parse MarkushGrapher JSON: {e}\n"
                f"extracted: {match.group(1)[:500]}"
            ) from e

    @staticmethod
    def _resolve_path(value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return str(path)

    # ------------------------------------------------------------------
    # Remote inference via HTTP
    # ------------------------------------------------------------------

    def _predict_batch_remote(self, image_paths: list[str]) -> list[MarkushStructure]:
        prepared: list[tuple[int, str, str]] = []
        structures = [_empty_structure(path) for path in image_paths]
        for idx, path in enumerate(image_paths):
            if not os.path.exists(path):
                logger.warning(f"Image path does not exist: {path}")
                continue
            cached_result = self._read_cache(path)
            if cached_result is not None:
                structures[idx] = self._structure_from_result(path, cached_result)
                continue
            try:
                image = Image.open(path).convert("RGB")
            except Exception as e:
                logger.warning(f"Failed to open image {path}: {e}")
                continue
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            prepared.append((idx, path, base64.b64encode(buf.getvalue()).decode("ascii")))

        if not prepared:
            return structures

        response = requests.post(
            self.endpoint,
            json={"batch_image": [item[2] for item in prepared]},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("MarkushGrapher remote response missing 'data' object")

        required_keys = ("smi", "caption", "score", "markush")
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            raise RuntimeError(
                f"MarkushGrapher remote response missing keys: {', '.join(missing_keys)}"
            )

        expected = len(prepared)
        lengths = {key: len(data[key]) for key in required_keys}
        if any(length != expected for length in lengths.values()):
            raise RuntimeError(
                f"MarkushGrapher remote response length mismatch: expected {expected}, got {lengths}"
            )

        for pos, (idx, path, _) in enumerate(prepared):
            caption = data["caption"][pos]
            result = {
                "path": os.path.abspath(path),
                "smi": data["smi"][pos],
                "caption": caption,
                "score": float(data["score"][pos]),
                "is_markush": bool(data["markush"][pos])
                or _caption_has_markush_signal(caption),
            }
            self._write_cache(path, result)
            structures[idx] = self._structure_from_result(path, result)
        return structures

    @staticmethod
    def _structure_from_result(path: str, result: dict) -> MarkushStructure:
        return MarkushStructure(
            cxsmiles=result.get("smi", ""),
            substituent_table={},
            caption=result.get("caption", ""),
            source_image_path=path,
            score=float(result.get("score", 0.0)),
            is_markush=_result_is_markush(result),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_structure(image_path: str) -> MarkushStructure:
    return MarkushStructure(
        cxsmiles="",
        substituent_table={},
        caption="",
        source_image_path=image_path,
        score=0.0,
        is_markush=False,
    )


def _caption_has_markush_signal(caption: str) -> bool:
    caption = (caption or "").strip()
    return bool(caption) and (
        "<sep>" in caption or _INLINE_RGROUP_RE.search(caption) is not None
    )


def _result_is_markush(result: dict) -> bool:
    if bool(result.get("is_markush", False)):
        return True
    caption = str(result.get("caption") or result.get("smi") or "")
    return _caption_has_markush_signal(caption)
