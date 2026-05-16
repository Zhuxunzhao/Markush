"""专利申请成功率分析 Agent

综合各步骤结果，多维度（新颖性、创造性 / 非显而易见性等）分析申请专利的成功率。
"""

from __future__ import annotations
from agents.base import BaseAgent

class SuccessRateAnalyzerAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return """你是一名资深专利律师和专利审查员。
你的任务是基于前序步骤生成的结果，分析专利申请的授权成功率。
你必须从多个维度评估可专利性，主要包括新颖性、创造性/非显而易见性、工业实用性以及权利要求清楚性。

请以 JSON 格式输出分析，字段如下：
- "novelty_analysis": 基于现有技术的新颖性详细分析。
- "inventiveness_analysis": 创造性/非显而易见性详细分析。
- "success_rate_estimation": 表示整体授权成功可能性的百分比，例如 "75%"。
- "key_risks": 影响可专利性的主要风险列表。
- "improvement_suggestions": 改进申请的建议，例如增加特定取代限定。
- "comprehensive_report": 中文 Markdown 综合报告，必须使用以下两段结构：
  一.最终结论
  二.相关分析及证据：
      分析/证据1，分析/证据2，分析/证据3，分析/证据4（按实际证据数量输出）
  不要保留或复述原始输入全文，只保留结论、必要事实、分析和证据。
"""

    def build_user_prompt(self, **kwargs) -> str:
        proposed_cxsmiles = kwargs.get("proposed_cxsmiles", "N/A")
        tech_domain = kwargs.get("tech_domain", "N/A")
        novelty_data = kwargs.get("novelty_data", {})
        prior_arts = kwargs.get("prior_arts", [])
        
        prior_art_summaries = []
        for pa in prior_arts:
            prior_art_summaries.append(f"- 专利号: {pa.patent_id}, 相关度: {pa.relevance_score}, 重叠描述: {pa.overlap_description}")
            
        return f"""请分析该申请的专利授权成功率。

## 拟申请结构（CXSMILES）
{proposed_cxsmiles}

## 技术领域
{tech_domain}

## 前序步骤的新颖性评估
评分: {novelty_data.get('novelty_score', 'N/A')}
新颖特征: {novelty_data.get('novel_features', [])}
重叠特征: {novelty_data.get('overlapping_features', [])}

## 已识别现有技术
{chr(10).join(prior_art_summaries)}

请基于上述结果，提供多维度可专利性分析。comprehensive_report 必须按“一.最终结论 / 二.相关分析及证据：分析/证据1...”的格式输出。"""

    def parse_response(self, response: dict) -> dict:
        return {
            "novelty_analysis": response.get("novelty_analysis", ""),
            "inventiveness_analysis": response.get("inventiveness_analysis", ""),
            "success_rate_estimation": response.get("success_rate_estimation", ""),
            "key_risks": response.get("key_risks", []),
            "improvement_suggestions": response.get("improvement_suggestions", []),
            "comprehensive_report": response.get("comprehensive_report", "")
        }
