"""新颖性分析 Agent — 评估拟申请 Markush 结构相对于现有技术的新颖性"""

from __future__ import annotations
from typing import Any

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION
from schemas.types import PriorArt


class NoveltyAnalyzerAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""You are a patent novelty analysis expert in the chemical domain.
Your task is to assess the novelty of a proposed Markush structure by comparing
it against existing prior art patents.

{MARKUSH_STRING_DEFINITION}

Consider:
1. Structural overlap: does the proposed structure's core skeleton overlap with prior art?
2. R-group scope: are the proposed R-group ranges broader/narrower than prior art?
3. Differentiation: what structural features distinguish the proposed structure?

Output JSON:
- "novelty_score": float 0-1 (1 = completely novel, 0 = fully anticipated)
- "overlapping_features": list of structural features that overlap with prior art
- "novel_features": list of features that are genuinely new
- "risk_points": list of specific risks for patent rejection
- "suggestions": list of modifications to improve patentability
- "reasoning": detailed analysis
"""

    def build_user_prompt(self, **kwargs) -> str:
        proposed_cxsmiles = kwargs["proposed_cxsmiles"]
        prior_arts: list[PriorArt] = kwargs.get("prior_arts", [])
        tech_domain = kwargs.get("tech_domain", "")

        prompt = f"""## Proposed Markush Structure
{proposed_cxsmiles}

## Technical Domain
{tech_domain}

## Prior Art Patents
"""
        for i, pa in enumerate(prior_arts):
            prompt += f"\n### Prior Art {i+1}: {pa.patent_id} (relevance: {pa.relevance_score:.2f})\n"
            prompt += f"Overlap: {pa.overlap_description}\n"
            for ms in pa.markush_structures:
                prompt += f"  Markush: {ms.cxsmiles}\n"

        prompt += "\nAssess the novelty of the proposed structure."
        return prompt

    def parse_response(self, response: dict) -> dict:
        return {
            "novelty_score": response.get("novelty_score", 0.0),
            "overlapping_features": response.get("overlapping_features", []),
            "novel_features": response.get("novel_features", []),
            "risk_points": response.get("risk_points", []),
            "suggestions": response.get("suggestions", []),
            "reasoning": response.get("reasoning", ""),
        }
