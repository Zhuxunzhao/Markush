"""Tool package exports.

Keep imports lazy so commands that do not need RDKit/MarkushGrapher can start
in lightweight environments.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ChemicalOCRTool",
    "LLMClient",
    "MarkushGrapherTool",
    "PatentScraperTool",
    "PipelineLogger",
    "RDKitMatcherTool",
    "log",
    "run_parallel",
]


def __getattr__(name: str) -> Any:
    if name == "MarkushGrapherTool":
        from .markush_grapher import MarkushGrapherTool

        return MarkushGrapherTool
    if name == "ChemicalOCRTool":
        from .chemical_ocr import ChemicalOCRTool

        return ChemicalOCRTool
    if name == "RDKitMatcherTool":
        from .rdkit_matcher import RDKitMatcherTool

        return RDKitMatcherTool
    if name == "PatentScraperTool":
        from .patent_scraper import PatentScraperTool

        return PatentScraperTool
    if name == "LLMClient":
        from .llm_client import LLMClient

        return LLMClient
    if name in {"log", "PipelineLogger"}:
        from .logger import PipelineLogger, log

        return {"log": log, "PipelineLogger": PipelineLogger}[name]
    if name == "run_parallel":
        from .async_utils import run_parallel

        return run_parallel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
