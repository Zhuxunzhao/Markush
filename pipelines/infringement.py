"""专利侵权分析管线

输入: target_smiles + patent_id
输出: InfringementResult

流程:
1. PatentScraper → 获取专利文本 + 图片
2. MarkushGrapher → 图片识别为 CXSMILES (可选)
3. ClaimAnalyzer → 分析权利要求
4. RDKitMatcher → 子结构匹配
5. SubsMatcher → 融合验证
6. RGroupAlignment → 对齐 caption-local 标签与 claim 变量
7. RequirementsExaminer → 判断 is_protected
8. ReportGenerator → 生成报告
"""

from __future__ import annotations
from typing import Any, Optional
import json
import dataclasses
import re

from schemas.types import (
    InfringementResult,
    MatchResult,
    FusedMatchResult,
    RGroupAlignmentResult,
    RequirementsResult,
    Confidence,
    MarkushStructure,
    MatchMethod,
    PatentDocument,
)
from tools.patent_scraper import PatentScraperTool
from tools.markush_grapher import MarkushGrapherTool
from tools.markush_caption import normalize_markush_caption
from tools.rdkit_matcher import RDKitMatcherTool
from tools.llm_client import LLMClient
from tools.logger import log
from agents.claim_analyzer import ClaimAnalyzerAgent, ClaimAnalysis
from agents.subs_matcher import SubsMatcherAgent
from agents.r_group_aligner import RGroupAlignmentAgent
from agents.requirements_examiner import RequirementsExaminerAgent
from agents.report_generator import ReportGeneratorAgent


