"""LangGraph orchestration trial for the LLM-only infringement workflow.

This module intentionally keeps the existing agents, tools, schemas, and
business rules. LangGraph is used only as the pipeline control layer so the
legacy ``LLMInfringementPipeline`` remains the baseline implementation.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised only when optional dep is absent.
    END = START = StateGraph = None  # type: ignore[assignment]

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict

from agents.claim_analyzer import ClaimAnalysis
from pipelines.llm_infringement import LLMInfringementPipeline, _dump
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
from tools.logger import log


class LangGraphInfringementState(TypedDict, total=False):
    patent_id: str
    target_smiles: str
    input_markush_caption: Optional[str]
    input_markush_structure: Optional[MarkushStructure]
    llm_outputs: dict[str, Any]
    patent: PatentDocument
    image_path: Optional[str]
    markush: Optional[MarkushStructure]
    markush_caption: str
    claim_analysis: Optional[ClaimAnalysis]
    llm_match_result: Optional[MatchResult]
    fused: FusedMatchResult
    alignment_result: Optional[RGroupAlignmentResult]
    effective_r_group_matching: dict[str, str]
    requirements: RequirementsResult
    report: dict[str, Any]
    result: InfringementResult


class LangGraphLLMInfringementPipeline(LLMInfringementPipeline):
    """LLM-only infringement pipeline with LangGraph as the orchestration layer."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.graph = self._build_graph()

    @staticmethod
    def _ensure_langgraph_available() -> None:
        if StateGraph is None or START is None or END is None:
            raise ImportError(
                "LangGraphLLMInfringementPipeline requires the optional "
                "'langgraph' dependency. Install it with: pip install langgraph"
            )

    @staticmethod
    def _route_result(state: LangGraphInfringementState) -> str:
        return "end" if state.get("result") is not None else "next"

    def _build_graph(self):
        self._ensure_langgraph_available()
        workflow = StateGraph(LangGraphInfringementState)
        workflow.add_node("fetch_patent", self._node_fetch_patent)
        workflow.add_node("extract_markush", self._node_extract_markush)
        workflow.add_node("analyze_claims", self._node_analyze_claims)
        workflow.add_node("match_structure", self._node_match_structure)
        workflow.add_node("fuse_matches", self._node_fuse_matches)
        workflow.add_node("align_r_groups", self._node_align_r_groups)
        workflow.add_node("examine_requirements", self._node_examine_requirements)
        workflow.add_node("generate_report", self._node_generate_report)

        workflow.add_edge(START, "fetch_patent")
        workflow.add_conditional_edges(
            "fetch_patent",
            self._route_result,
            {"next": "extract_markush", "end": END},
        )
        workflow.add_conditional_edges(
            "extract_markush",
            self._route_result,
            {"next": "analyze_claims", "end": END},
        )
        workflow.add_edge("analyze_claims", "match_structure")
        workflow.add_conditional_edges(
            "match_structure",
            self._route_result,
            {"next": "fuse_matches", "end": END},
        )
        workflow.add_conditional_edges(
            "fuse_matches",
            self._route_result,
            {"next": "align_r_groups", "end": END},
        )
        workflow.add_conditional_edges(
            "align_r_groups",
            self._route_result,
            {"next": "examine_requirements", "end": END},
        )
        workflow.add_conditional_edges(
            "examine_requirements",
            self._route_result,
            {"next": "generate_report", "end": END},
        )
        workflow.add_edge("generate_report", END)
        return workflow.compile()

    def _base_result_kwargs(self, state: LangGraphInfringementState) -> dict[str, Any]:
        return {
            "patent_id": state["patent_id"],
            "target_smiles": state["target_smiles"],
            "llm_outputs": state["llm_outputs"],
        }

    def _node_fetch_patent(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        patent_id = state["patent_id"]
        log.step(f"Fetching patent {patent_id}")
        try:
            patent = self.scraper.fetch(patent_id)
        except Exception as exc:
            log.error(f"Failed to fetch patent: {exc}")
            self._record_step_output(
                step=1,
                agent_key="fetch",
                title="Patent fetch summary",
                summary=f"Failed to fetch patent {patent_id}.",
                data={"patent_id": patent_id, "error": str(exc)},
            )
            return {
                "result": self._non_conclusive_result(
                    reason=f"Error: Failed to fetch patent {patent_id}: {exc}",
                    status="failed",
                    **self._base_result_kwargs(state),
                )
            }

        log.info(f"  >> claims_text length: {len(patent.claims_text)} chars")
        log.info(f"  >> images found: {len(patent.images)}")
        log.info(f"  >> claims_text (first 800 chars):\n{patent.claims_text[:800]}")
        self._record_step_output(
            step=1,
            agent_key="fetch",
            title="Patent fetch summary",
            summary=(
                f"Fetched {patent.patent_id}: {len(patent.claims_text)} claim "
                f"characters and {len(patent.images)} image(s)."
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
        return {"patent": patent}

    def _node_extract_markush(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        log.step("Extracting Markush structure with LLM")
        patent = state["patent"]
        target_smiles = state["target_smiles"]
        llm_outputs = state["llm_outputs"]
        markush_caption = state.get("input_markush_caption")
        markush_structure = state.get("input_markush_structure")
        provided_caption = bool(markush_caption or markush_structure)
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

        markush_caption = markush_caption or ""
        log.info(f"  >> markush_caption: {markush_caption}")
        self._record_step_output(
            step=2,
            agent_key="markush",
            title="Markush structure extraction",
            summary=(
                "A Markush description is available for downstream matching."
                if markush_caption
                else "No Markush description was produced."
            ),
            data={
                "provided_caption": provided_caption,
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
            return {
                "llm_outputs": llm_outputs,
                "markush": markush,
                "markush_caption": markush_caption,
                "result": self._non_conclusive_result(
                    reason=reason,
                    status="failed" if extraction_error else "undetermined",
                    markush=markush,
                    **self._base_result_kwargs(state),
                ),
            }

        return {
            "llm_outputs": llm_outputs,
            "markush": markush,
            "markush_caption": markush_caption,
        }

    def _node_analyze_claims(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        log.step("Analyzing patent claims")
        patent = state["patent"]
        markush_caption = state["markush_caption"]
        llm_outputs = state["llm_outputs"]
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
        except Exception as exc:
            llm_outputs["claim_analysis"] = {"error": str(exc)}
            log.warning(
                f"  Claim analysis failed: {exc}, continuing with LLM Markush caption"
            )

        self._record_step_output(
            step=3,
            agent_key="claim",
            title="Claim analysis",
            summary=(
                f"Identified {len(claim_analysis.markush_claims or [])} "
                "Markush-related claim(s)."
                if claim_analysis
                else "Claim analysis failed or returned no structured result."
            ),
            data={
                "claim_analysis": claim_analysis,
                "llm_response": llm_outputs.get("claim_analysis"),
                "effective_markush_caption": markush_caption,
            },
        )
        return {
            "llm_outputs": llm_outputs,
            "claim_analysis": claim_analysis,
            "markush_caption": markush_caption,
        }

    def _node_match_structure(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        log.step("Running LLM substructure matching")
        patent = state["patent"]
        llm_outputs = state["llm_outputs"]
        try:
            llm_match_result = self.structure_matcher.run(
                markush_caption=state["markush_caption"],
                markush_structure=state.get("markush"),
                target_smiles=state["target_smiles"],
                claim_analysis=state.get("claim_analysis"),
                claim_text=patent.claims_text,
            )
            llm_outputs["llm_structure_matching"] = (
                self.structure_matcher.last_llm_response
            )
            log.info(f"  >> LLM MatchResult:\n{_dump(llm_match_result)}")
        except Exception as exc:
            llm_outputs["llm_structure_matching"] = {"error": str(exc)}
            log.warning(f"  LLM substructure matching failed: {exc}")
            self._record_step_output(
                step=4,
                agent_key="llm_match",
                title="LLM structure matching",
                summary="LLM structure matching failed; stopping scope analysis.",
                data={
                    "error": str(exc),
                    "llm_response": llm_outputs.get("llm_structure_matching"),
                },
            )
            return {
                "llm_outputs": llm_outputs,
                "result": self._non_conclusive_result(
                    reason=f"Error during LLM substructure matching: {exc}",
                    status="failed",
                    markush=state.get("markush"),
                    **self._base_result_kwargs(state),
                )
            }

        self._record_step_output(
            step=4,
            agent_key="llm_match",
            title="LLM structure matching",
            summary=(
                f"LLM skeleton match result: {llm_match_result.is_match}."
                if llm_match_result
                else "LLM structure matching returned no usable result."
            ),
            data={
                "match_result": llm_match_result,
                "llm_response": llm_outputs.get("llm_structure_matching"),
            },
        )
        return {
            "llm_outputs": llm_outputs,
            "llm_match_result": llm_match_result,
        }

    def _node_fuse_matches(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        log.step("Fusing and verifying matches")
        llm_outputs = state["llm_outputs"]
        llm_match_result = state.get("llm_match_result")
        try:
            fused: FusedMatchResult = self.subs_matcher.run(
                markush_caption=state["markush_caption"],
                target_smiles=state["target_smiles"],
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
        except Exception as exc:
            log.error(f"  Match fusion failed: {exc}")
            self._record_step_output(
                step=5,
                agent_key="fusion",
                title="Match fusion",
                summary="LLM match fusion failed.",
                data={
                    "error": str(exc),
                    "llm_match_result": llm_match_result,
                    "llm_response": llm_outputs.get("match_fusion"),
                },
            )
            return {
                "llm_outputs": llm_outputs,
                "result": self._non_conclusive_result(
                    reason=f"Error during match fusion: {exc}",
                    status="failed",
                    markush=state.get("markush"),
                    **self._base_result_kwargs(state),
                )
            }

        self._record_step_output(
            step=5,
            agent_key="fusion",
            title="Match fusion",
            summary=(
                f"Produced {len(fused.r_group_matching or {})} R-group mapping(s)."
                if fused.r_group_matching
                else "No verified R-group mapping was produced."
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
                    summary=(
                        "No verified R-group mapping was produced, so label "
                        "alignment was skipped."
                    ),
                    data={
                        "skipped": True,
                        "reason": "Skeleton mismatch; there is no R-group mapping to align.",
                        "original_r_group_matching": fused.r_group_matching,
                    },
                )
                self._record_step_output(
                    step=7,
                    agent_key="requirements",
                    title="Scope determination",
                    summary=(
                        "The target skeleton did not match, so the result is "
                        "non-infringement."
                    ),
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
                        "result."
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
                return {
                    "llm_outputs": llm_outputs,
                    "fused": fused,
                    "result": self._not_protected_no_match_result(
                        markush=state.get("markush"),
                        fused=fused,
                        reason=reason,
                        **self._base_result_kwargs(state),
                    ),
                }

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
                summary=(
                    "No verified R-group mapping was produced, so label alignment "
                    "was skipped."
                ),
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
                summary=(
                    "No verified mapping was available, so claim scope "
                    "determination is inconclusive."
                ),
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
                summary=(
                    "No conclusive infringement report was generated; the skip "
                    "reason was recorded."
                ),
                data={
                    "report": {
                        "confidence": "very_low",
                        "detailed_analysis": reason,
                    },
                    "source": "early_no_verified_match_result",
                },
            )
            return {
                "llm_outputs": llm_outputs,
                "fused": fused,
                "result": self._no_verified_match_result(
                    markush=state.get("markush"),
                    fused=fused,
                    reason=reason,
                    **self._base_result_kwargs(state),
                ),
            }

        return {
            "llm_outputs": llm_outputs,
            "fused": fused,
        }

    def _node_align_r_groups(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        log.step("Aligning R-group labels with claim variables")
        patent = state["patent"]
        fused = state["fused"]
        llm_outputs = state["llm_outputs"]
        alignment_result: Optional[RGroupAlignmentResult] = None
        effective_r_group_matching = fused.r_group_matching
        try:
            alignment_result = self.r_group_aligner.run(
                markush_caption=state["markush_caption"],
                target_smiles=state["target_smiles"],
                r_group_matching=fused.r_group_matching,
                claim_analysis=state.get("claim_analysis"),
                claim_text=patent.claims_text,
            )
            llm_outputs["r_group_alignment"] = self.r_group_aligner.last_llm_response
            llm_outputs["r_group_alignment_parsed"] = dataclasses.asdict(
                alignment_result
            )
            log.info(f"  >> RGroupAlignmentResult:\n{_dump(alignment_result)}")
        except Exception as exc:
            llm_outputs["r_group_alignment"] = {"error": str(exc)}
            alignment_result = RGroupAlignmentResult(
                reasoning=f"R-group label alignment failed: {exc}",
                confidence=Confidence.VERY_LOW,
            )
            log.warning(f"  R-group label alignment failed: {exc}")

        if self._alignment_covers_source_labels(
            alignment_result, fused.r_group_matching
        ):
            effective_r_group_matching = alignment_result.aligned_r_group_matching
        elif self._can_use_identity_alignment(
            fused.r_group_matching, state.get("claim_analysis")
        ):
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
                title="R-group alignment",
                summary=(
                    "R-group labels could not be safely aligned to claim "
                    "variables."
                ),
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
                summary=(
                    "Claim scope determination was skipped because label "
                    "alignment failed."
                ),
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
                summary=(
                    "No conclusive infringement report was generated; the "
                    "alignment failure was recorded."
                ),
                data={
                    "report": {
                        "confidence": "very_low",
                        "detailed_analysis": reason,
                    },
                    "source": "early_alignment_failure",
                },
            )
            return {
                "llm_outputs": llm_outputs,
                "alignment_result": alignment_result,
                "result": self._no_verified_match_result(
                    markush=state.get("markush"),
                    fused=fused,
                    reason=reason,
                    **self._base_result_kwargs(state),
                ),
            }

        self._record_step_output(
            step=6,
            agent_key="alignment",
            title="R-group alignment",
            summary=(
                f"Aligned {len(effective_r_group_matching or {})} R-group label(s)."
            ),
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
        return {
            "llm_outputs": llm_outputs,
            "fused": fused,
            "alignment_result": alignment_result,
            "effective_r_group_matching": effective_r_group_matching,
        }

    def _node_examine_requirements(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        log.step("Examining requirements")
        fused = state["fused"]
        alignment_result = state["alignment_result"]
        effective_r_group_matching = state["effective_r_group_matching"]
        llm_outputs = state["llm_outputs"]
        try:
            req_result: RequirementsResult = self.req_examiner.run(
                markush_caption=state["markush_caption"],
                target_smiles=state["target_smiles"],
                r_group_matching=effective_r_group_matching,
                original_r_group_matching=fused.r_group_matching,
                label_alignment=alignment_result.label_alignment,
                claim_text=state["patent"].claims_text,
            )
            llm_outputs["requirements_examination"] = (
                self.req_examiner.last_llm_response
            )
            log.info(f"  >> RequirementsResult:\n{_dump(req_result)}")
        except Exception as exc:
            log.error(f"  Requirements examination failed: {exc}")
            self._record_step_output(
                step=7,
                agent_key="requirements",
                title="Scope determination",
                summary="Claim requirement examination failed.",
                data={
                    "error": str(exc),
                    "r_group_matching": effective_r_group_matching,
                    "llm_response": llm_outputs.get("requirements_examination"),
                },
            )
            return {
                "llm_outputs": llm_outputs,
                "result": self._non_conclusive_result(
                    reason=f"Error during requirements examination: {exc}",
                    status="failed",
                    markush=state.get("markush"),
                    fused=fused,
                    **self._base_result_kwargs(state),
                )
            }

        self._record_step_output(
            step=7,
            agent_key="requirements",
            title="Scope determination",
            summary=(
                "The target molecule was judged within the claim scope."
                if req_result.is_protected
                else "The target molecule was judged outside the claim scope."
            ),
            data={
                "requirements": req_result,
                "llm_response": llm_outputs.get("requirements_examination"),
            },
        )
        return {
            "llm_outputs": llm_outputs,
            "requirements": req_result,
        }

    def _node_generate_report(
        self, state: LangGraphInfringementState
    ) -> dict[str, Any]:
        req_result = state["requirements"]
        fused = state["fused"]
        alignment_result = state["alignment_result"]
        effective_r_group_matching = state["effective_r_group_matching"]
        llm_outputs = state["llm_outputs"]

        if self.generate_report:
            log.step("Generating report")
            try:
                report_data = {
                    "patent_id": state["patent_id"],
                    "target_smiles": state["target_smiles"],
                    "markush_caption": state["markush_caption"],
                    "fused_match": fused.r_group_matching,
                    "claim_aligned_r_group_matching": effective_r_group_matching,
                    "label_alignment": alignment_result.label_alignment,
                    "is_protected": req_result.is_protected,
                    "requirements_reasoning": req_result.reasoning,
                    "r_group_analysis": req_result.r_group_analysis,
                    "structure_match_method": "llm",
                    "orchestrator": "langgraph",
                }
                report = self.reporter.run(
                    report_type="infringement",
                    analysis_data=report_data,
                )
                llm_outputs["infringement_report"] = self.reporter.last_llm_response
                log.info(f"  >> Report:\n{_dump(report)}")
            except Exception as exc:
                llm_outputs["infringement_report"] = {"error": str(exc)}
                log.warning(f"  Report generation failed: {exc}, using fallback")
                report = {
                    "confidence": req_result.confidence.value,
                    "detailed_analysis": (
                        f"Analysis completed but report generation failed: {exc}"
                    ),
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
            title="Final report",
            summary="The infringement analysis report was generated.",
            data={
                "report": report,
                "llm_response": llm_outputs.get("infringement_report"),
            },
        )
        result = InfringementResult(
            patent_id=state["patent_id"],
            target_smiles=state["target_smiles"],
            is_protected=req_result.is_protected,
            confidence=req_result.confidence,
            markush_structure=state.get("markush"),
            fused_match=fused,
            requirements=req_result,
            llm_outputs=llm_outputs,
            report=report.get("detailed_analysis", ""),
            analysis_status="protected" if req_result.is_protected else "not_protected",
            is_conclusive=True,
        )
        return {
            "llm_outputs": llm_outputs,
            "report": report,
            "result": result,
        }

    def run(
        self,
        patent_id: str,
        target_smiles: str,
        markush_caption: Optional[str] = None,
        markush_structure: Optional[MarkushStructure] = None,
    ) -> InfringementResult:
        log.set_total_steps(8 if self.generate_report else 7)
        self.step_outputs = []
        initial_state: LangGraphInfringementState = {
            "patent_id": patent_id,
            "target_smiles": target_smiles,
            "input_markush_caption": markush_caption,
            "input_markush_structure": markush_structure,
            "llm_outputs": {
                "llm_only_workflow": True,
                "llm_model": self.config.get("llm", {}).get("model"),
                "orchestrator": "langgraph",
            },
        }
        final_state = self.graph.invoke(initial_state)
        result = final_state.get("result")
        if result is None:
            raise RuntimeError("LangGraph infringement workflow finished without a result")
        return result
