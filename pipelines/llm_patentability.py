"""LLM-only patentability workflow for the Web workbench."""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from agents.llm_markush_extractor import LLMMarkushExtractorAgent
from agents.markush_image_selector import MarkushImageSelection, MarkushImageSelectorAgent
from agents.novelty_analyzer import NoveltyAnalyzerAgent
from agents.prior_art_searcher import PriorArtSearcherAgent
from agents.report_generator import ReportGeneratorAgent
from agents.success_rate_analyzer import SuccessRateAnalyzerAgent
from schemas.types import (
    MarkushStructure,
    PatentDocument,
    PatentImage,
    PatentabilityResult,
    PriorArt,
)
from tools.llm_client import LLMClient
from tools.llm_config import build_llm_config
from tools.logger import log
from tools.patent_scraper import PatentScraperTool


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


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class LLMPatentabilityPipeline:
    """Patentability analysis without MarkushGrapher or RDKit dependencies."""

    PATENT_ID_PATTERN = re.compile(r"^[A-Z]{2,3}[0-9][A-Z0-9]*$")

    def __init__(
        self,
        config: dict,
        *,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_api_key_env: Optional[str] = None,
        step_output_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self.config = build_llm_config(
            config,
            pipeline_key="llm_patentability",
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_api_key_env=llm_api_key_env,
        )
        pat_cfg = self.config.get("pipelines", {}).get("patentability", {})
        selection_cfg = self.config.get("pipelines", {}).get("markush_image_selection", {})
        self.max_prior_arts = int(pat_cfg.get("max_prior_arts", 10))
        self.image_selection_enabled = bool(selection_cfg.get("enabled", False))
        self.image_selection_max_images = int(selection_cfg.get("max_images", 60))
        self.image_selection_min_score = float(selection_cfg.get("min_score", 0.55))
        self.image_selection_allow_fallback = bool(
            selection_cfg.get("allow_candidate_fallback", True)
        )
        self.step_outputs: list[dict[str, Any]] = []
        self._step_output_callback = step_output_callback

        self.scraper = PatentScraperTool(self.config)
        llm = LLMClient(self.config)
        self.image_selector = MarkushImageSelectorAgent(llm)
        self.markush_extractor = LLMMarkushExtractorAgent(llm)
        self.prior_art_searcher = PriorArtSearcherAgent(llm)
        self.novelty_analyzer = NoveltyAnalyzerAgent(llm)
        self.success_rate_analyzer = SuccessRateAnalyzerAgent(llm)
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

    @classmethod
    def _normalize_patent_id(cls, patent_id: str) -> str:
        return re.sub(r"[\s\-_/]+", "", patent_id.strip().upper())

    @classmethod
    def _is_candidate_patent_id(cls, patent_id: str) -> bool:
        return bool(cls.PATENT_ID_PATTERN.fullmatch(patent_id))

    def _merge_prior_art_candidates(
        self,
        suggested_ids: list[str],
        known_prior_art_ids: Optional[list[str]],
    ) -> tuple[list[tuple[str, str]], list[str]]:
        merged: list[tuple[str, str]] = []
        notes: list[str] = []
        seen: set[str] = set()

        def add_many(ids: Optional[list[str]], source: str) -> None:
            if not ids:
                return
            for patent_id in ids:
                normalized = self._normalize_patent_id(patent_id)
                if not normalized:
                    continue
                if not self._is_candidate_patent_id(normalized):
                    notes.append(f"Ignored invalid {source} prior-art id: {patent_id}")
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                merged.append((normalized, source))

        add_many(known_prior_art_ids, "user-supplied")
        add_many(suggested_ids, "LLM-suggested")
        return merged[: self.max_prior_arts], notes

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
        patent: PatentDocument,
        proposed_cxsmiles: str,
    ) -> tuple[Optional[str], dict[str, Any]]:
        if not self.image_selection_enabled or not patent.images:
            return None, {"skipped": True, "image_count": len(patent.images)}
        try:
            selection, evaluations = self.image_selector.select_main_markush_image(
                patent=patent,
                target_smiles=proposed_cxsmiles,
                purpose="llm_patentability_prior_art",
                max_images=self.image_selection_max_images,
                min_score=self.image_selection_min_score,
                allow_candidate_fallback=self.image_selection_allow_fallback,
            )
        except Exception as exc:
            return None, {"error": str(exc), "image_count": len(patent.images)}
        return (
            selection.image_path if selection else None,
            {
                "selected": self._selection_summary(selection) if selection else None,
                "evaluations": [self._selection_summary(item) for item in evaluations],
            },
        )

    def _resolve_proposed_structure(
        self,
        *,
        proposed_cxsmiles: Optional[str],
        proposed_image_path: Optional[str],
        tech_domain: str,
    ) -> tuple[MarkushStructure, str, dict[str, Any]]:
        if proposed_cxsmiles:
            structure = MarkushStructure(
                cxsmiles=proposed_cxsmiles,
                caption=proposed_cxsmiles,
                substituent_table={},
            )
            return structure, proposed_cxsmiles, {"source": "cxsmiles"}

        if not proposed_image_path:
            raise ValueError("Must provide either proposed_cxsmiles or proposed_image_path")

        patent = PatentDocument(
            patent_id="PROPOSED_STRUCTURE",
            claims_text=f"用户上传的拟申请结构。技术领域：{tech_domain}",
            description_text="该图片代表拟申请的 Markush 或候选药物分子结构。",
            images=[PatentImage(path=proposed_image_path)],
        )
        structure = self.markush_extractor.run(
            patent=patent,
            target_smiles=tech_domain,
            image_path=proposed_image_path,
        )
        resolved = (structure.cxsmiles or structure.caption or "").strip()
        if not resolved:
            raise ValueError("LLM could not resolve the proposed structure image")
        if not structure.cxsmiles:
            structure.cxsmiles = resolved
        return (
            structure,
            resolved,
            {
                "source": "image",
                "image_path": proposed_image_path,
                "llm_response": self.markush_extractor.last_llm_response,
            },
        )

    def _search_prior_art_candidates(
        self,
        *,
        proposed_cxsmiles: str,
        tech_domain: str,
        known_prior_art_ids: Optional[list[str]],
    ) -> tuple[list[tuple[str, str]], list[str], dict[str, Any]]:
        validation_notes: list[str] = []
        try:
            search_result = self.prior_art_searcher.run(
                proposed_cxsmiles=proposed_cxsmiles,
                tech_domain=tech_domain,
            )
            suggested_ids = search_result.get("patent_ids", [])
        except Exception as exc:
            search_result = {
                "patent_ids": [],
                "search_queries": [],
                "reasoning": f"Prior-art candidate generation failed: {exc}",
                "key_structural_features": [],
            }
            suggested_ids = []
            validation_notes.append(str(search_result["reasoning"]))

        candidates, notes = self._merge_prior_art_candidates(
            suggested_ids=suggested_ids,
            known_prior_art_ids=known_prior_art_ids,
        )
        validation_notes.extend(notes)
        return candidates, validation_notes, search_result

    def _load_prior_arts(
        self,
        *,
        prior_art_candidates: list[tuple[str, str]],
        proposed_cxsmiles: str,
    ) -> tuple[list[PriorArt], list[str], list[dict[str, Any]]]:
        prior_arts: list[PriorArt] = []
        validation_notes: list[str] = []
        extraction_rows: list[dict[str, Any]] = []

        for patent_id, source in prior_art_candidates:
            log.info(f"  Processing prior art: {patent_id} ({source})")
            row: dict[str, Any] = {"patent_id": patent_id, "source": source}
            try:
                patent = self.scraper.fetch(patent_id)
                row["fetch"] = {
                    "claims_text_length": len(patent.claims_text),
                    "image_count": len(patent.images),
                }
            except Exception as exc:
                note = f"Rejected {source} prior-art candidate {patent_id}: fetch failed ({exc})"
                validation_notes.append(note)
                row["error"] = str(exc)
                extraction_rows.append(row)
                log.warning(f"  {note}")
                continue

            image_path, selection = self._select_main_markush_image(
                patent,
                proposed_cxsmiles=proposed_cxsmiles,
            )
            row["image_selection"] = selection
            try:
                structure = self.markush_extractor.run(
                    patent=patent,
                    target_smiles=proposed_cxsmiles,
                    image_path=image_path,
                )
                resolved = (structure.cxsmiles or structure.caption or "").strip()
                if resolved and not structure.cxsmiles:
                    structure.cxsmiles = resolved
                structures = [structure] if resolved else []
                row["markush_structure"] = structure if resolved else None
                row["llm_response"] = self.markush_extractor.last_llm_response
            except Exception as exc:
                structures = []
                row["error"] = str(exc)
                validation_notes.append(
                    f"Prior-art {patent_id} Markush extraction failed: {exc}"
                )
                log.warning(f"  Prior-art {patent_id} Markush extraction failed: {exc}")

            prior_arts.append(
                PriorArt(
                    patent_id=patent_id,
                    relevance_score=0.5,
                    overlap_description=(
                        "LLM extracted a comparable Markush structure."
                        if structures
                        else "Patent fetched, but no comparable Markush structure was extracted."
                    ),
                    markush_structures=structures,
                )
            )
            row["markush_count"] = len(structures)
            extraction_rows.append(row)

        return prior_arts, validation_notes, extraction_rows

    @staticmethod
    def _report_payload(
        *,
        proposed_cxsmiles: str,
        tech_domain: str,
        novelty: dict[str, Any],
        prior_arts: list[PriorArt],
    ) -> dict[str, Any]:
        return {
            "proposed_cxsmiles": proposed_cxsmiles,
            "tech_domain": tech_domain,
            "novelty_score": novelty.get("novelty_score", 0),
            "novel_features": novelty.get("novel_features", []),
            "overlapping_features": novelty.get("overlapping_features", []),
            "prior_art_summary": [
                {
                    "patent_id": prior_art.patent_id,
                    "n_markush": len(prior_art.markush_structures),
                    "overlap_description": prior_art.overlap_description,
                }
                for prior_art in prior_arts
            ],
            "risk_points": novelty.get("risk_points", []),
        }

    def run(
        self,
        proposed_cxsmiles: Optional[str] = None,
        proposed_image_path: Optional[str] = None,
        tech_domain: str = "",
        known_prior_art_ids: Optional[list[str]] = None,
    ) -> PatentabilityResult:
        log.set_total_steps(6)
        llm_outputs: dict[str, Any] = {
            "llm_only_workflow": True,
            "llm_model": self.config.get("llm", {}).get("model"),
        }

        log.step("Resolving proposed structure with LLM")
        proposed, resolved_cxsmiles, resolve_meta = self._resolve_proposed_structure(
            proposed_cxsmiles=proposed_cxsmiles,
            proposed_image_path=proposed_image_path,
            tech_domain=tech_domain,
        )
        llm_outputs["proposed_structure_resolution"] = resolve_meta.get("llm_response")
        self._record_step_output(
            step=1,
            agent_key="resolve",
            title="拟申请结构解析",
            summary="已解析拟申请结构。",
            data={
                "proposed_structure": proposed,
                "resolved_cxsmiles": resolved_cxsmiles,
                "meta": resolve_meta,
            },
        )

        log.step("Searching for prior art")
        candidates, validation_notes, search_result = self._search_prior_art_candidates(
            proposed_cxsmiles=resolved_cxsmiles,
            tech_domain=tech_domain,
            known_prior_art_ids=known_prior_art_ids,
        )
        llm_outputs["prior_art_search"] = self.prior_art_searcher.last_llm_response
        self._record_step_output(
            step=2,
            agent_key="search",
            title="现有技术检索",
            summary=f"得到 {len(candidates)} 个候选现有技术专利。",
            data={
                "search_result": search_result,
                "candidate_patents": [
                    {"patent_id": patent_id, "source": source}
                    for patent_id, source in candidates
                ],
                "validation_notes": validation_notes,
            },
        )

        log.step(f"Extracting Markush structures from {len(candidates)} prior art patent(s)")
        prior_arts, load_notes, extraction_rows = self._load_prior_arts(
            prior_art_candidates=candidates,
            proposed_cxsmiles=resolved_cxsmiles,
        )
        validation_notes.extend(load_notes)
        self._record_step_output(
            step=3,
            agent_key="prior_markush",
            title="Prior-art Markush 解析",
            summary=f"已处理 {len(extraction_rows)} 个候选专利，得到 {len(prior_arts)} 个可比较对象。",
            data={
                "prior_art_extractions": extraction_rows,
                "validation_notes": validation_notes,
            },
        )

        log.step("Assessing novelty")
        try:
            novelty = self.novelty_analyzer.run(
                proposed_cxsmiles=resolved_cxsmiles,
                prior_arts=prior_arts,
                tech_domain=tech_domain,
            )
            llm_outputs["novelty_analysis"] = self.novelty_analyzer.last_llm_response
        except Exception as exc:
            novelty = {
                "novelty_score": 0.0,
                "overlapping_features": [],
                "novel_features": [],
                "risk_points": [f"Novelty analysis error: {exc}"],
                "suggestions": [],
                "reasoning": f"Error during novelty analysis: {exc}",
            }
            llm_outputs["novelty_analysis"] = {"error": str(exc)}
            log.error(f"  Novelty analysis failed: {exc}")
        self._record_step_output(
            step=4,
            agent_key="novelty",
            title="新颖性分析",
            summary=f"新颖性评分：{_coerce_float(novelty.get('novelty_score')):.2f}",
            data={
                "novelty": novelty,
                "llm_response": llm_outputs.get("novelty_analysis"),
            },
        )

        log.step("Analyzing authorization likelihood")
        try:
            success_analysis = self.success_rate_analyzer.run(
                proposed_cxsmiles=resolved_cxsmiles,
                tech_domain=tech_domain,
                novelty_data=novelty,
                prior_arts=prior_arts,
            )
            llm_outputs["success_rate_analysis"] = (
                self.success_rate_analyzer.last_llm_response
            )
        except Exception as exc:
            success_analysis = {
                "success_rate_estimation": "",
                "key_risks": [f"Authorization analysis failed: {exc}"],
                "improvement_suggestions": [],
                "comprehensive_report": f"Authorization analysis failed: {exc}",
            }
            llm_outputs["success_rate_analysis"] = {"error": str(exc)}
            log.warning(f"  Authorization likelihood analysis failed: {exc}")
        self._record_step_output(
            step=5,
            agent_key="authorization",
            title="授权可能性分析",
            summary=(
                f"授权可能性：{success_analysis.get('success_rate_estimation') or '未量化'}"
            ),
            data={
                "success_analysis": success_analysis,
                "llm_response": llm_outputs.get("success_rate_analysis"),
            },
        )

        log.step("Generating patentability report")
        try:
            report = self.reporter.run(
                report_type="patentability",
                analysis_data=self._report_payload(
                    proposed_cxsmiles=resolved_cxsmiles,
                    tech_domain=tech_domain,
                    novelty=novelty,
                    prior_arts=prior_arts,
                ),
            )
            llm_outputs["patentability_report"] = self.reporter.last_llm_response
        except Exception as exc:
            report = {
                "detailed_analysis": f"Analysis completed but report generation failed: {exc}",
                "recommendations": [],
                "confidence": "very_low",
            }
            llm_outputs["patentability_report"] = {"error": str(exc)}
            log.warning(f"  Report generation failed: {exc}")
        self._record_step_output(
            step=6,
            agent_key="report",
            title="最终报告",
            summary="可授权分析报告已生成。",
            data={
                "report": report,
                "llm_response": llm_outputs.get("patentability_report"),
            },
        )

        risk_points = validation_notes + list(novelty.get("risk_points", []))
        return PatentabilityResult(
            proposed_structure=proposed,
            novelty_score=_coerce_float(novelty.get("novelty_score")),
            prior_arts=prior_arts,
            risk_points=risk_points,
            suggestions=list(novelty.get("suggestions", [])),
            success_analysis=success_analysis,
            llm_outputs=llm_outputs,
            report=report.get("detailed_analysis")
            or success_analysis.get("comprehensive_report", ""),
        )
