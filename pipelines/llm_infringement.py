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
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

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
from tools.llm_config import build_llm_config
from tools.logger import log
from tools.patent_scraper import PatentScraperTool


def _dump(obj: Any) -> str:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(dataclasses.asdict(obj), ensure_ascii=False, indent=2, default=str)
    if isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    return str(obj)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


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
    if lowered in {
        "3.6plus",
        "3.6-plus",
        "qwen3.6plus",
        "qwen3.6-plus",
        "qwen-3.6plus",
        "qwen-3.6-plus",
    }:
        candidates.extend(
            ["qwen3.6-plus", "qwen-3.6plus", "qwen3.6plus", "qwen-3.6-plus"]
        )
    if lowered in {"qwen-max", "qwenmax"}:
        candidates.extend(["qwen-max", "qwen_max"])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _canonical_model_name(model_or_profile: str) -> str:
    lowered = str(model_or_profile or "").strip().lower().replace("_", "-")
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        return "glm-5.1"
    if lowered in {
        "3.6plus",
        "3.6-plus",
        "qwen3.6plus",
        "qwen3.6-plus",
        "qwen-3.6plus",
        "qwen-3.6-plus",
    }:
        return "qwen3.6-plus"
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
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_api_key_env: Optional[str] = None,
        llm_request_timeout: Optional[float] = None,
        llm_max_tokens: Optional[int] = None,
        llm_temperature: Optional[float] = None,
        llm_token_limit_param: Optional[str] = None,
        llm_omit_temperature: Optional[bool] = None,
        llm_reasoning_effort: Optional[str] = None,
        llm_verbosity: Optional[str] = None,
        generate_report: Optional[bool] = None,
        step_output_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.config = build_llm_config(
            config,
            pipeline_key="llm_infringement",
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_api_key_env=llm_api_key_env,
            llm_request_timeout=llm_request_timeout,
            llm_max_tokens=llm_max_tokens,
            llm_temperature=llm_temperature,
            llm_token_limit_param=llm_token_limit_param,
            llm_omit_temperature=llm_omit_temperature,
            llm_reasoning_effort=llm_reasoning_effort,
            llm_verbosity=llm_verbosity,
        )
        self.step_outputs: list[dict[str, Any]] = []
        self._step_output_callback = step_output_callback
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
        self.use_image_for_markush_extraction = bool(
            pipe_cfg.get("use_image_for_markush_extraction", True)
        )
        self.use_first_image_when_selection_disabled = bool(
            pipe_cfg.get("use_first_image_when_selection_disabled", True)
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

    def _record_step_output(
        self,
        *,
        step: int,
        agent_key: str,
        title: str,
        summary: str,
        data: Any,
    ) -> None:
        output = {
            "step": step,
            "agent_key": agent_key,
            "title": title,
            "summary": summary,
            "data": _jsonable(data),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.step_outputs.append(output)
        if self._step_output_callback:
            self._step_output_callback(output)

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
            if (
                self.use_first_image_when_selection_disabled
                and self.use_image_for_markush_extraction
                and patent.images
                and patent.images[0].path
            ):
                image = patent.images[0]
                llm_outputs["markush_image_selection"] = {
                    "selected": {
                        "image_index": 1,
                        "image_path": image.path,
                        "is_markush": None,
                        "is_main_markush": None,
                        "score": None,
                        "image_role": "first_image_fallback",
                        "reasoning": (
                            "Image selection is disabled; using the first cached patent "
                            "image as visual evidence for LLM Markush extraction."
                        ),
                    },
                    "evaluations": [],
                    "mode": "first_image_fallback",
                }
                log.info(
                    "  Image selection disabled; using first patent image as Markush "
                    f"extraction evidence: {image.path}"
                )
                return image.path
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
    def _non_conclusive_result(
        patent_id: str,
        target_smiles: str,
        reason: str,
        *,
        status: str,
        markush: Optional[MarkushStructure] = None,
        fused: Optional[FusedMatchResult] = None,
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
            analysis_status=status,
            is_conclusive=False,
            failure_reason=reason,
        )

    @staticmethod
    def _no_verified_match_result(
        patent_id: str,
        target_smiles: str,
        markush: Optional[MarkushStructure],
        fused: FusedMatchResult,
        reason: str,
        llm_outputs: Optional[dict] = None,
    ) -> InfringementResult:
        return LLMInfringementPipeline._non_conclusive_result(
            patent_id=patent_id,
            target_smiles=target_smiles,
            markush=markush,
            fused=fused,
            reason=reason,
            status="undetermined",
            llm_outputs=llm_outputs,
        )

    @staticmethod
    def _not_protected_no_match_result(
        patent_id: str,
        target_smiles: str,
        markush: Optional[MarkushStructure],
        fused: FusedMatchResult,
        reason: str,
        llm_outputs: Optional[dict] = None,
    ) -> InfringementResult:
        confidence = Confidence.HIGH if "confidence=high" in reason.lower() else Confidence.LOW
        requirements = RequirementsResult(
            is_protected=False,
            confidence=confidence,
            reasoning=reason,
            r_group_analysis={},
        )
        return InfringementResult(
            patent_id=patent_id,
            target_smiles=target_smiles,
            is_protected=False,
            confidence=confidence,
            markush_structure=markush,
            fused_match=fused,
            requirements=requirements,
            llm_outputs=llm_outputs or {},
            report=reason,
            analysis_status="not_protected",
            is_conclusive=True,
        )

    def _extract_markush_with_llm(
        self,
        patent: PatentDocument,
        target_smiles: str,
        image_path: Optional[str],
        llm_outputs: dict[str, Any],
    ) -> Optional[MarkushStructure]:
        try:
            extraction_image_path = image_path if self.use_image_for_markush_extraction else None
            if image_path and not extraction_image_path:
                log.info(
                    "  Selected image is recorded as evidence, but Markush extraction "
                    "is running text-only per config"
                )
            elif extraction_image_path:
                log.info(f"  Passing selected image to Markush extractor: {image_path}")
            else:
                log.info("  Running Markush extractor without an image")
            structure = self.markush_extractor.run(
                patent=patent,
                target_smiles=target_smiles,
                image_path=extraction_image_path,
            )
            llm_outputs["llm_markush_extraction"] = (
                self.markush_extractor.last_llm_response
            )
            log.info(
                "  Markush extractor returned "
                f"is_markush={structure.is_markush} "
                f"score={getattr(structure, 'score', 0.0):.2f} "
                f"caption_len={len(structure.caption or '')}"
            )
            return structure
        except Exception as e:
            llm_outputs["llm_markush_extraction"] = {
                "error": str(e),
                "image_path": image_path,
                "use_image_for_markush_extraction": self.use_image_for_markush_extraction,
            }
            if image_path and self.use_image_for_markush_extraction and self.fallback_to_text_on_image_error:
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
            self._record_step_output(
                step=1,
                agent_key="fetch",
                title="专利抓取摘要",
                summary=f"抓取专利 {patent_id} 失败。",
                data={"patent_id": patent_id, "error": str(e)},
            )
            return self._non_conclusive_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                reason=f"Error: Failed to fetch patent {patent_id}: {e}",
                status="failed",
                llm_outputs=llm_outputs,
            )
        log.info(f"  >> claims_text length: {len(patent.claims_text)} chars")
        log.info(f"  >> images found: {len(patent.images)}")
        log.info(f"  >> claims_text (first 800 chars):\n{patent.claims_text[:800]}")
        self._record_step_output(
            step=1,
            agent_key="fetch",
            title="专利抓取摘要",
            summary=(
                f"已获取 {patent.patent_id}，权利要求 {len(patent.claims_text)} 字符，"
                f"附图 {len(patent.images)} 张。"
            ),
            data={
                "patent_id": patent.patent_id,
                "claims_text_length": len(patent.claims_text),
                "description_text_length": len(patent.description_text),
                "abstract_text_length": len(patent.abstract_text),
                "image_count": len(patent.images),
                "claims_preview": patent.claims_text[:1200],
            },
        )

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
        self._record_step_output(
            step=2,
            agent_key="markush",
            title="Markush 结构解析",
            summary=(
                "已得到可用于后续匹配的 Markush 描述。"
                if markush_caption
                else "未能从 LLM-only 流程中得到 Markush 描述。"
            ),
            data={
                "provided_caption": bool(markush_structure or markush_caption),
                "markush_caption": markush_caption,
                "markush_structure": markush,
                "llm_response": llm_outputs.get("llm_markush_extraction"),
                "image_selection": llm_outputs.get("markush_image_selection"),
            },
        )
        if not markush_caption:
            reason = (
                "No Markush structure was extracted by the LLM workflow. "
                "Cannot perform infringement analysis."
            )
            extraction_error = (
                llm_outputs.get("llm_markush_extraction", {}).get("error")
                if isinstance(llm_outputs.get("llm_markush_extraction"), dict)
                else None
            )
            if extraction_error:
                reason = f"{reason} Extraction error: {extraction_error}"
            log.warning(reason)
            return self._non_conclusive_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                reason=reason,
                status="failed" if extraction_error else "undetermined",
                markush=markush,
                llm_outputs=llm_outputs,
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
        self._record_step_output(
            step=3,
            agent_key="claim",
            title="权利要求解析",
            summary=(
                f"识别到 {len(claim_analysis.markush_claims or [])} 条 Markush 相关权利要求。"
                if claim_analysis
                else "权利要求解析失败或未返回结构化结果。"
            ),
            data={
                "claim_analysis": claim_analysis,
                "llm_response": llm_outputs.get("claim_analysis"),
                "effective_markush_caption": markush_caption,
            },
        )

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
            self._record_step_output(
                step=4,
                agent_key="llm_match",
                title="LLM 结构匹配",
                summary="LLM 结构匹配失败，停止后续保护范围判断。",
                data={
                    "error": str(e),
                    "llm_response": llm_outputs.get("llm_structure_matching"),
                },
            )
            return self._non_conclusive_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                reason=f"Error during LLM substructure matching: {e}",
                status="failed",
                markush=markush,
                llm_outputs=llm_outputs,
            )
        self._record_step_output(
            step=4,
            agent_key="llm_match",
            title="LLM 结构匹配",
            summary=(
                f"LLM 判断骨架匹配结果为 {llm_match_result.is_match}。"
                if llm_match_result
                else "LLM 结构匹配未返回可用结果。"
            ),
            data={
                "match_result": llm_match_result,
                "llm_response": llm_outputs.get("llm_structure_matching"),
            },
        )

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
            self._record_step_output(
                step=5,
                agent_key="fusion",
                title="匹配融合",
                summary="LLM 匹配融合失败。",
                data={
                    "error": str(e),
                    "llm_match_result": llm_match_result,
                    "llm_response": llm_outputs.get("match_fusion"),
                },
            )
            return self._non_conclusive_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                reason=f"Error during match fusion: {e}",
                status="failed",
                markush=markush,
                llm_outputs=llm_outputs,
            )
        self._record_step_output(
            step=5,
            agent_key="fusion",
            title="匹配融合",
            summary=(
                f"得到 {len(fused.r_group_matching or {})} 个 R-group 映射。"
                if fused.r_group_matching
                else "未得到可验证的 R-group 映射。"
            ),
            data={
                "fused_match": fused,
                "llm_response": llm_outputs.get("match_fusion"),
            },
        )

        if not fused.r_group_matching:
            if llm_match_result and llm_match_result.is_match is False:
                reason = (
                    "The target molecule does not match the Markush skeleton, so it "
                    "does not fall within the claim scope. "
                    f"{llm_match_result.reasoning}"
                )
                log.info(f"  {reason}")
                self._record_step_output(
                    step=6,
                    agent_key="alignment",
                    title="R-group label alignment",
                    summary="No verified R-group mapping was produced, so label alignment was skipped.",
                    data={
                        "skipped": True,
                        "reason": "Skeleton mismatch; there is no R-group mapping to align.",
                        "original_r_group_matching": fused.r_group_matching,
                    },
                )
                self._record_step_output(
                    step=7,
                    agent_key="requirements",
                    title="保护范围判断",
                    summary="目标分子骨架不匹配，判断为未落入保护范围。",
                    data={
                        "requirements": {
                            "is_protected": False,
                            "confidence": "high"
                            if "confidence=high" in reason.lower()
                            else "low",
                            "reasoning": reason,
                            "r_group_analysis": {},
                        },
                        "llm_response": llm_outputs.get("llm_structure_matching"),
                    },
                )
                self._record_step_output(
                    step=8,
                    agent_key="report",
                    title="Infringement report",
                    summary=(
                        "Skeleton mismatch produced a conclusive non-infringement "
                        "result; the matching rationale was used as the report."
                    ),
                    data={
                        "report": {
                            "confidence": "high"
                            if "confidence=high" in reason.lower()
                            else "low",
                            "detailed_analysis": reason,
                        },
                        "source": "early_no_match_result",
                    },
                )
                return self._not_protected_no_match_result(
                    patent_id=patent_id,
                    target_smiles=target_smiles,
                    markush=markush,
                    fused=fused,
                    reason=reason,
                    llm_outputs=llm_outputs,
                )
            reason = (
                "No verified skeleton/R-group match was produced by the LLM-only "
                "workflow. Skipping claim requirement examination to avoid a "
                "high-confidence conclusion from an empty or invalid mapping."
            )
            log.warning(f"  {reason}")
            self._record_step_output(
                step=6,
                agent_key="alignment",
                title="R-group label alignment",
                summary="No verified R-group mapping was produced, so label alignment was skipped.",
                data={
                    "skipped": True,
                    "reason": reason,
                    "original_r_group_matching": fused.r_group_matching,
                },
            )
            self._record_step_output(
                step=7,
                agent_key="requirements",
                title="Scope determination",
                summary="No verified mapping was available, so claim scope determination is inconclusive.",
                data={
                    "requirements": {
                        "is_protected": False,
                        "confidence": "very_low",
                        "reasoning": reason,
                        "r_group_analysis": {},
                    },
                    "llm_response": llm_outputs.get("match_fusion"),
                },
            )
            self._record_step_output(
                step=8,
                agent_key="report",
                title="Infringement report",
                summary="No conclusive infringement report was generated; the skip reason was recorded.",
                data={
                    "report": {
                        "confidence": "very_low",
                        "detailed_analysis": reason,
                    },
                    "source": "early_no_verified_match_result",
                },
            )
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
            self._record_step_output(
                step=6,
                agent_key="alignment",
                title="R-group 对齐",
                summary="R-group 标签无法安全对齐到权利要求变量。",
                data={
                    "alignment_result": alignment_result,
                    "original_r_group_matching": fused.r_group_matching,
                    "reason": reason,
                    "llm_response": llm_outputs.get("r_group_alignment"),
                },
            )
            self._record_step_output(
                step=7,
                agent_key="requirements",
                title="Scope determination",
                summary="Claim scope determination was skipped because label alignment failed.",
                data={
                    "requirements": {
                        "is_protected": False,
                        "confidence": "very_low",
                        "reasoning": reason,
                        "r_group_analysis": {},
                    },
                    "llm_response": llm_outputs.get("r_group_alignment"),
                },
            )
            self._record_step_output(
                step=8,
                agent_key="report",
                title="Infringement report",
                summary="No conclusive infringement report was generated; the alignment failure was recorded.",
                data={
                    "report": {
                        "confidence": "very_low",
                        "detailed_analysis": reason,
                    },
                    "source": "early_alignment_failure",
                },
            )
            return self._no_verified_match_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                markush=markush,
                fused=fused,
                reason=reason,
                llm_outputs=llm_outputs,
            )

        self._record_step_output(
            step=6,
            agent_key="alignment",
            title="R-group 对齐",
            summary=f"已对齐 {len(effective_r_group_matching or {})} 个 R-group 标签。",
            data={
                "alignment_result": alignment_result,
                "original_r_group_matching": fused.r_group_matching,
                "effective_r_group_matching": effective_r_group_matching,
                "llm_response": llm_outputs.get("r_group_alignment"),
                "fallback": llm_outputs.get("r_group_alignment_fallback"),
            },
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
            self._record_step_output(
                step=7,
                agent_key="requirements",
                title="保护范围判断",
                summary="权利要求要件检查失败。",
                data={
                    "error": str(e),
                    "r_group_matching": effective_r_group_matching,
                    "llm_response": llm_outputs.get("requirements_examination"),
                },
            )
            return self._non_conclusive_result(
                patent_id=patent_id,
                target_smiles=target_smiles,
                reason=f"Error during requirements examination: {e}",
                status="failed",
                markush=markush,
                fused=fused,
                llm_outputs=llm_outputs,
            )
        self._record_step_output(
            step=7,
            agent_key="requirements",
            title="保护范围判断",
            summary=(
                "目标分子被判断落入保护范围。"
                if req_result.is_protected
                else "目标分子被判断未落入保护范围。"
            ),
            data={
                "requirements": req_result,
                "llm_response": llm_outputs.get("requirements_examination"),
            },
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
        self._record_step_output(
            step=8,
            agent_key="report",
            title="最终报告",
            summary="侵权分析报告已生成。",
            data={
                "report": report,
                "llm_response": llm_outputs.get("infringement_report"),
            },
        )

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
            analysis_status="protected" if req_result.is_protected else "not_protected",
            is_conclusive=True,
        )
