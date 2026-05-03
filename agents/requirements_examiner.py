"""R 基团约束检查 Agent — 判断 R 基团是否满足专利权利要求

复用 patent_finder/agents/requirements_examinator.py 的核心逻辑。
最终决策者：输出 is_protected。
"""

from __future__ import annotations
from typing import Any

from agents.base import (
    BaseAgent,
    MARKUSH_STRING_DEFINITION,
    RGROUP_MAPPING_DEFINITION,
    CONFIDENCE_SCORE_DEFINITION,
)
from schemas.types import RequirementsResult, Confidence


class RequirementsExaminerAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""You are an expert in chemical patents and molecular representations.
You are tasked with determining whether a given molecule is covered under the
protection scope of a specific patent.

{MARKUSH_STRING_DEFINITION}
{RGROUP_MAPPING_DEFINITION}

Special Attention Required:
- Pay particular attention to the matching of R-group values from the substructure
  match result with the stipulations outlined in the claim requirement text.
- Meticulously assess whether each R-group and its corresponding substitutions
  align with the conditions specified for patent coverage.
- Though the molecule's skeleton may match the Markush, you must verify the value
  of each R-group by comparing them against the claim requirement text one by one.
- Also mention the corresponding definition of each R-group in your analysis.
- Be careful to draw an "is_protected" conclusion. If ANY of the R-group values
  are not protected by the claim, the molecule is NOT protected by the patent.
- If you do find every R-group value is protected by the claim, don't be afraid
  to draw an "is_protected" conclusion. But provide clear reasoning.

{CONFIDENCE_SCORE_DEFINITION}

Output JSON:
- "is_protected": boolean (final decision)
- "confidence": "high" / "moderate" / "low" / "very_low"
- "reasoning": detailed step-by-step explanation
- "r_group_analysis": dict mapping each R-group to:
  - "value": the actual SMILES
  - "covered": boolean
  - "claim_definition": what the claim requires for this position
  - "reason": why it is/isn't covered
"""

    def build_user_prompt(self, **kwargs) -> str:
        markush_caption = kwargs["markush_caption"]
        target_smiles = kwargs["target_smiles"]
        r_group_matching = kwargs["r_group_matching"]
        claim_text = kwargs["claim_text"]

        prompt = f"""## Markush Claim
`{markush_caption}`

## Current Substructure Match Result
```json
{r_group_matching}
```

## Query Molecule
`{target_smiles}`

## Claim Requirement Text
```
{self.truncate(claim_text)}
```

Determine whether each R-group value is covered by the claim requirements.
Analyze each R-group one by one against the claim text."""
        return prompt

    def parse_response(self, response: dict) -> RequirementsResult:
        confidence_raw = response.get("confidence", Confidence.VERY_LOW.value)
        try:
            confidence = Confidence(confidence_raw)
        except ValueError:
            confidence = Confidence.VERY_LOW

        return RequirementsResult(
            is_protected=response.get("is_protected", False),
            reasoning=response.get("reasoning", ""),
            confidence=confidence,
            r_group_analysis=response.get("r_group_analysis", {}),
        )
