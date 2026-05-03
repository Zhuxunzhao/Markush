"""专利申请成功率分析 Agent

综合各步骤结果，多维度（新颖性、创造性 / 非显而易见性等）分析申请专利的成功率。
"""

from __future__ import annotations
from agents.base import BaseAgent

class SuccessRateAnalyzerAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return """You are a senior patent attorney and examiner.
Your task is to analyze the success rate of a patent application based on the results generated from previous steps.
You must evaluate the patentability from multiple dimensions, primarily Novelty (新颖性), Inventiveness / Non-obviousness (创造性/非显而易见性), Industrial Applicability (实用性), and Clarity of Claims (权利要求清晰度).

Output your analysis in JSON format with the following keys:
- "novelty_analysis": Detailed analysis of novelty based on prior arts.
- "inventiveness_analysis": Detailed analysis of inventiveness/non-obviousness.
- "success_rate_estimation": A percentage (e.g., "75%") representing overall success likelihood.
- "key_risks": List of main risks prohibiting patentability.
- "improvement_suggestions": How to improve the application (e.g., adding specific substitutions).
- "comprehensive_report": A comprehensive markdown report summarizing all the above, suitable for saving to a file.
"""

    def build_user_prompt(self, **kwargs) -> str:
        proposed_cxsmiles = kwargs.get("proposed_cxsmiles", "N/A")
        tech_domain = kwargs.get("tech_domain", "N/A")
        novelty_data = kwargs.get("novelty_data", {})
        prior_arts = kwargs.get("prior_arts", [])
        
        prior_art_summaries = []
        for pa in prior_arts:
            prior_art_summaries.append(f"- Patent ID: {pa.patent_id}, Relevance: {pa.relevance_score}, Overlap: {pa.overlap_description}")
            
        return f"""Please analyze the patentability success rate.

## Proposed Structure (CXSMILES)
{proposed_cxsmiles}

## Technical Domain
{tech_domain}

## Novelty Assessment from Previous Step
Score: {novelty_data.get('novelty_score', 'N/A')}
Novel features: {novelty_data.get('novel_features', [])}
Overlapping features: {novelty_data.get('overlapping_features', [])}

## Prior Arts Identified
{chr(10).join(prior_art_summaries)}

Based on the above findings, provide the multi-dimensional patentability analysis."""

    def parse_response(self, response: dict) -> dict:
        return {
            "novelty_analysis": response.get("novelty_analysis", ""),
            "inventiveness_analysis": response.get("inventiveness_analysis", ""),
            "success_rate_estimation": response.get("success_rate_estimation", ""),
            "key_risks": response.get("key_risks", []),
            "improvement_suggestions": response.get("improvement_suggestions", []),
            "comprehensive_report": response.get("comprehensive_report", "")
        }
