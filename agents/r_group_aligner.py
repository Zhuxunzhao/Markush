"""R-group 标签语义对齐 Agent。

把图像/RDKit 产生的 caption-local 标签映射到权利要求文本中的法律变量标签。
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from agents.base import (
    BaseAgent,
    MARKUSH_STRING_DEFINITION,
    RGROUP_MAPPING_DEFINITION,
    CONFIDENCE_SCORE_DEFINITION,
)
from schemas.types import Confidence, RGroupAlignmentResult


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


class RGroupAlignmentAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return f"""你是一名化学专利 Markush 变量语义对齐专家。
你的任务不是判断是否侵权，而是把结构匹配工具输出的 caption-local R 标签，
对齐到权利要求文本中的法律变量标签。

{MARKUSH_STRING_DEFINITION}
{RGROUP_MAPPING_DEFINITION}

关键规则：
- caption label 是图像识别/RDKit 分解中的局部占位标签；claim label 是权利要求中的法律变量。
- 不要假设同名标签必然同义。例如 caption 的 "R1" 可能对应 claim 的 "X"。
- 只能根据 Markush caption 中的连接位置、目标分子的取代基、claim 变量定义和 claim 文本上下文建立映射。
- 输出的 aligned_r_group_matching 必须使用 claim 文本中的自然标签，例如 "X"、"R1"、"R2"、"R[6]"、"Ra"。
- 如果无法可靠对齐某个 caption label，把它放入 unresolved_labels，不要编造映射。
- 标签规范化只用于理解：R1 与 R[1] 可视为同一编号写法，但输出应优先使用 claim 文本中的写法。

US9655879 回归示例：
- caption map 为 {{"R1": "Nc1cc(C(=O)O)cc(C(=O)O)c1", "R2": "C", "R3": "C"}}。
- claim 中羰基右端变量是 X，季碳上的两个变量是 R1/R2。
- 因此应对齐为 {{"X": "Nc1cc(C(=O)O)cc(C(=O)O)c1", "R1": "C", "R2": "C"}}。

{CONFIDENCE_SCORE_DEFINITION}

输出 JSON：
- "aligned_r_group_matching": dict，claim-label 到取代基 SMILES 的映射
- "label_alignment": dict，caption-label 到对象的映射，每个对象包含：
  - "claim_label": 对应的 claim 变量标签
  - "confidence": "high" / "moderate" / "low" / "very_low"
  - "claim_definition": 权利要求中该 claim 变量的限定
  - "reason": 为什么这样对齐
- "unresolved_labels": list，无法可靠对齐的 caption label
- "reasoning": 中文说明整体对齐依据
- "confidence": "high" / "moderate" / "low" / "very_low"
"""

    def build_user_prompt(self, **kwargs) -> str:
        markush_caption = kwargs["markush_caption"]
        target_smiles = kwargs["target_smiles"]
        r_group_matching = kwargs["r_group_matching"]
        claim_analysis = kwargs.get("claim_analysis")
        claim_text = kwargs["claim_text"]

        claim_analysis_json = json.dumps(
            _jsonable(claim_analysis),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        r_group_matching_json = json.dumps(
            r_group_matching,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        return f"""## Markush caption（caption-local 标签来源）
`{markush_caption}`

## 查询分子
`{target_smiles}`

## 原始 caption-local R-group 匹配结果
```json
{r_group_matching_json}
```

## ClaimAnalyzer 提取的权利要求变量与约束
```json
{claim_analysis_json}
```

## 原始权利要求文本
```
{self.truncate(claim_text)}
```

请把原始匹配结果中的 caption-local 标签显式对齐到 claim 文本中的法律变量标签。
只做变量语义对齐，不要判断每个取代基是否被 claim 覆盖。"""

    def parse_response(self, response: dict) -> RGroupAlignmentResult:
        confidence_raw = response.get("confidence", Confidence.VERY_LOW.value)
        try:
            confidence = Confidence(confidence_raw)
        except ValueError:
            confidence = Confidence.VERY_LOW

        aligned = response.get("aligned_r_group_matching", {})
        label_alignment = response.get("label_alignment", {})
        unresolved = response.get("unresolved_labels", [])

        return RGroupAlignmentResult(
            aligned_r_group_matching=aligned if isinstance(aligned, dict) else {},
            label_alignment=label_alignment if isinstance(label_alignment, dict) else {},
            unresolved_labels=[str(label) for label in unresolved] if isinstance(unresolved, list) else [],
            reasoning=response.get("reasoning", ""),
            confidence=confidence,
        )
