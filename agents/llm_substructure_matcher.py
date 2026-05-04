"""LLM-based Markush skeleton and R-group matcher.

This agent replaces the RDKit R-group decomposition step in the LLM-only
infringement workflow. It does not make the final infringement decision; it
only proposes whether the query molecule matches the Markush skeleton and which
claim-local/caption-local variables are instantiated by which substituents.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Optional

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION, RGROUP_MAPPING_DEFINITION
from schemas.types import MatchMethod, MatchResult, MarkushStructure


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


class LLMSubstructureMatcherAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return f"""你是一名谨慎的化学结构匹配专家。
你的任务是复现 RDKitMatcher 的作用：判断查询分子是否匹配 Markush 骨架，并提取 R-group 映射。

{MARKUSH_STRING_DEFINITION}
{RGROUP_MAPPING_DEFINITION}

边界：
- 你只判断骨架和 R-group 分解，不做最终侵权结论。
- 必须先确认查询分子的核心骨架、连接位置、原子类型、环系、官能团和立体化学是否与 Markush 主通式兼容。
- 只有在骨架兼容时才输出 r_group_map；否则 r_group_map 返回空对象。
- 若 Markush caption 是文本化描述而非精确 caption，你仍可根据权利要求和变量定义做保守结构分解，但置信度应降低。
- 不要为了推进后续步骤而编造 R-group 映射。无法可靠分解时，is_match=false 或 null，r_group_map={{}}。

只返回合法 JSON：
- "is_match": boolean 或 null
- "r_group_map": object，键为 caption-local 或 claim-local 变量标签，值为实际取代基 SMILES/短描述
- "confidence": "high" / "moderate" / "low" / "very_low"
- "reasoning": 中文说明骨架比较和每个 R-group 的依据
"""

    def build_user_prompt(self, **kwargs) -> str:
        markush_structure: Optional[MarkushStructure] = kwargs.get("markush_structure")
        markush_caption = kwargs["markush_caption"]
        target_smiles = kwargs["target_smiles"]
        claim_analysis = kwargs.get("claim_analysis")
        claim_text = kwargs.get("claim_text", "")

        structure_json = json.dumps(
            _jsonable(markush_structure),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        claim_analysis_json = json.dumps(
            _jsonable(claim_analysis),
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        return f"""## Markush 结构
`{markush_caption}`

## MarkushStructure 对象
```json
{structure_json}
```

## 查询分子
`{target_smiles}`

## ClaimAnalyzer 提取的变量约束
```json
{claim_analysis_json}
```

## 权利要求文本
```
{self.truncate(claim_text)}
```

请像 RDKit R-group decomposition 一样，先判断骨架是否匹配，再输出可核验的 R-group 映射。"""

    def parse_response(self, response: dict[str, Any]) -> MatchResult:
        r_group_map = response.get("r_group_map", {})
        if not isinstance(r_group_map, dict):
            r_group_map = {}

        confidence = response.get("confidence", "very_low")
        reasoning = response.get("reasoning", "")
        if confidence:
            reasoning = f"[confidence={confidence}] {reasoning}".strip()

        return MatchResult(
            is_match=_coerce_optional_bool(response.get("is_match")),
            r_group_map={str(key): str(value) for key, value in r_group_map.items()}
            if r_group_map
            else None,
            method=MatchMethod.LLM,
            reasoning=reasoning,
        )


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
        if lowered in {"null", "none", "unknown", "uncertain"}:
            return None
    return bool(value)
