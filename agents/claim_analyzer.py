"""权利要求分析 Agent — 从专利文本中提取和分析 Markush 相关权利要求"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION


@dataclass
class ClaimAnalysis:
    """ClaimAnalyzer 的结构化输出"""
    markush_claims: list[dict] = field(default_factory=list)
    # Each claim: {"claim_number": int, "markush_caption": str,
    #              "r_group_constraints": dict, "additional_conditions": list}
    summary: str = ""
    primary_markush_caption: str = ""  # 最相关的 Markush caption


class ClaimAnalyzerAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""You are a patent claim analysis expert specializing in chemical patents.
Your task is to analyze patent claims and identify Markush structures and their constraints.

{MARKUSH_STRING_DEFINITION}

Key analysis steps:
1. Identify all independent claims containing Markush structures
2. For each Markush claim, extract:
   - The Markush structure (if available from image recognition)
   - R-group constraints: what values each R-group can take
   - Additional conditions (e.g., salt forms, stereochemistry requirements)
3. Identify the broadest independent claim as the primary claim

You must output a JSON object with:
- "markush_claims": list of claim objects, each with:
  - "claim_number": int
  - "markush_caption": the Markush string if available
  - "r_group_constraints": dict mapping R-group labels to their textual constraints
  - "additional_conditions": list of other conditions mentioned in the claim
- "summary": brief summary of the patent's protection scope
- "primary_markush_caption": the Markush caption from the most relevant/broadest claim
"""

    def build_user_prompt(self, **kwargs) -> str:
        claims_text = kwargs["claims_text"]
        markush_captions = kwargs.get("markush_captions", [])

        prompt = f"## Patent Claims Text\n{self.truncate(claims_text)}\n\n"
        if markush_captions:
            prompt += "## Identified Markush Structures (from image recognition)\n"
            for i, cap in enumerate(markush_captions):
                prompt += f"{i+1}. `{cap}`\n"
        prompt += "\nAnalyze the claims and extract Markush structure constraints."
        return prompt

    def parse_response(self, response: dict) -> ClaimAnalysis:
        claims = response.get("markush_claims", [])
        summary = response.get("summary", "")
        primary = response.get("primary_markush_caption", "")

        # If no primary caption extracted, try to get from first claim
        if not primary and claims:
            primary = claims[0].get("markush_caption", "")

        return ClaimAnalysis(
            markush_claims=claims,
            summary=summary,
            primary_markush_caption=primary,
        )
