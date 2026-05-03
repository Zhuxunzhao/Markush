"""现有技术检索 Agent — 搜索与拟申请结构相关的现有专利"""

from __future__ import annotations
from typing import Any

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION
from schemas.types import PriorArt


class PriorArtSearcherAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""You are a patent prior art search expert in the chemical domain.
Given a proposed Markush structure and technical domain description,
identify the most relevant existing patents that could affect patentability.

{MARKUSH_STRING_DEFINITION}

Your search strategy should consider:
1. Core scaffold similarity
2. R-group position and type overlap
3. Same therapeutic/application area
4. Key structural motifs

Output JSON:
- "search_queries": list of search queries to find related patents
- "patent_ids": list of candidate patent IDs only when you are confident they are real and relevant; otherwise return []
- "reasoning": explanation of your search strategy
- "key_structural_features": list of features to focus the search on

Rules:
- Do not invent patent IDs.
- If you are unsure whether an ID exists, omit it and focus on search_queries / key_structural_features.
"""

    def build_user_prompt(self, **kwargs) -> str:
        proposed_cxsmiles = kwargs["proposed_cxsmiles"]
        tech_domain = kwargs.get("tech_domain", "")
        additional_context = kwargs.get("additional_context", "")

        prompt = f"""## Proposed Markush Structure
{proposed_cxsmiles}

## Technical Domain
{tech_domain}
"""
        if additional_context:
            prompt += f"\n## Additional Context\n{additional_context}\n"

        prompt += "\nIdentify relevant prior art patents for this structure."
        return prompt

    def parse_response(self, response: dict) -> dict:
        return {
            "search_queries": response.get("search_queries", []),
            "patent_ids": response.get("patent_ids", []),
            "reasoning": response.get("reasoning", ""),
            "key_structural_features": response.get("key_structural_features", []),
        }
