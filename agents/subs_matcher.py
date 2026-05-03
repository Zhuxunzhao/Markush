"""取代基验证 Agent — 融合 RDKit 和 NN 的匹配结果

复用 patent_finder/agents/substitutes_matcher.py 的核心逻辑。
"""

from __future__ import annotations
from typing import Any, Optional
import json

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION, RGROUP_MAPPING_DEFINITION
from schemas.types import MatchResult, FusedMatchResult


class SubsMatcherAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""You are an expert in chemical patents and molecular representations.
Your task is to verify the correctness of the substructure match result between
the Markush claim and the query molecule.

{MARKUSH_STRING_DEFINITION}
{RGROUP_MAPPING_DEFINITION}

Rules:
- If RDKit provides a valid match, prefer it (higher reliability for skeleton matching)
- If RDKit fails but NN succeeds, use NN result with lower confidence
- If both provide results, cross-validate: check if R-group values are consistent
- If both fail, the molecule likely does not match the Markush skeleton
- The R-group values are considered correct iff when we replace the R-groups
  in the Markush structure with the corresponding values, we get the query molecule
- Be very cautious about potential protection scope. Misclassification may lead to
  serious legal issues
- In your reasoning, compare each R-group definition with the query molecule,
  and analyze the correctness of the R-group values one by one

Output JSON:
- "r_group_matching": dict of verified R-group mappings (empty dict if no match)
- "reasoning": detailed explanation of your verification process
- "confidence": "high" / "moderate" / "low" / "very_low"
"""

    def build_user_prompt(self, **kwargs) -> str:
        markush_caption = kwargs["markush_caption"]
        target_smiles = kwargs["target_smiles"]
        rdkit_result: Optional[MatchResult] = kwargs.get("rdkit_result")
        nn_result: Optional[MatchResult] = kwargs.get("nn_result")

        prompt = f"""## Markush Structure
`{markush_caption}`

## Target Molecule
`{target_smiles}`

## R-Group Mapping Extracted by Chemical Software (RDKit)
Match: {rdkit_result.is_match if rdkit_result else 'N/A'}
```json
{json.dumps(rdkit_result.r_group_map, indent=2) if rdkit_result and rdkit_result.r_group_map else 'N/A'}
```
Note: {rdkit_result.reasoning if rdkit_result else 'N/A'}

## R-Group Mapping Extracted by Neural Network Model (T5)
Match: {nn_result.is_match if nn_result else 'N/A'}
```json
{json.dumps(nn_result.r_group_map, indent=2) if nn_result and nn_result.r_group_map else 'N/A'}
```
Note: {nn_result.reasoning if nn_result else 'N/A'}

Verify and fuse these results. Provide a verified R-group mapping result explicitly."""
        return prompt

    def parse_response(self, response: dict) -> FusedMatchResult:
        return FusedMatchResult(
            r_group_matching=response.get("r_group_matching", {}),
            reasoning=response.get("reasoning", ""),
        )
