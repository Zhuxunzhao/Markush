"""LLM-only patent infringement workflow.

This pipeline mirrors ``pipelines.infringement`` but replaces the two
environment-heavy tool steps:

1. MarkushGrapher image recognition -> ``LLMMarkushExtractorAgent``
2. RDKit R-group decomposition -> ``LLMSubstructureMatcherAgent``

The later legal/semantic checks are intentionally reused so outputs stay close
to the original infringement pipeline.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from typing import Any, Optional

from agents.claim_analyzer import ClaimAnalyzerAgent, ClaimAnalysis
from agents.llm_markush_extractor import LLMMarkushExtractorAgent
from agents.llm_substructure_matcher import LLMSubstructureMatcherAgent
from agents.markush_image_selector import MarkushImageSelection, MarkushImageSelectorAgent
from agents.r_group_aligner import RGroupAlignmentAgent
from agents.report_generator import ReportGeneratorAgent
from agents.requirements_examiner import RequirementsExaminerAgent
from agents.subs_matcher import SubsMatcherAgent
from schemas.types import (
    Confidence,
    FusedMatchResult,
    InfringementResult,
    MarkushStructure,
    MatchResult,
    PatentDocument,
    RequirementsResult,
    RGroupAlignmentResult,
)
from tools.llm_client import LLMClient
from tools.logger import log
from tools.patent_scraper import PatentScraperTool


def _dump(obj: Any) -> str:
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


def _model_candidates(model_or_profile: str) -> list[str]:
    raw = str(model_or_profile or "").strip()
    lowered = raw.lower().replace("_", "-")
    candidates = [raw, lowered]
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        candidates.extend(["glm5.1", "glm-5.1"])
    if lowered in {"qwen-max", "qwenmax"}:
        candidates.extend(["qwen-max", "qwen_max"])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _canonical_model_name(model_or_profile: str) -> str:
    lowered = str(model_or_profile or "").strip().lower().replace("_", "-")
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        return "glm-5.1"
    if lowered in {"qwenmax", "qwen-max"}:
        return "qwen-max"
    return str(model_or_profile).strip()


def _config_with_llm_overrides(
    config: dict,
    *,
    llm_model: Optional[str],
    llm_base_url: Optional[str],
    llm_api_key_env: Optional[str],
) -> dict:
    resolved = copy.deepcopy(config)
    pipe_cfg = resolved.get("pipelines", {}).get("llm_infringement", {})
    model_or_profile = llm_model or pipe_cfg.get("llm_model")
    resolved.setdefault("llm", {})

    if model_or_profile:
        profiles = resolved.get("llm_profiles", {})
        profile = None
        for candidate in _model_candidates(model_or_profile):
            if candidate in profiles:
                profile = profiles[candidate]
                break
        if profile:
            resolved["llm"] = {**resolved["llm"], **profile}
        else:
            resolved["llm"]["model"] = _canonical_model_name(model_or_profile)

    if llm_base_url:
        resolved["llm"]["base_url"] = llm_base_url
    if llm_api_key_env:
        resolved["llm"]["api_key_env"] = llm_api_key_env
    return resolved


class LLMInfringementPipeline:
    def __init__(
        self,
        config: dict,
        *,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_api_key_env: Optional[str] = None,
        generate_report: Optional[bool] = None,
    ):
        self.config = _config_with_llm_overrides(
            config,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key_env=llm_api_key_env,
        )
        pipe_cfg = self.config.get("pipelines", {}).get("llm_infringement", {})
        selection_cfg = self.config.get("pipelines", {}).get("markush_image_selection", {})
        self.image_selection_enabled = bool(selection_cfg.get("enabled", True))
        self.image_selection_max_images = int(selection_cfg.get("max_images", 60))
        self.image_selection_min_score = float(selection_cfg.get("min_score", 0.55))
        self.image_selection_allow_fallback = bool(
            selection_cfg.get("allow_candidate_fallback", True)
        )
        self.fallback_to_text_on_image_error = bool(
            pipe_cfg.get("fallback_to_text_on_image_error", True)
        )
        self.generate_report = (
            bool(pipe_cfg.get("generate_report", True))
            if generate_report is None
            else bool(generate_report)
        )

        self.scraper = PatentScraperTool(self.config)
        llm = LLMClient(self.config)
        self.image_selector = MarkushImageSelectorAgent(llm)
        self.markush_extractor = LLMMarkushExtractorAgent(
            llm,
            max_tokens=pipe_cfg.get("markush_extraction_max_tokens"),
        )
        self.claim_analyzer = ClaimAnalyzerAgent(llm)
        self.structure_matcher = LLMSubstructureMatcherAgent(
            llm,
            max_tokens=pipe_cfg.get("structure_match_max_tokens"),
        )
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
                    "reason": "LLM-only 流程中 caption label 与 claim label 同名/同编号，作为保守 identity fallback 使用。",
                }
                for label in r_group_matching
            },
            reasoning="R-group 语义对齐未产生可用结果，但原始标签均可在 claim constraints 中同名/同编号找到，因此使用保守 identity fallback。",
            confidence=Confidence.LOW,
        )

    @staticmethod
    def _alignment_covers_source_labels(
        alignment_result: Optional[RGroupAlignmentResult],
        r_group_matching: dict[str, str],
    ) -> bool:
        if alignment_result is None:
            return False
        if not alignment_result.aligned_r_group_matching or alignment_result.unresolved_labels:
            return False
        if alignment_result.label_alignment:
            return all(label in alignment_result.label_alignment for label in r_group_matching)
        return len(alignment_result.aligned_r_group_matching) >= len(r_group_matching)

    @staticmethod
    def _selection_summary(selection: MarkushImageSelection) -> dict[str, Any]:
        return {
            "image_index": selection.image_index,
            "image_path": selection.image_path,
            "is_markush": selection.is_markush,
            "is_main_markush": selection.is_main_markush,
            "score": selection.score,
            "image_role": selection.image_role,
            "reasoning": selection.reasoning,
        }

    def _select_main_markush_image(
        self,
        *,
        patent: PatentDocument,
        target_smiles: str,
        llm_outputs: dict[str, Any],
    ) -> Optional[str]:
        if not self.image_selection_enabled or not patent.images:
            return None
        try:
            selection, evaluations = self.image_selector.select_main_markush_image(
                patent=patent,
                target_smiles=target_smiles,
                purpose="llm_infringement",
                max_images=self.image_selection_max_images,
                min_score=self.image_selection_min_score,
                allow_candidate_fallback=self.image_selection_allow_fallback,
            )
        except Exception as e:
            llm_outputs["markush_image_selection"] = {"error": str(e)}
            log.warning(f"  LLM Markush image selection failed: {e}")
            return None

        llm_outputs["markush_image_selection"] = {
            "selected": self._selection_summary(selection) if selection else None,
            "evaluations": [self._selection_summary(item) for item in evaluations],
        }
        if selection is None:
            log.warning("  LLM did not select a qualifying main Markush image")
            return None

        log.info(
            "  LLM selected main Markush image "
            f"#{selection.image_index} score={selection.score:.2f} "
            f"role={selection.image_role}: {selection.image_path}"
        )
        return selection.image_path

    @staticmethod
    def _select_claim_markush_caption(current_caption: str, claim_caption: str) -> str:
        current_caption = (current_caption or "").strip()
        claim_caption = (claim_caption or "").strip()
        if current_caption:
            if claim_caption and claim_caption != current_caption:
                log.warning(
                    "  Keeping LLM-extracted/provided Markush caption as structural evidence; "
                    "claim-analysis caption is recorded only in llm_outputs"
                )
            return current_caption
        if claim_caption:
            log.info("  Using primary Markush caption from claim analysis")
        return claim_caption

    @staticmethod
    def _no_verified_match_result(
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

    def _extract_markush_with_llm(
        self,
        patent: PatentDocument,
        target_smiles: str,
        image_path: Optional[str],
        llm_outputs: dict[str, Any],
    ) -> Optional[MarkushStructure]:
        try:
            structure = self.markush_extractor.run(
                patent=patent,
                target_smiles=target_smiles,
                image_path=image_path,
            )
            llm_outputs["llm_markush_extraction"] = (
                self.markush_extractor.last_llm_response
            )
            return structure
        except Exception as e:
            llm_outputs["llm_markush_extraction"] = {
                "error": str(e),
                "image_path": image_path,
            }
            if image_path and self.fallback_to_text_on_image_error:
                log.warning(
                    f"  LLM image Markush extraction failed: {e}; retrying text-only"
                )
                try:
                    structure = self.markush_extractor.run(
                        patent=patent,
                        target_smiles=target_smiles,
                        image_path=None,
                    )
                    llm_outputs["llm_markush_extraction_text_fallback"] = (
                        self.markush_extractor.last_llm_response
                    )
                    return structure
                except Exception as fallback_error:
                    llm_outputs["llm_markush_extraction_text_fallback"] = {
                        "error": str(fallback_error)
                    }
            else:
                log.warning(f"  LLM Markush extraction failed: {e}")
        return None

    def run(
        self,
        patent_id: str,
        target_smiles: str,
        markush_caption: Optional[str] = None,
        markush_structure: Optional[MarkushStructure] = None,
    ) -> InfringementResult:
        log.set_total_steps(8 if self.generate_report else 7)
        llm_outputs: dict[str, Any] = {
            "llm_only_workflow": True,
            "llm_model": self.config.get("llm", {}).get("model"),
        }

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

        log.step("Extracting Markush structure with LLM")
        markush: Optional[MarkushStructure] = None
        if markush_structure:
            markush = markush_structure
            markush_caption = markush_structure.caption
        elif markush_caption:
            markush = MarkushStructure(
                cxsmiles="",
                substituent_table={},
                caption=markush_caption,
                is_markush=True,
            )
        else:
            image_path = self._select_main_markush_image(
                patent=patent,
                target_smiles=target_smiles,
                llm_outputs=llm_outputs,
            )
            markush = self._extract_markush_with_llm(
                patent,
                target_smiles,
                image_path,
                llm_outputs,
            )
            if markush and markush.caption:
                markush_caption = markush.caption

        log.info(f"  >> markush_caption: {markush_caption}")
        if not markush_caption:
            reason = (
                "No Markush structure was extracted by the LLM workflow. "
                "Cannot perform infringement analysis."
            )
            log.warning(reason)
            return InfringementResult(
                patent_id=patent_id,
                target_smiles=target_smiles,
                is_protected=False,
                confidence=Confidence.VERY_LOW,
                markush_structure=markush,
                llm_outputs=llm_outputs,
                report=reason,
            )

        log.step("Analyzing patent claims")
        claim_analysis: Optional[ClaimAnalysis] = None
        try:
            claim_analysis = self.claim_analyzer.run(
                claims_text=patent.claims_text,
                markush_captions=[markush_caption],
            )
            llm_outputs["claim_analysis"] = self.claim_analyzer.last_llm_response
            if claim_analysis.primary_markush_caption:
                markush_caption = self._select_claim_markush_caption(
                    markush_caption,
                    claim_analysis.primary_markush_caption,
                )
            log.info(f"  >> ClaimAnalysis:\n{_dump(claim_analysis)}")
        except Exception as e:
            llm_outputs["claim_analysis"] = {"error": str(e)}
            log.warning(f"  Claim analysis failed: {e}, continuing with LLM Markush caption")

        log.step("Running LLM substructure matching")
        llm_match_result: Optional[MatchResult] = None
        try:
            llm_match_result = self.structure_matcher.run(
                markush_caption=markush_caption,
                markush_structure=markush,
                target_smiles=target_smiles,
                claim_analysis=claim_analysis,
                claim_text=patent.claims_text,
            )
            llm_outputs["llm_structure_matching"] = (
                self.structure_matcher.last_llm_response
            )
            log.info(f"  >> LLM MatchResult:\n{_dump(llm_match_result)}")
        except Exception as e:
            llm_outputs["llm_structure_matching"] = {"error": str(e)}
            log.warning(f"  LLM substructure matching failed: {e}")

        log.step("Fusing and verifying matches")
        try:
            fused: FusedMatchResult = self.subs_matcher.run(
                markush_caption=markush_caption,
                target_smiles=target_smiles,
                llm_match_result=llm_match_result,
            )
            llm_outputs["match_fusion"] = self.subs_matcher.last_llm_response
            fused.llm_result = llm_match_result
            if (
                not fused.r_group_matching
                and llm_match_result
                and llm_match_result.is_match is True
                and llm_match_result.r_group_map
            ):
                fused.r_group_matching = llm_match_result.r_group_map
                log.info("  Using LLM R-group map as fused mapping fallback")
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
            reason = (
                "No verified skeleton/R-group match was produced by the LLM-only "
                "workflow. Skipping claim requirement examination to avoid a "
                "high-confidence conclusion from an empty or invalid mapping."
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

        log.step("Aligning R-group labels with claim variables")
        alignment_result: Optional[RGroupAlignmentResult] = None
        effective_r_group_matching = fused.r_group_matching
        try:
            alignment_result = self.r_group_aligner.run(
                markush_caption=markush_caption,
                target_smiles=target_smiles,
                r_group_matching=fused.r_group_matching,
                claim_analysis=claim_analysis,
                claim_text=patent.claims_text,
            )
            llm_outputs["r_group_alignment"] = self.r_group_aligner.last_llm_response
            llm_outputs["r_group_alignment_parsed"] = dataclasses.asdict(
                alignment_result
            )
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
            llm_outputs["r_group_alignment_fallback"] = dataclasses.asdict(
                alignment_result
            )
            log.warning("  Using conservative identity R-group label alignment fallback")
        else:
            reason = (
                "R-group label alignment failed. The LLM-produced labels cannot "
                "be safely used as claim labels, so claim requirement examination "
                "was skipped."
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

        log.step("Examining requirements")
        try:
            req_result: RequirementsResult = self.req_examiner.run(
                markush_caption=markush_caption,
                target_smiles=target_smiles,
                r_group_matching=effective_r_group_matching,
                original_r_group_matching=fused.r_group_matching,
                label_alignment=alignment_result.label_alignment,
                claim_text=patent.claims_text,
            )
            llm_outputs["requirements_examination"] = (
                self.req_examiner.last_llm_response
            )
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

        if self.generate_report:
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
                    "structure_match_method": "llm",
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
                    "confidence": req_result.confidence.value,
                    "detailed_analysis": f"Analysis completed but report generation failed: {e}",
                }
        else:
            llm_outputs["infringement_report"] = {"skipped": True}
            report = {
                "confidence": req_result.confidence.value,
                "detailed_analysis": req_result.reasoning,
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
