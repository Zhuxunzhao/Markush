"""R 基团约束检查 Agent — 判断 R 基团是否满足专利权利要求

复用 patent_finder/agents/requirements_examinator.py 的核心逻辑。
最终决策者：输出 is_protected。
"""

from __future__ import annotations
import json
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
        return f"""你是一名化学专利与分子表示专家。
你的任务是判断给定分子是否落入特定专利的保护范围。

{MARKUSH_STRING_DEFINITION}
{RGROUP_MAPPING_DEFINITION}

特别注意：
- 子结构匹配工具输出的 caption-local R 标签不一定等同于权利要求中的 claim 标签。
- 如果输入中提供了“显式 R-group 标签对齐结果”，你必须使用对齐后的 claim label 映射进行权利要求审查。
- 不要把原始 caption label 直接套用到同名 claim label；原始映射只可作为结构分解证据。
- 重点检查子结构匹配结果中的 R 基团取值是否符合权利要求文本中的限定。
- 仔细评估每个 R 基团及其对应取代基是否满足专利保护条件。
- 即使分子骨架匹配 Markush，也必须逐一对照权利要求文本核验每个 R 基团取值。
- 分析中要写明每个 R 基团在权利要求中的对应定义。
- 对 "is_protected" 结论要谨慎。只要任一 R 基团取值不被权利要求覆盖，该分子就不落入专利保护范围。
- 如果所有 R 基团取值都被权利要求覆盖，应明确给出 "is_protected": true，并提供清晰理由。

{CONFIDENCE_SCORE_DEFINITION}

输出 JSON：
- "is_protected": boolean，最终判断
- "confidence": "high" / "moderate" / "low" / "very_low"
- "reasoning": 中文逐步详细解释
- "r_group_analysis": dict，将每个 R 基团映射到：
  - "value": 实际 SMILES
  - "covered": boolean
  - "claim_definition": 权利要求对该位置的限定
  - "reason": 为什么覆盖或不覆盖
"""

    def build_user_prompt(self, **kwargs) -> str:
        markush_caption = kwargs["markush_caption"]
        target_smiles = kwargs["target_smiles"]
        r_group_matching = kwargs["r_group_matching"]
        claim_text = kwargs["claim_text"]
        original_r_group_matching = kwargs.get("original_r_group_matching")
        label_alignment = kwargs.get("label_alignment")

        effective_matching_json = json.dumps(
            r_group_matching,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        original_matching_json = json.dumps(
            original_r_group_matching,
            ensure_ascii=False,
            indent=2,
            default=str,
        ) if original_r_group_matching is not None else "N/A"
        label_alignment_json = json.dumps(
            label_alignment,
            ensure_ascii=False,
            indent=2,
            default=str,
        ) if label_alignment is not None else "N/A"

        prompt = f"""## Markush 权利要求
`{markush_caption}`

## 用于权利要求审查的 R-group 映射（已对齐为 claim label）
```json
{effective_matching_json}
```

## 原始 caption-local 子结构匹配结果（仅作结构分解证据，不可直接套 claim 同名变量）
```json
{original_matching_json}
```

## 显式 R-group 标签对齐结果
```json
{label_alignment_json}
```

## 查询分子
`{target_smiles}`

## 权利要求限定文本
```
{self.truncate(claim_text)}
```

请判断每个 R 基团取值是否被权利要求覆盖。
请逐一对照权利要求文本分析每个对齐后的 claim R 基团。"""
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
