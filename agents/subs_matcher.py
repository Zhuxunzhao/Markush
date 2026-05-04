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
        return f"""你是一名化学专利与分子表示专家。
你的任务是核验 Markush 权利要求与查询分子之间的子结构匹配结果是否正确。

{MARKUSH_STRING_DEFINITION}
{RGROUP_MAPPING_DEFINITION}

规则：
- 如果 RDKit 给出了有效匹配，优先参考 RDKit 结果，因为骨架匹配可靠性更高。
- 如果输入来自 LLM 结构匹配器，必须独立核验其骨架比较和 R 基团取值，不要盲信。
- 如果 RDKit 失败但神经网络结果成功，可以采用神经网络结果，但置信度应降低。
- 在 LLM-only 模式中，LLM 结构匹配器是主要候选来源；若证据不足，应返回空映射。
- 如果两者都给出结果，需要交叉验证 R 基团取值是否一致。
- 如果两者都失败，该分子很可能不匹配 Markush 骨架。
- 只有当把 Markush 结构中的 R 基团替换为对应取代基后能得到查询分子时，R 基团取值才视为正确。
- 对潜在保护范围要非常谨慎，误判可能带来严重法律风险。
- 推理中要逐一比较每个 R 基团定义与查询分子，并逐项分析 R 基团取值是否正确。

输出 JSON：
- "r_group_matching": 经核验的 R 基团映射 dict；如果不匹配则返回空 dict
- "reasoning": 中文详细说明你的核验过程
- "confidence": "high" / "moderate" / "low" / "very_low"
"""

    def build_user_prompt(self, **kwargs) -> str:
        markush_caption = kwargs["markush_caption"]
        target_smiles = kwargs["target_smiles"]
        rdkit_result: Optional[MatchResult] = kwargs.get("rdkit_result")
        nn_result: Optional[MatchResult] = kwargs.get("nn_result")
        llm_match_result: Optional[MatchResult] = kwargs.get("llm_match_result")

        prompt = f"""## Markush 结构
`{markush_caption}`

## 目标分子
`{target_smiles}`

## 化学软件（RDKit）提取的 R 基团映射
是否匹配: {rdkit_result.is_match if rdkit_result else 'N/A'}
```json
{json.dumps(rdkit_result.r_group_map, indent=2) if rdkit_result and rdkit_result.r_group_map else 'N/A'}
```
备注: {rdkit_result.reasoning if rdkit_result else 'N/A'}

## LLM 结构匹配器提取的 R 基团映射
是否匹配: {llm_match_result.is_match if llm_match_result else 'N/A'}
```json
{json.dumps(llm_match_result.r_group_map, indent=2, ensure_ascii=False) if llm_match_result and llm_match_result.r_group_map else 'N/A'}
```
备注: {llm_match_result.reasoning if llm_match_result else 'N/A'}

## 神经网络模型（T5）提取的 R 基团映射
是否匹配: {nn_result.is_match if nn_result else 'N/A'}
```json
{json.dumps(nn_result.r_group_map, indent=2, ensure_ascii=False) if nn_result and nn_result.r_group_map else 'N/A'}
```
备注: {nn_result.reasoning if nn_result else 'N/A'}

请核验并融合上述结果，明确给出经核验的 R 基团映射。"""
        return prompt

    def parse_response(self, response: dict) -> FusedMatchResult:
        return FusedMatchResult(
            r_group_matching=response.get("r_group_matching", {}),
            reasoning=response.get("reasoning", ""),
        )
