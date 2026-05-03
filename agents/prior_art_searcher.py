"""现有技术检索 Agent — 搜索与拟申请结构相关的现有专利"""

from __future__ import annotations
from typing import Any

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION
from schemas.types import PriorArt


class PriorArtSearcherAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return f"""你是一名化学领域的专利现有技术检索专家。
给定拟申请的 Markush 结构和技术领域描述后，请识别最可能影响可专利性的相关现有专利。

{MARKUSH_STRING_DEFINITION}

你的检索策略应考虑：
1. 核心骨架相似性
2. R 基团位置与类型的重叠
3. 相同治疗领域或应用领域
4. 关键结构片段

输出 JSON：
- "search_queries": 用于检索相关专利的查询语句列表
- "patent_ids": 候选专利号列表；只有在你确信专利号真实且相关时才填写，否则返回 []
- "reasoning": 中文说明你的检索策略
- "key_structural_features": 检索时应重点关注的结构特征列表

规则：
- 不要编造专利号。
- 如果不确定某个专利号是否真实存在，请省略它，重点输出 search_queries 和 key_structural_features。
"""

    def build_user_prompt(self, **kwargs) -> str:
        proposed_cxsmiles = kwargs["proposed_cxsmiles"]
        tech_domain = kwargs.get("tech_domain", "")
        additional_context = kwargs.get("additional_context", "")

        prompt = f"""## 拟申请 Markush 结构
{proposed_cxsmiles}

## 技术领域
{tech_domain}
"""
        if additional_context:
            prompt += f"\n## 补充上下文\n{additional_context}\n"

        prompt += "\n请识别与该结构相关的现有技术专利。"
        return prompt

    def parse_response(self, response: dict) -> dict:
        return {
            "search_queries": response.get("search_queries", []),
            "patent_ids": response.get("patent_ids", []),
            "reasoning": response.get("reasoning", ""),
            "key_structural_features": response.get("key_structural_features", []),
        }
