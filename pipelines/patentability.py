"""专利申请成功率分析管线

输入: proposed_markush (CXSMILES 或图片) + 技术领域描述
输出: PatentabilityResult

流程:
1. [可选] MarkushGrapher → 图片识别为 CXSMILES
2. PriorArtSearcher → 检索相关现有专利
3. 对每个相关专利: PatentScraper + MarkushGrapher → 提取现有 Markush
4. NoveltyAnalyzer → 新颖性评估
5. ReportGenerator → 生成可专利性报告
"""

from __future__ import annotations
from typing import Optional
import re
import json

from schemas.types import (
    PatentabilityResult,
    MarkushStructure,
    PriorArt,
)
from tools.patent_scraper import PatentScraperTool
from tools.markush_grapher import MarkushGrapherTool
from tools.rdkit_matcher import RDKitMatcherTool
from tools.llm_client import LLMClient
from tools.logger import log
from agents.prior_art_searcher import PriorArtSearcherAgent
from agents.novelty_analyzer import NoveltyAnalyzerAgent
from agents.report_generator import ReportGeneratorAgent
from agents.success_rate_analyzer import SuccessRateAnalyzerAgent


class PatentabilityPipeline:
    PATENT_ID_PATTERN = re.compile(r"^[A-Z]{2,3}[0-9][A-Z0-9]*$")

    def __init__(self, config: dict):
        self.config = config
        pat_cfg = config["pipelines"]["patentability"]
        self.max_prior_arts = pat_cfg.get("max_prior_arts", 10)

        # Tools
        self.scraper = PatentScraperTool(config)
        self.markush_grapher = MarkushGrapherTool(config)
        self.rdkit = RDKitMatcherTool()

        # Agents
        llm = LLMClient(config)
        self.prior_art_searcher = PriorArtSearcherAgent(llm)
        self.novelty_analyzer = NoveltyAnalyzerAgent(llm)
        self.reporter = ReportGeneratorAgent(llm)
        self.success_rate_analyzer = SuccessRateAnalyzerAgent(llm)

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
                    notes.append(
                        f"Ignored {source} prior-art candidate with invalid patent-id format: {patent_id}"
                    )
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                merged.append((normalized, source))

        add_many(known_prior_art_ids, "user-supplied")
        add_many(suggested_ids, "LLM-suggested")
        return merged[: self.max_prior_arts], notes

    def _resolve_proposed_structure(
        self,
        proposed_cxsmiles: Optional[str],
        proposed_image_path: Optional[str],
    ) -> tuple[MarkushStructure, str]:
        if proposed_cxsmiles:
            return (
                MarkushStructure(
                    cxsmiles=proposed_cxsmiles,
                    substituent_table={},
                ),
                proposed_cxsmiles,
            )

        if not proposed_image_path:
            raise ValueError("Must provide either proposed_cxsmiles or proposed_image_path")

        try:
            proposed = self.markush_grapher.predict(proposed_image_path)
            resolved_cxsmiles = proposed.cxsmiles or proposed.caption
            log.info(f"  Recognized structure from image: {proposed_image_path}")
        except Exception as e:
            log.error(f"  Failed to recognize structure from image: {e}")
            raise ValueError(
                f"Could not recognize Markush structure from image '{proposed_image_path}': {e}"
            ) from e

        if not resolved_cxsmiles:
            log.error("  No CXSMILES could be derived from the proposed structure")
            raise ValueError("Proposed structure has no CXSMILES representation")

        return proposed, resolved_cxsmiles

    def _search_prior_art_candidates(
        self,
        proposed_cxsmiles: str,
        tech_domain: str,
        known_prior_art_ids: Optional[list[str]],
    ) -> tuple[list[tuple[str, str]], list[str]]:
        validation_notes: list[str] = []
        try:
            search_result = self.prior_art_searcher.run(
                proposed_cxsmiles=proposed_cxsmiles,
                tech_domain=tech_domain,
            )
            suggested_ids: list[str] = search_result.get("patent_ids", [])
        except Exception as e:
            log.warning(f"  Prior art search failed: {e}, proceeding with known IDs only")
            suggested_ids = []
            validation_notes.append(f"Prior-art candidate generation failed: {e}")

        prior_art_candidates, candidate_notes = self._merge_prior_art_candidates(
            suggested_ids=suggested_ids,
            known_prior_art_ids=known_prior_art_ids,
        )
        validation_notes.extend(candidate_notes)
        return prior_art_candidates, validation_notes

    def _extract_markush_structures(self, patent) -> list[MarkushStructure]:
        markush_list: list[MarkushStructure] = []
        for img in patent.images:
            try:
                structure = self.markush_grapher.predict(img.path)
            except Exception:
                continue
            if structure.is_markush:
                markush_list.append(structure)
        return markush_list

    def _load_prior_arts(
        self,
        prior_art_candidates: list[tuple[str, str]],
        verify_prior_art: bool = True,
    ) -> tuple[list[PriorArt], list[str]]:
        prior_arts: list[PriorArt] = []
        validation_notes: list[str] = []

        for pid, source in prior_art_candidates:
            log.info(f"  Processing prior art: {pid} ({source})")
            if not verify_prior_art:
                prior_arts.append(
                    PriorArt(
                        patent_id=pid,
                        relevance_score=0.5,
                        overlap_description=(
                            "Candidate retained without patent fetch or Markush image "
                            "extraction in lightweight patentability mode."
                        ),
                        markush_structures=[],
                    )
                )
                continue

            try:
                patent = self.scraper.fetch(pid)
                markush_list = self._extract_markush_structures(patent) if patent.images else []
            except Exception as e:
                log.warning(f"  Failed to verify {pid}: {e}")
                validation_notes.append(
                    f"Rejected {source} prior-art candidate {pid}: fetch failed ({e})"
                )
                continue

            prior_arts.append(
                PriorArt(
                    patent_id=pid,
                    relevance_score=0.5,  # refined later by NoveltyAnalyzer
                    overlap_description="",
                    markush_structures=markush_list,
                )
            )
            log.info(f"    Found {len(markush_list)} Markush structure(s) in {pid}")

        return prior_arts, validation_notes

    @staticmethod
    def _report_payload(
        proposed_cxsmiles: str,
        tech_domain: str,
        novelty: dict,
        prior_arts: list[PriorArt],
    ) -> dict:
        return {
            "proposed_cxsmiles": proposed_cxsmiles,
            "tech_domain": tech_domain,
            "novelty_score": novelty.get("novelty_score", 0),
            "novel_features": novelty.get("novel_features", []),
            "overlapping_features": novelty.get("overlapping_features", []),
            "prior_art_summary": [
                {"patent_id": pa.patent_id, "n_markush": len(pa.markush_structures)}
                for pa in prior_arts
            ],
            "risk_points": novelty.get("risk_points", []),
        }

    def _build_report(
        self,
        proposed_cxsmiles: str,
        tech_domain: str,
        novelty: dict,
        prior_arts: list[PriorArt],
    ) -> dict:
        try:
            return self.reporter.run(
                report_type="patentability",
                analysis_data=self._report_payload(
                    proposed_cxsmiles=proposed_cxsmiles,
                    tech_domain=tech_domain,
                    novelty=novelty,
                    prior_arts=prior_arts,
                ),
            )
        except Exception as e:
            log.warning(f"  Report generation failed: {e}, using fallback")
            return {
                "detailed_analysis": f"Analysis completed but report generation failed: {e}",
            }

    def run(
        self,
        proposed_cxsmiles: Optional[str] = None,
        proposed_image_path: Optional[str] = None,
        tech_domain: str = "",
        known_prior_art_ids: Optional[list[str]] = None,
        verify_prior_art: bool = True,
    ) -> PatentabilityResult:
        """执行可专利性分析

        Args:
            proposed_cxsmiles: 拟申请的 CXSMILES（与 image_path 二选一）
            proposed_image_path: 拟申请结构的图片路径
            tech_domain: 技术领域描述
            known_prior_art_ids: 已知的相关专利号列表
            verify_prior_art: 是否抓取并解析 prior-art 专利图片；批处理可关闭以节省时间

        Returns:
            PatentabilityResult
        """
        log.set_total_steps(6)
        llm_outputs: dict[str, object] = {}

        # Step 1: 获取拟申请结构
        log.step("Resolving proposed structure")
        proposed, proposed_cxsmiles = self._resolve_proposed_structure(
            proposed_cxsmiles=proposed_cxsmiles,
            proposed_image_path=proposed_image_path,
        )

        # Step 2: 检索现有技术
        log.step("Searching for prior art")
        prior_art_candidates, validation_notes = self._search_prior_art_candidates(
            proposed_cxsmiles=proposed_cxsmiles,
            tech_domain=tech_domain,
            known_prior_art_ids=known_prior_art_ids,
        )
        if self.prior_art_searcher.last_llm_response is not None:
            llm_outputs["prior_art_search"] = self.prior_art_searcher.last_llm_response
        prior_art_ids = [patent_id for patent_id, _ in prior_art_candidates]

        if not prior_art_ids:
            log.warning("  No prior art patents identified — novelty analysis will be limited")

        # Step 3: 获取并分析每个现有专利
        log.step(f"Analyzing {len(prior_art_ids)} prior art patent(s)")
        prior_arts, load_notes = self._load_prior_arts(
            prior_art_candidates,
            verify_prior_art=verify_prior_art,
        )
        validation_notes.extend(load_notes)

        if not prior_arts and prior_art_ids:
            log.warning("  Could not retrieve any prior art patents — novelty score may be unreliable")
            validation_notes.append(
                "No prior-art candidates could be verified by fetching a patent document."
            )

        # Step 4: 新颖性评估
        log.step("Assessing novelty")
        try:
            novelty = self.novelty_analyzer.run(
                proposed_cxsmiles=proposed_cxsmiles,
                prior_arts=prior_arts,
                tech_domain=tech_domain,
            )
            llm_outputs["novelty_analysis"] = self.novelty_analyzer.last_llm_response
        except Exception as e:
            llm_outputs["novelty_analysis"] = {"error": str(e)}
            log.error(f"  Novelty analysis failed: {e}")
            return PatentabilityResult(
                proposed_structure=proposed,
                novelty_score=0.0,
                prior_arts=prior_arts,
                risk_points=validation_notes + [f"Novelty analysis error: {e}"],
                suggestions=[],
                success_analysis={},
                llm_outputs=llm_outputs,
                report=f"Error during novelty analysis: {e}",
            )

        # Step 4.5: 成功率等多维度分析
        log.step("Analyzing success rate (Novelty, Inventiveness, etc.)")
        try:
            success_analysis = self.success_rate_analyzer.run(
                proposed_cxsmiles=proposed_cxsmiles,
                tech_domain=tech_domain,
                novelty_data=novelty,
                prior_arts=prior_arts,
            )
            llm_outputs["success_rate_analysis"] = (
                self.success_rate_analyzer.last_llm_response
            )
            log.info(
                "  >> SuccessRateAnalysis:\n"
                + json.dumps(success_analysis, ensure_ascii=False, indent=2, default=str)
            )
        except Exception as e:
            llm_outputs["success_rate_analysis"] = {"error": str(e)}
            log.warning(f"  Success rate analysis failed: {e}")
            success_analysis = {"comprehensive_report": f"Success rate analysis failed: {e}"}

        # Step 5: 生成报告
        log.step("Generating patentability report")
        report = self._build_report(
            proposed_cxsmiles=proposed_cxsmiles,
            tech_domain=tech_domain,
            novelty=novelty,
            prior_arts=prior_arts,
        )
        if self.reporter.last_llm_response is not None:
            llm_outputs["patentability_report"] = self.reporter.last_llm_response
        log.info(
            "  >> PatentabilityReport:\n"
            + json.dumps(report, ensure_ascii=False, indent=2, default=str)
        )

        return PatentabilityResult(
            proposed_structure=proposed,
            novelty_score=novelty.get("novelty_score", 0),
            prior_arts=prior_arts,
            risk_points=validation_notes + novelty.get("risk_points", []),
            suggestions=novelty.get("suggestions", []),
            success_analysis=success_analysis,
            llm_outputs=llm_outputs,
            report=report.get("detailed_analysis", ""),
        )
