"""报告生成 Agent — 综合所有分析结果生成最终报告

支持两种报告类型:
1. 侵权分析报告
2. 可专利性分析报告
"""

from __future__ import annotations
from typing import Any

from agents.base import BaseAgent


class ReportGeneratorAgent(BaseAgent):

    @property
    def system_prompt(self) -> str:
        return """你是一名专利分析报告撰写专家。
你的任务是把技术分析结果综合成清晰、结构化、适合专利专业人员阅读的中文报告。

报告应包括：
1. 执行摘要（1-2 句话）
2. 技术分析细节
3. 带置信度的结论
4. 建议（如适用）

输出 JSON：
- "executive_summary": string
- "detailed_analysis": string，使用 Markdown 格式
- "conclusion": string
- "confidence": "high" / "moderate" / "low" / "very_low"
- "recommendations": string 列表
"""

    def build_user_prompt(self, **kwargs) -> str:
        report_type = kwargs.get("report_type", "infringement")
        analysis_data = kwargs["analysis_data"]

        if report_type == "infringement":
            return self._build_infringement_prompt(analysis_data)
        else:
            return self._build_patentability_prompt(analysis_data)

    def _build_infringement_prompt(self, data: dict) -> str:
        return f"""## 报告类型：专利侵权分析

## 专利：{data.get('patent_id', 'N/A')}
## 待评估分子：{data.get('target_smiles', 'N/A')}

## Markush 结构
`{data.get('markush_caption', 'N/A')}`

## 原始 R 基团匹配结果（caption-local label）
```json
{data.get('fused_match', 'N/A')}
```

## 对齐后的 R 基团匹配结果（claim label）
```json
{data.get('claim_aligned_r_group_matching', 'N/A')}
```

## R 基团标签语义对齐
```json
{data.get('label_alignment', 'N/A')}
```

## 权利要求要件审查
是否落入保护范围: {data.get('is_protected', 'N/A')}
推理: {data.get('requirements_reasoning', 'N/A')}
R 基团分析:
```json
{data.get('r_group_analysis', 'N/A')}
```

请生成一份完整的中文侵权分析报告。"""

    def _build_patentability_prompt(self, data: dict) -> str:
        return f"""## 报告类型：可专利性分析

## 拟申请结构
`{data.get('proposed_cxsmiles', 'N/A')}`

## 技术领域
{data.get('tech_domain', 'N/A')}

## 新颖性评估
评分: {data.get('novelty_score', 'N/A')}
新颖特征: {data.get('novel_features', 'N/A')}
重叠特征: {data.get('overlapping_features', 'N/A')}

## 现有技术摘要
{data.get('prior_art_summary', 'N/A')}

## 风险点
{data.get('risk_points', 'N/A')}

请生成一份完整的中文可专利性分析报告。报告正文必须使用以下格式：
一.最终结论
二.相关分析及证据：
    分析/证据1，分析/证据2，分析/证据3，分析/证据4（按实际证据数量输出）
不要保留或复述原始输入全文，只保留结论、必要事实、分析和证据。"""

    def parse_response(self, response: dict) -> dict:
        return {
            "executive_summary": response.get("executive_summary", ""),
            "detailed_analysis": response.get("detailed_analysis", ""),
            "conclusion": response.get("conclusion", ""),
            "confidence": response.get("confidence", "very_low"),
            "recommendations": response.get("recommendations", []),
        }
