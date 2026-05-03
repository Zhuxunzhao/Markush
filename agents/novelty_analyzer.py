"""新颖性分析 Agent — 评估拟申请 Markush 结构相对于现有技术的新颖性"""

from __future__ import annotations
from typing import Any

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION
from schemas.types import PriorArt


class NoveltyAnalyzerAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""你是一名化学领域的专利新颖性分析专家。
你的任务是将拟申请 Markush 结构与现有技术专利进行比较，评估其新颖性。

{MARKUSH_STRING_DEFINITION}

请考虑：
1. 结构重叠：拟申请结构的核心骨架是否与现有技术重叠？
2. R 基团范围：拟申请的 R 基团范围相对现有技术更宽还是更窄？
3. 区分特征：哪些结构特征能将拟申请结构与现有技术区分开？

输出 JSON：
- "novelty_score": float，范围 0-1；1 表示完全新颖，0 表示完全被现有技术预见
- "overlapping_features": 与现有技术重叠的结构特征列表
- "novel_features": 真正具有新颖性的特征列表
- "risk_points": 可能导致驳回的具体风险列表
- "suggestions": 提高可专利性的修改建议列表
- "reasoning": 中文详细分析
"""

    def build_user_prompt(self, **kwargs) -> str:
        proposed_cxsmiles = kwargs["proposed_cxsmiles"]
        prior_arts: list[PriorArt] = kwargs.get("prior_arts", [])
        tech_domain = kwargs.get("tech_domain", "")

        prompt = f"""## 拟申请 Markush 结构
{proposed_cxsmiles}

## 技术领域
{tech_domain}

## 现有技术专利
"""
        for i, pa in enumerate(prior_arts):
            prompt += f"\n### 现有技术 {i+1}: {pa.patent_id}（相关度: {pa.relevance_score:.2f}）\n"
            prompt += f"重叠描述: {pa.overlap_description}\n"
            for ms in pa.markush_structures:
                prompt += f"  Markush: {ms.cxsmiles}\n"

        prompt += "\n请评估拟申请结构的新颖性。"
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
