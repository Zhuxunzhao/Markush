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
        return """You are a patent analysis report writer.
Your task is to synthesize technical analysis results into a clear,
well-structured report suitable for patent professionals.

The report should include:
1. Executive summary (1-2 sentences)
2. Technical analysis details
3. Conclusion with confidence level
4. Recommendations (if applicable)

Output JSON:
- "executive_summary": string
- "detailed_analysis": string (markdown formatted)
- "conclusion": string
- "confidence": "high" / "moderate" / "low" / "very_low"
- "recommendations": list of strings
"""

    def build_user_prompt(self, **kwargs) -> str:
        report_type = kwargs.get("report_type", "infringement")
        analysis_data = kwargs["analysis_data"]

        if report_type == "infringement":
            return self._build_infringement_prompt(analysis_data)
        else:
            return self._build_patentability_prompt(analysis_data)

    def _build_infringement_prompt(self, data: dict) -> str:
        return f"""## Report Type: Patent Infringement Analysis

## Patent: {data.get('patent_id', 'N/A')}
## Target Molecule: {data.get('target_smiles', 'N/A')}

## Markush Structure
`{data.get('markush_caption', 'N/A')}`

## R-group Matching Result
```json
{data.get('fused_match', 'N/A')}
```

## Requirements Examination
Protected: {data.get('is_protected', 'N/A')}
Reasoning: {data.get('requirements_reasoning', 'N/A')}
R-group analysis:
```json
{data.get('r_group_analysis', 'N/A')}
```

Generate a comprehensive infringement analysis report."""

    def _build_patentability_prompt(self, data: dict) -> str:
        return f"""## Report Type: Patentability Analysis

## Proposed Structure
`{data.get('proposed_cxsmiles', 'N/A')}`

## Technical Domain
{data.get('tech_domain', 'N/A')}

## Novelty Assessment
Score: {data.get('novelty_score', 'N/A')}
Novel features: {data.get('novel_features', 'N/A')}
Overlapping features: {data.get('overlapping_features', 'N/A')}

## Prior Art Summary
{data.get('prior_art_summary', 'N/A')}

## Risk Points
{data.get('risk_points', 'N/A')}

Generate a comprehensive patentability analysis report."""

    def parse_response(self, response: dict) -> dict:
        return {
            "executive_summary": response.get("executive_summary", ""),
            "detailed_analysis": response.get("detailed_analysis", ""),
            "conclusion": response.get("conclusion", ""),
            "confidence": response.get("confidence", "very_low"),
            "recommendations": response.get("recommendations", []),
        }
