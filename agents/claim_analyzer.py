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
        return f"""你是一名专注化学专利的权利要求分析专家。
你的任务是分析专利权利要求，识别其中的 Markush 结构及其约束条件。

{MARKUSH_STRING_DEFINITION}

关键分析步骤：
1. 找出所有包含 Markush 结构的独立权利要求。
2. 对每个 Markush 权利要求提取：
   - Markush 结构（如果图像识别结果中提供了）
   - R 基团约束：每个 R 基团可取哪些值
   - 其他附加条件，例如盐形式、立体化学要求等
3. 找出保护范围最宽的独立权利要求，并将其作为主权利要求。

你必须输出一个 JSON object，字段如下：
- "markush_claims": 权利要求对象列表，每个对象包含：
  - "claim_number": int
  - "markush_caption": 可用的 Markush 字符串；若无法确定则为空字符串
  - "r_group_constraints": dict，将 R 基团标签映射到对应文字约束
  - "additional_conditions": 权利要求中提到的其他条件列表
- "summary": 对专利保护范围的简要中文总结
- "primary_markush_caption": 最相关或保护范围最宽权利要求对应的 Markush caption
"""

    def build_user_prompt(self, **kwargs) -> str:
        claims_text = kwargs["claims_text"]
        markush_captions = kwargs.get("markush_captions", [])

        prompt = f"## 专利权利要求文本\n{self.truncate(claims_text)}\n\n"
        if markush_captions:
            prompt += "## 已识别的 Markush 结构（来自图像识别）\n"
            for i, cap in enumerate(markush_captions):
                prompt += f"{i+1}. `{cap}`\n"
        prompt += "\n请分析权利要求，并提取 Markush 结构约束。"
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
