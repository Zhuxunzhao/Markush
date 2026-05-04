"""Pipeline package exports.

Imports are lazy so the LLM-only workflow can be imported without loading
RDKit/MarkushGrapher-dependent modules.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "InfringementPipeline",
    "LLMInfringementPipeline",
    "PatentabilityPipeline",
]


def __getattr__(name: str) -> Any:
    if name == "InfringementPipeline":
        from .infringement import InfringementPipeline

        return InfringementPipeline
    if name == "LLMInfringementPipeline":
        from .llm_infringement import LLMInfringementPipeline

        return LLMInfringementPipeline
    if name == "PatentabilityPipeline":
        from .patentability import PatentabilityPipeline

        return PatentabilityPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