def _dump(obj) -> str:
    """Pretty-print a dataclass or dict for verbose logging."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(dataclasses.asdict(obj), ensure_ascii=False, indent=2, default=str)
    if isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    return str(obj)


def _canonical_claim_label(label: str) -> str:
    label = str(label or "").strip()
    bracketed = re.fullmatch(r"R\[(\d+)\]", label, flags=re.IGNORECASE)
    if bracketed:
        return f"R{bracketed.group(1)}"
    simple = re.fullmatch(r"R(\d+)", label, flags=re.IGNORECASE)
    if simple:
        return f"R{simple.group(1)}"
    return re.sub(r"\s+", " ", label).upper()


class InfringementPipeline:
    def __init__(self, config: dict):
        self.config = config
        pipe_cfg = config["pipelines"]["infringement"]
        self.min_markush_score = pipe_cfg.get("min_markush_score", 0.5)
        self.markush_empty_retry_max = int(pipe_cfg.get("markush_empty_retry_max", 3))

        # Tools
        self.scraper = PatentScraperTool(config)
        self.markush_grapher = MarkushGrapherTool(config) if pipe_cfg["use_markush_grapher"] else None
        self.rdkit = RDKitMatcherTool() if pipe_cfg["use_rdkit"] else None

        # Agents
        llm = LLMClient(config)
        self.claim_analyzer = ClaimAnalyzerAgent(llm)
        self.subs_matcher = SubsMatcherAgent(llm)
        self.r_group_aligner = RGroupAlignmentAgent(llm)
        self.req_examiner = RequirementsExaminerAgent(llm)
        self.reporter = ReportGeneratorAgent(llm)

    def _claim_constraint_labels(self, claim_analysis: Optional[ClaimAnalysis]) -> set[str]:
        labels: set[str] = set()
        if not claim_analysis:
            return labels
        for claim in claim_analysis.markush_claims or []:
            if not isinstance(claim, dict):
                continue
            constraints = claim.get("r_group_constraints", {})
            if isinstance(constraints, dict):
                labels.update(_canonical_claim_label(label) for label in constraints.keys())
        return labels

    def _can_use_identity_alignment(
        self,
        r_group_matching: dict[str, str],
        claim_analysis: Optional[ClaimAnalysis],
    ) -> bool:
        claim_labels = self._claim_constraint_labels(claim_analysis)
        if not r_group_matching or not claim_labels:
            return False
        return all(_canonical_claim_label(label) in claim_labels for label in r_group_matching)

    def _identity_alignment_result(
        self,
        r_group_matching: dict[str, str],
    ) -> RGroupAlignmentResult:
        return RGroupAlignmentResult(
            aligned_r_group_matching=dict(r_group_matching),
            label_alignment={
                label: {
                    "claim_label": label,
                    "confidence": Confidence.LOW.value,
                    "claim_definition": "",
                    "reason": "caption label 与 claim label 同名/同编号，作为保守 identity fallback 使用。",
                }
                for label in r_group_matching
            },
            reasoning="R-group 语义对齐未产生可用结果，但原始标签均可在 claim constraints 中同名/同编号找到，因此使用保守 identity fallback。",
            confidence=Confidence.LOW,
        )

    def _alignment_covers_source_labels(
        self,
        alignment_result: RGroupAlignmentResult,
        r_group_matching: dict[str, str],
    ) -> bool:
        if not alignment_result.aligned_r_group_matching or alignment_result.unresolved_labels:
            return False
        if alignment_result.label_alignment:
            return all(label in alignment_result.label_alignment for label in r_group_matching)
        return len(alignment_result.aligned_r_group_matching) >= len(r_group_matching)

    def _is_usable_markush(self, structure: MarkushStructure) -> bool:
        if not structure.caption:
            return False
        if normalize_markush_caption(structure.caption):
            return True
        if structure.is_markush:
            return True
        return "<sep>" in structure.caption and structure.score >= self.min_markush_score

    def _select_claim_markush_caption(
        self,
        current_caption: str,
        claim_caption: str,
    ) -> str:
        """Keep a usable image/provided caption from being replaced by LLM text."""
        claim_caption = (claim_caption or "").strip()
        if not claim_caption:
            return current_caption

        current_normalized = normalize_markush_caption(current_caption)
        claim_normalized = normalize_markush_caption(claim_caption)

        if current_normalized:
            if not claim_normalized:
                log.warning(
                    "  Ignoring unsupported primary Markush caption from claim analysis; "
                    "keeping image/provided caption for matching"
                )
            elif claim_normalized != current_normalized:
                log.warning(
                    "  Ignoring claim-analysis Markush caption because it differs from "
                    "the usable image/provided caption"
                )
            return current_caption

        if claim_normalized:
            log.info("  Using supported primary Markush caption from claim analysis")
            return claim_caption

        log.warning("  Ignoring unsupported primary Markush caption from claim analysis")
        return current_caption

    def _no_verified_match_result(
        self,
        patent_id: str,
        target_smiles: str,
        markush: Optional[MarkushStructure],
        fused: FusedMatchResult,
        reason: str,
        llm_outputs: Optional[dict] = None,
    ) -> InfringementResult:
        requirements = RequirementsResult(
            is_protected=False,
            confidence=Confidence.VERY_LOW,
            reasoning=reason,
            r_group_analysis={},
        )
        return InfringementResult(
            patent_id=patent_id,
            target_smiles=target_smiles,
            is_protected=False,
            confidence=Confidence.VERY_LOW,
            markush_structure=markush,
            fused_match=fused,
            requirements=requirements,
            llm_outputs=llm_outputs or {},
            report=reason,
        )

    def _predict_first_image_markush(
        self,
        patent: PatentDocument,
    ) -> Optional[MarkushStructure]:
        if not self.markush_grapher or not patent.images:
            return None

        first_image = patent.images[0]
        if not first_image.path:
            log.warning("  First patent image has no local path")
            return None

        max_attempts = max(1, self.markush_empty_retry_max)
        last_structure: Optional[MarkushStructure] = None
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                self.markush_grapher.clear_cache(first_image.path)
                log.info(
                    f"  Retrying first-image Markush recognition after empty caption "
                    f"({attempt}/{max_attempts})"
                )

            structure = self.markush_grapher.predict(first_image.path)
            last_structure = structure
            if structure.caption:
                first_image.structure = structure
                if self._is_usable_markush(structure):
                    return structure
                log.info(
                    "  First image produced a non-empty but unusable caption "
                    f"(score={structure.score:.2f}, image={first_image.path})"
                )
                return structure

        log.warning(
            f"  First image produced empty caption after {max_attempts} attempt(s)"
        )
        return last_structure

    def run(
        self,
        patent_id: str,
        target_smiles: str,
        markush_caption: Optional[str] = None,
        markush_structure: Optional[MarkushStructure] = None,
    ) -> InfringementResult:
        """执行完整的侵权分析管线

        Args:
            patent_id: 专利号
            target_smiles: 目标分子 SMILES
            markush_caption: 可选，直接提供 Markush caption 跳过图片识别

        Returns:
            InfringementResult
        """
        log.set_total_steps(8)
        llm_outputs: dict[str, Any] = {}

        # Step 1: 获取专利
        log.step(f"Fetching patent {patent_id}")
        try:
            patent = self.scraper.fetch(patent_id)
        except Exception as e:
            log.error(f"Failed to fetch patent: {e}")
            return InfringementResult(
                patent_id=patent_id,
                target_smiles=target_smiles,
                is_protected=False,
                confidence=Confidence.VERY_LOW,
                llm_outputs=llm_outputs,
                report=f"Error: Failed to fetch patent {patent_id}: {e}",
            )

        log.info(f"  >> claims_text length: {len(patent.claims_text)} chars")
        log.info(f"  >> images found: {len(patent.images)}")
        log.info(f"  >> claims_text (first 800 chars):\n{patent.claims_text[:800]}")

        # Step 2: 识别 Markush 结构（如果未直接提供）
        markush: Optional[MarkushStructure] = None
        if markush_structure:
            log.step("Using provided Markush structure")
            markush = markush_structure
            markush_caption = markush_structure.caption
        elif markush_caption:
            log.step("Using provided Markush caption")
            markush = MarkushStructure(
                cxsmiles="", caption=markush_caption, substituent_table={}
            )
        elif self.markush_grapher and patent.images:
            log.step("Recognizing Markush structure from first image")
            try:
                markush = self._predict_first_image_markush(patent)
                if markush and markush.caption:
                    markush_caption = markush.caption
            except Exception as e:
                log.warning(f"  Markush recognition failed: {e}")
        else:
            log.step("Skipping Markush recognition (not configured or no images)")

        log.info(f"  >> markush_caption: {markush_caption}")

        if not markush_caption:
            log.warning("No Markush structure found — cannot perform infringement analysis")
            return InfringementResult(
                patent_id=patent_id,
                target_smiles=target_smiles,
                is_protected=False,
                confidence=Confidence.VERY_LOW,
                llm_outputs=llm_outputs,
                report="No Markush structure found in patent. Cannot perform infringement analysis.",
            )

        # Step 3: 分析权利要求
        log.step("Analyzing patent claims")
        claim_analysis: Optional[ClaimAnalysis] = None
        try:
            claim_analysis = self.claim_analyzer.run(
                claims_text=patent.claims_text,
                markush_captions=[markush_caption],
            )
            llm_outputs["claim_analysis"] = self.claim_analyzer.last_llm_response
            # Keep image/provided captions as structural ground truth for matching.
            if claim_analysis.primary_markush_caption:
                markush_caption = self._select_claim_markush_caption(
                    markush_caption,
                    claim_analysis.primary_markush_caption,
                )
            log.info(f"  >> ClaimAnalysis:\n{_dump(claim_analysis)}")
        except Exception as e:
            llm_outputs["claim_analysis"] = {"error": str(e)}
            log.warning(f"  Claim analysis failed: {e}, continuing with original caption")

        normalized_markush_caption = normalize_markush_caption(markush_caption)
        if normalized_markush_caption and normalized_markush_caption != markush_caption:
            log.info(f"  >> normalized_markush_caption: {normalized_markush_caption}")

        # Step 4: 子结构匹配
        log.step("Running substructure matching")
        rdkit_result: Optional[MatchResult] = None

        if self.rdkit:
            try:
                rdkit_result = self.rdkit.match(markush_caption, target_smiles)
                log.info(f"  RDKit: match={rdkit_result.is_match}")
                log.info(f"  >> RDKit MatchResult:\n{_dump(rdkit_result)}")
            except Exception as e:
                log.warning(f"  RDKit matcher raised an error: {e}")
                rdkit_result = MatchResult(
                    is_match=None,
                    r_group_map=None,
                    method=MatchMethod.RDKIT,
                    reasoning=f"Error: {e}",
                )

        # Step 5: 融合验证
        log.step("Fusing and verifying matches")
        try:
            fused: FusedMatchResult = self.subs_matcher.run(
                markush_caption=normalized_markush_caption or markush_caption,
                target_smiles=target_smiles,
                rdkit_result=rdkit_result,
            )
            llm_outputs["match_fusion"] = self.subs_matcher.last_llm_response
            fused.rdkit_result = rdkit_result
            if (
                not fused.r_group_matching
                and rdkit_result
                and rdkit_result.is_match is True
                and rdkit_result.r_group_map
            ):
                fused.r_group_matching = rdkit_result.r_group_map
                log.info("  Using RDKit R-group map as fused mapping fallback")
            log.info(f"  >> FusedMatchResult:\n{_dump(fused)}")
        except Exception as e:
            log.error(f"  Match fusion failed: {e}")
            return InfringementResult(
                patent_id=patent_id,
                target_smiles=target_smiles,
                is_protected=False,
                confidence=Confidence.VERY_LOW,
                markush_structure=markush,
                llm_outputs=llm_outputs,
                report=f"Error during match fusion: {e}",
            )

        if not fused.r_group_matching:
            if not rdkit_result or rdkit_result.is_match is not True:
                reason = (
                    "No verified skeleton/R-group match was produced. "
                    "Skipping claim requirement examination to avoid a high-confidence "
                    "conclusion from an empty or invalid R-group mapping."
                )
                log.warning(f"  {reason}")
                return self._no_verified_match_result(
                    patent_id=patent_id,
                    target_smiles=target_smiles,
                    markush=markush,
                    fused=fused,
                    reason=reason,
                    llm_outputs=llm_outputs,
                )

        # Step 6: R 基团标签语义对齐
        log.step("Aligning R-group labels with claim variables")
        alignment_result: Optional[RGroupAlignmentResult] = None
        effective_r_group_matching = fused.r_group_matching
        try:
            alignment_result = self.r_group_aligner.run(
                markush_caption=normalized_markush_caption or markush_caption,
                target_smiles=target_smiles,
                r_group_matching=fused.r_group_matching,
                claim_analysis=claim_analysis,
                claim_text=patent.claims_text,
            )
            llm_outputs["r_group_alignment"] = self.r_group_aligner.last_llm_response
            llm_outputs["r_group_alignment_parsed"] = dataclasses.asdict(alignment_result)
            log.info(f"  >> RGroupAlignmentResult:\n{_dump(alignment_result)}")
        except Exception as e:
            llm_outputs["r_group_alignment"] = {"error": str(e)}
            alignment_result = RGroupAlignmentResult(
                reasoning=f"R-group label alignment failed: {e}",
                confidence=Confidence.VERY_LOW,
            )
            log.warning(f"  R-group label alignment failed: {e}")

        if self._alignment_covers_source_labels(alignment_result, fused.r_group_matching):
            effective_r_group_matching = alignment_result.aligned_r_group_matching
        elif self._can_use_identity_alignment(fused.r_group_matching, claim_analysis):
            alignment_result = self._identity_alignment_result(fused.r_group_matching)
            effective_r_group_matching = alignment_result.aligned_r_group_matching
            llm_outputs["r_group_alignment_fallback"] = dataclasses.asdict(alignment_result)
            log.warning("  Using conservative identity R-group label alignment fallback")
        else:
            reason = (
                "R-group label alignment failed. The original caption-local labels "
                "cannot be safely used as claim labels, so claim requirement examination "
                "was skipped to avoid a high-confidence conclusion from misaligned "
                "R-group constraints."
            )
            log.warning(f"  {reason}")
            return self._no_verified_match_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                markush=markush,
                fused=fused,
                reason=reason,
                llm_outputs=llm_outputs,
            )

        fused.claim_aligned_r_group_matching = effective_r_group_matching
        fused.label_alignment = alignment_result.label_alignment

        # Step 7: R 基团约束检查
        log.step("Examining requirements")
        try:
            req_result: RequirementsResult = self.req_examiner.run(
                markush_caption=normalized_markush_caption or markush_caption,
                target_smiles=target_smiles,
                r_group_matching=effective_r_group_matching,
                original_r_group_matching=fused.r_group_matching,
                label_alignment=alignment_result.label_alignment,
                claim_text=patent.claims_text,
            )
            llm_outputs["requirements_examination"] = self.req_examiner.last_llm_response
            log.info(f"  >> RequirementsResult:\n{_dump(req_result)}")
        except Exception as e:
            log.error(f"  Requirements examination failed: {e}")
            return InfringementResult(
                patent_id=patent_id,
                target_smiles=target_smiles,
                is_protected=False,
                confidence=Confidence.VERY_LOW,
                markush_structure=markush,
                fused_match=fused,
                llm_outputs=llm_outputs,
                report=f"Error during requirements examination: {e}",
            )

        # Step 8: 生成报告
        log.step("Generating report")
        try:
            report_data = {
                "patent_id": patent_id,
                "target_smiles": target_smiles,
                "markush_caption": markush_caption,
                "fused_match": fused.r_group_matching,
                "claim_aligned_r_group_matching": effective_r_group_matching,
                "label_alignment": alignment_result.label_alignment,
                "is_protected": req_result.is_protected,
                "requirements_reasoning": req_result.reasoning,
                "r_group_analysis": req_result.r_group_analysis,
            }
            report = self.reporter.run(
                report_type="infringement",
                analysis_data=report_data,
            )
            llm_outputs["infringement_report"] = self.reporter.last_llm_response
            log.info(f"  >> Report:\n{_dump(report)}")
        except Exception as e:
            llm_outputs["infringement_report"] = {"error": str(e)}
            log.warning(f"  Report generation failed: {e}, using fallback")
            report = {
                "confidence": "moderate",
                "detailed_analysis": f"Analysis completed but report generation failed: {e}",
            }

        return InfringementResult(
            patent_id=patent_id,
            target_smiles=target_smiles,
            is_protected=req_result.is_protected,
            confidence=req_result.confidence,
            markush_structure=markush,
            fused_match=fused,
            requirements=req_result,
            llm_outputs=llm_outputs,
            report=report.get("detailed_analysis", ""),
        )
