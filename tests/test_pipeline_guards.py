from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.base import BaseAgent
from agents.claim_analyzer import ClaimAnalysis
from agents.llm_markush_extractor import LLMMarkushExtractorAgent
from agents.llm_substructure_matcher import LLMSubstructureMatcherAgent
from agents.markush_image_selector import MarkushImageSelection, MarkushImageSelectorAgent
from agents.r_group_aligner import RGroupAlignmentAgent
from agents.requirements_examiner import RequirementsExaminerAgent
from pipelines.infringement import InfringementPipeline
from pipelines.llm_infringement import LLMInfringementPipeline
from pipelines.patentability import PatentabilityPipeline
from schemas.types import Confidence, FusedMatchResult, MarkushStructure, MatchMethod, MatchResult, PatentDocument, PatentImage, RGroupAlignmentResult
from scripts.run_infringement_dataset import _resolve_main_markush_structure
from tools.markush_caption import inline_markush_to_rdkit_caption
from tools.markush_grapher import MarkushGrapherTool
from tools.llm_client import DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION, LLMClient
from tools.rdkit_matcher import RDKitMatcherTool


class DummyAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return "system"

    def build_user_prompt(self, **kwargs) -> str:
        return kwargs["message"]

    def parse_response(self, response: dict) -> dict:
        return response


class BaseAgentTests(unittest.TestCase):
    def test_run_passes_agent_max_tokens_to_llm(self) -> None:
        llm = Mock()
        llm.chat.return_value = {"ok": True}
        agent = DummyAgent(llm=llm, max_tokens=1234)

        result = agent.run(message="hello")

        self.assertEqual(result, {"ok": True})
        llm.chat.assert_called_once()
        self.assertEqual(llm.chat.call_args.kwargs["max_tokens"], 1234)


class LLMClientTests(unittest.TestCase):
    def test_applies_chinese_output_instruction_to_system_prompt(self) -> None:
        client = LLMClient.__new__(LLMClient)
        client.output_language_instruction = DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION.strip()

        prompt = client._apply_output_language_instruction("system")

        self.assertIn("简体中文", prompt)
        self.assertIn("合法 JSON", prompt)

    def test_output_language_instruction_is_idempotent(self) -> None:
        client = LLMClient.__new__(LLMClient)
        client.output_language_instruction = DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION.strip()

        prompt = client._apply_output_language_instruction("system")
        prompt = client._apply_output_language_instruction(prompt)

        self.assertEqual(prompt.count("输出语言要求："), 1)


class RequirementsExaminerTests(unittest.TestCase):
    def test_parse_response_reads_confidence(self) -> None:
        agent = RequirementsExaminerAgent(llm=Mock())

        parsed = agent.parse_response(
            {
                "is_protected": True,
                "confidence": "high",
                "reasoning": "ok",
                "r_group_analysis": {"R1": {"covered": True}},
            }
        )

        self.assertTrue(parsed.is_protected)
        self.assertEqual(parsed.confidence, Confidence.HIGH)

    def test_parse_response_falls_back_on_invalid_confidence(self) -> None:
        agent = RequirementsExaminerAgent(llm=Mock())

        parsed = agent.parse_response(
            {"is_protected": False, "confidence": "nonsense", "reasoning": "bad"}
        )

        self.assertEqual(parsed.confidence, Confidence.VERY_LOW)


class RGroupAlignmentAgentTests(unittest.TestCase):
    def test_parse_response_reads_confidence(self) -> None:
        agent = RGroupAlignmentAgent(llm=Mock())

        parsed = agent.parse_response(
            {
                "aligned_r_group_matching": {"X": "aryl", "R1": "C", "R2": "C"},
                "label_alignment": {"R1": {"claim_label": "X"}},
                "unresolved_labels": [],
                "reasoning": "ok",
                "confidence": "high",
            }
        )

        self.assertEqual(
            parsed.aligned_r_group_matching,
            {"X": "aryl", "R1": "C", "R2": "C"},
        )
        self.assertEqual(parsed.confidence, Confidence.HIGH)

    def test_parse_response_falls_back_on_invalid_confidence(self) -> None:
        agent = RGroupAlignmentAgent(llm=Mock())

        parsed = agent.parse_response({"confidence": "nonsense"})

        self.assertEqual(parsed.confidence, Confidence.VERY_LOW)


class LLMOnlyAgentTests(unittest.TestCase):
    def test_markush_image_selector_parse_response(self) -> None:
        agent = MarkushImageSelectorAgent(llm=Mock())

        parsed = agent.parse_response(
            {
                "is_markush": True,
                "is_main_markush": True,
                "score": 92,
                "image_role": "main_markush_formula",
                "reasoning": "Formula I with R groups",
            }
        )

        self.assertTrue(parsed.is_markush)
        self.assertTrue(parsed.is_main_markush)
        self.assertAlmostEqual(parsed.score, 0.92)
        self.assertEqual(parsed.image_role, "main_markush_formula")

    def test_markush_extractor_parse_response_accepts_textual_caption(self) -> None:
        agent = LLMMarkushExtractorAgent(llm=Mock())

        parsed = agent.parse_response(
            {
                "is_markush": True,
                "markush_caption": "Formula I: core with R1 = halogen",
                "cxsmiles": "",
                "substituent_table": {"R1": "halogen"},
                "score": 87,
            }
        )

        self.assertTrue(parsed.is_markush)
        self.assertEqual(parsed.caption, "Formula I: core with R1 = halogen")
        self.assertEqual(parsed.substituent_table, {"R1": "halogen"})
        self.assertAlmostEqual(parsed.score, 0.87)

    def test_llm_substructure_matcher_parse_response_returns_llm_method(self) -> None:
        agent = LLMSubstructureMatcherAgent(llm=Mock())

        parsed = agent.parse_response(
            {
                "is_match": True,
                "r_group_map": {"R1": "Cl"},
                "confidence": "moderate",
                "reasoning": "skeleton matches",
            }
        )

        self.assertTrue(parsed.is_match)
        self.assertEqual(parsed.method, MatchMethod.LLM)
        self.assertEqual(parsed.r_group_map, {"R1": "Cl"})
        self.assertIn("moderate", parsed.reasoning)


class MarkushCaptionTests(unittest.TestCase):
    def test_inline_caption_converts_to_rdkit_caption(self) -> None:
        caption = inline_markush_to_rdkit_caption("<r>R1</r>C")

        self.assertEqual(caption, "*C<sep><a>0:R1</a>")

    def test_rdkit_matcher_uses_inline_caption_normalization(self) -> None:
        result = RDKitMatcherTool().match("<r>R1</r>C", "CC")

        self.assertTrue(result.is_match)
        self.assertEqual(result.r_group_map, {"R1": "C"})


class InfringementPipelineTests(unittest.TestCase):
    def test_is_usable_markush_requires_markush_signal(self) -> None:
        pipeline = InfringementPipeline.__new__(InfringementPipeline)
        pipeline.min_markush_score = 0.5

        self.assertTrue(
            pipeline._is_usable_markush(
                MarkushStructure(
                    cxsmiles="",
                    substituent_table={},
                    caption="core<sep><a>0:R[1]</a>",
                    is_markush=False,
                    score=0.8,
                )
            )
        )
        self.assertFalse(
            pipeline._is_usable_markush(
                MarkushStructure(
                    cxsmiles="",
                    substituent_table={},
                    caption="plain caption",
                    is_markush=False,
                    score=1.0,
                )
            )
        )

    def test_final_confidence_comes_from_requirements_examiner(self) -> None:
        config = {
            "pipelines": {"infringement": {"use_markush_grapher": False, "use_rdkit": False}},
            "tools": {"markush_grapher": {}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }

        with patch("pipelines.infringement.PatentScraperTool") as scraper_cls, patch(
            "pipelines.infringement.LLMClient"
        ) as llm_cls:
            scraper_cls.return_value.fetch.return_value = PatentDocument(
                patent_id="US123",
                claims_text="claim text",
            )
            llm_cls.return_value = Mock()

            pipeline = InfringementPipeline(config)
            pipeline.claim_analyzer.run = Mock(
                return_value=ClaimAnalysis(
                    markush_claims=[
                        {"r_group_constraints": {"R1": "halogen"}},
                    ]
                )
            )
            pipeline.subs_matcher.run = Mock(
                return_value=FusedMatchResult(r_group_matching={"R1": "Cl"})
            )
            pipeline.r_group_aligner.run = Mock(
                return_value=RGroupAlignmentResult(
                    aligned_r_group_matching={"R1": "Cl"},
                    label_alignment={"R1": {"claim_label": "R1"}},
                    confidence=Confidence.HIGH,
                )
            )
            pipeline.req_examiner.run = Mock(
                return_value=type(
                    "ReqStub",
                    (),
                    {
                        "is_protected": True,
                        "confidence": Confidence.LOW,
                        "reasoning": "req confidence",
                        "r_group_analysis": {"R1": {"covered": True}},
                    },
                )()
            )
            pipeline.reporter.run = Mock(
                return_value={"confidence": "high", "detailed_analysis": "report text"}
            )

            result = pipeline.run("US123", "CC", markush_caption="core<sep><a>0:R[1]</a>")

        self.assertEqual(result.confidence, Confidence.LOW)
        self.assertEqual(result.report, "report text")

    def test_requirements_examiner_receives_claim_aligned_mapping(self) -> None:
        config = {
            "pipelines": {"infringement": {"use_markush_grapher": False, "use_rdkit": False}},
            "tools": {"markush_grapher": {}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }
        original_map = {
            "R1": "Nc1cc(C(=O)O)cc(C(=O)O)c1",
            "R2": "C",
            "R3": "C",
        }
        aligned_map = {
            "X": "Nc1cc(C(=O)O)cc(C(=O)O)c1",
            "R1": "C",
            "R2": "C",
        }
        label_alignment = {
            "R1": {"claim_label": "X"},
            "R2": {"claim_label": "R1"},
            "R3": {"claim_label": "R2"},
        }

        with patch("pipelines.infringement.PatentScraperTool") as scraper_cls, patch(
            "pipelines.infringement.LLMClient"
        ) as llm_cls:
            scraper_cls.return_value.fetch.return_value = PatentDocument(
                patent_id="US9655879",
                claims_text="R1 and R2 are alkyl; X is formula II.",
            )
            llm_cls.return_value = Mock()

            pipeline = InfringementPipeline(config)
            pipeline.claim_analyzer.run = Mock(
                return_value=ClaimAnalysis(
                    markush_claims=[
                        {
                            "r_group_constraints": {
                                "R1": "alkyl",
                                "R2": "alkyl",
                                "X": "formula II",
                            }
                        }
                    ]
                )
            )
            pipeline.subs_matcher.run = Mock(
                return_value=FusedMatchResult(r_group_matching=original_map)
            )
            pipeline.r_group_aligner.run = Mock(
                return_value=RGroupAlignmentResult(
                    aligned_r_group_matching=aligned_map,
                    label_alignment=label_alignment,
                    confidence=Confidence.HIGH,
                )
            )
            pipeline.req_examiner.run = Mock(
                return_value=type(
                    "ReqStub",
                    (),
                    {
                        "is_protected": True,
                        "confidence": Confidence.HIGH,
                        "reasoning": "aligned",
                        "r_group_analysis": {"X": {"covered": True}},
                    },
                )()
            )
            pipeline.reporter.run = Mock(
                return_value={"confidence": "high", "detailed_analysis": "report text"}
            )

            result = pipeline.run(
                "US9655879",
                "CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2F)s1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1",
                markush_caption="*C(=O)C(*)(*)CC1=CC=C(C(=O)OC2=CC=C(C(=N)N)C=C2F)S1<sep><a>0:R1</a><a>4:R2</a><a>5:R3</a>",
            )

        req_kwargs = pipeline.req_examiner.run.call_args.kwargs
        self.assertTrue(result.is_protected)
        self.assertEqual(req_kwargs["r_group_matching"], aligned_map)
        self.assertEqual(req_kwargs["original_r_group_matching"], original_map)
        self.assertEqual(req_kwargs["label_alignment"], label_alignment)
        self.assertEqual(result.fused_match.claim_aligned_r_group_matching, aligned_map)

    def test_claim_plain_smiles_does_not_override_usable_markush_caption(self) -> None:
        config = {
            "pipelines": {"infringement": {"use_markush_grapher": False, "use_rdkit": True}},
            "tools": {"markush_grapher": {}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }
        original_caption = "<r>R1</r>C"
        llm_plain_smiles = "c1cc(c(N*)=O)ccc1"

        with patch("pipelines.infringement.PatentScraperTool") as scraper_cls, patch(
            "pipelines.infringement.LLMClient"
        ) as llm_cls:
            scraper_cls.return_value.fetch.return_value = PatentDocument(
                patent_id="WO2020252229A2",
                claims_text="claim text",
            )
            llm_cls.return_value = Mock()

            pipeline = InfringementPipeline(config)
            pipeline.claim_analyzer.run = Mock(
                return_value=ClaimAnalysis(
                    markush_claims=[
                        {"r_group_constraints": {"R1": "alkyl"}},
                    ],
                    primary_markush_caption=llm_plain_smiles,
                )
            )
            pipeline.rdkit.match = Mock(
                return_value=MatchResult(
                    is_match=True,
                    r_group_map={"R1": "C"},
                    method=MatchMethod.RDKIT,
                    reasoning="matched",
                )
            )
            pipeline.subs_matcher.run = Mock(
                return_value=FusedMatchResult(r_group_matching={"R1": "C"})
            )
            pipeline.r_group_aligner.run = Mock(
                return_value=RGroupAlignmentResult(
                    aligned_r_group_matching={"R1": "C"},
                    label_alignment={"R1": {"claim_label": "R1"}},
                    confidence=Confidence.HIGH,
                )
            )
            pipeline.req_examiner.run = Mock(
                return_value=type(
                    "ReqStub",
                    (),
                    {
                        "is_protected": True,
                        "confidence": Confidence.HIGH,
                        "reasoning": "protected",
                        "r_group_analysis": {"R1": {"covered": True}},
                    },
                )()
            )
            pipeline.reporter.run = Mock(
                return_value={"confidence": "high", "detailed_analysis": "report text"}
            )

            result = pipeline.run(
                "WO2020252229A2",
                "CC",
                markush_caption=original_caption,
            )

        pipeline.rdkit.match.assert_called_once_with(original_caption, "CC")
        self.assertTrue(result.is_protected)
        self.assertEqual(
            pipeline.reporter.run.call_args.kwargs["analysis_data"]["markush_caption"],
            original_caption,
        )

    def test_alignment_failure_short_circuits_requirements_examiner(self) -> None:
        config = {
            "pipelines": {"infringement": {"use_markush_grapher": False, "use_rdkit": False}},
            "tools": {"markush_grapher": {}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }

        with patch("pipelines.infringement.PatentScraperTool") as scraper_cls, patch(
            "pipelines.infringement.LLMClient"
        ) as llm_cls:
            scraper_cls.return_value.fetch.return_value = PatentDocument(
                patent_id="US9655879",
                claims_text="R1 and R2 are alkyl; X is formula II.",
            )
            llm_cls.return_value = Mock()

            pipeline = InfringementPipeline(config)
            pipeline.claim_analyzer.run = Mock(
                return_value=ClaimAnalysis(
                    markush_claims=[
                        {
                            "r_group_constraints": {
                                "R1": "alkyl",
                                "R2": "alkyl",
                                "X": "formula II",
                            }
                        }
                    ]
                )
            )
            pipeline.subs_matcher.run = Mock(
                return_value=FusedMatchResult(
                    r_group_matching={
                        "R1": "Nc1cc(C(=O)O)cc(C(=O)O)c1",
                        "R2": "C",
                        "R3": "C",
                    }
                )
            )
            pipeline.r_group_aligner.run = Mock(
                return_value=RGroupAlignmentResult(
                    unresolved_labels=["R1", "R2", "R3"],
                    reasoning="cannot align",
                    confidence=Confidence.VERY_LOW,
                )
            )
            pipeline.req_examiner.run = Mock()
            pipeline.reporter.run = Mock()

            result = pipeline.run(
                "US9655879",
                "CC",
                markush_caption="*C(=O)C(*)(*)<sep><a>0:R1</a><a>4:R2</a><a>5:R3</a>",
            )

        self.assertFalse(result.is_protected)
        self.assertEqual(result.confidence, Confidence.VERY_LOW)
        self.assertIn("R-group label alignment failed", result.report)
        pipeline.req_examiner.run.assert_not_called()
        pipeline.reporter.run.assert_not_called()

    def test_empty_unverified_mapping_short_circuits_requirements_examiner(self) -> None:
        config = {
            "pipelines": {"infringement": {"use_markush_grapher": False, "use_rdkit": True}},
            "tools": {"markush_grapher": {}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }

        with patch("pipelines.infringement.PatentScraperTool") as scraper_cls, patch(
            "pipelines.infringement.LLMClient"
        ) as llm_cls:
            scraper_cls.return_value.fetch.return_value = PatentDocument(
                patent_id="US123",
                claims_text="claim text",
            )
            llm_cls.return_value = Mock()

            pipeline = InfringementPipeline(config)
            pipeline.claim_analyzer.run = Mock(
                return_value=type("ClaimAnalysisStub", (), {"primary_markush_caption": ""})()
            )
            pipeline.rdkit.match = Mock(
                return_value=MatchResult(
                    is_match=False,
                    r_group_map=None,
                    method=MatchMethod.RDKIT,
                    reasoning="no match",
                )
            )
            pipeline.subs_matcher.run = Mock(
                return_value=FusedMatchResult(r_group_matching={}, reasoning="no verified map")
            )
            pipeline.req_examiner.run = Mock()
            pipeline.reporter.run = Mock()

            result = pipeline.run("US123", "CC", markush_caption="<r>R1</r>N")

        self.assertFalse(result.is_protected)
        self.assertEqual(result.confidence, Confidence.VERY_LOW)
        pipeline.req_examiner.run.assert_not_called()
        pipeline.reporter.run.assert_not_called()


class LLMInfringementPipelineTests(unittest.TestCase):
    def test_applies_glm_profile_alias_to_llm_config(self) -> None:
        config = {
            "pipelines": {"llm_infringement": {"llm_model": "qwen-max"}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "qwen-max", "api_key_env": "OPENAI_API_KEY"},
            "llm_profiles": {
                "glm5.1": {
                    "provider": "openai",
                    "model": "glm-5.1",
                    "api_key_env": "ZAI_API_KEY",
                    "base_url": "https://example.test/v4",
                }
            },
        }

        with patch("pipelines.llm_infringement.PatentScraperTool"), patch(
            "pipelines.llm_infringement.LLMClient"
        ) as llm_cls:
            llm_cls.return_value = Mock()

            LLMInfringementPipeline(config, llm_model="glm5.1")

        used_config = llm_cls.call_args.args[0]
        self.assertEqual(used_config["llm"]["model"], "glm-5.1")
        self.assertEqual(used_config["llm"]["api_key_env"], "ZAI_API_KEY")

    def test_run_uses_llm_match_result_for_fusion(self) -> None:
        config = {
            "pipelines": {
                "llm_infringement": {},
                "markush_image_selection": {"enabled": True},
            },
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }

        with patch("pipelines.llm_infringement.PatentScraperTool") as scraper_cls, patch(
            "pipelines.llm_infringement.LLMClient"
        ) as llm_cls:
            scraper_cls.return_value.fetch.return_value = PatentDocument(
                patent_id="US123",
                claims_text="R1 is halogen.",
            )
            llm_cls.return_value = Mock()

            pipeline = LLMInfringementPipeline(config)
            pipeline.claim_analyzer.run = Mock(
                return_value=ClaimAnalysis(
                    markush_claims=[
                        {"r_group_constraints": {"R1": "halogen"}},
                    ]
                )
            )
            llm_match = MatchResult(
                is_match=True,
                r_group_map={"R1": "Cl"},
                method=MatchMethod.LLM,
                reasoning="matched by LLM",
            )
            pipeline.structure_matcher.run = Mock(return_value=llm_match)
            pipeline.subs_matcher.run = Mock(
                return_value=FusedMatchResult(r_group_matching={"R1": "Cl"})
            )
            pipeline.r_group_aligner.run = Mock(
                return_value=RGroupAlignmentResult(
                    aligned_r_group_matching={"R1": "Cl"},
                    label_alignment={"R1": {"claim_label": "R1"}},
                    confidence=Confidence.HIGH,
                )
            )
            pipeline.req_examiner.run = Mock(
                return_value=type(
                    "ReqStub",
                    (),
                    {
                        "is_protected": True,
                        "confidence": Confidence.HIGH,
                        "reasoning": "covered",
                        "r_group_analysis": {"R1": {"covered": True}},
                    },
                )()
            )
            pipeline.reporter.run = Mock(
                return_value={"confidence": "high", "detailed_analysis": "report text"}
            )

            result = pipeline.run(
                "US123",
                "CCl",
                markush_caption="Formula I: core with R1",
            )

        self.assertTrue(result.is_protected)
        self.assertEqual(result.fused_match.llm_result, llm_match)
        self.assertEqual(
            pipeline.subs_matcher.run.call_args.kwargs["llm_match_result"],
            llm_match,
        )


class InfringementDatasetRunnerTests(unittest.TestCase):
    def test_selected_image_empty_caption_retries_after_clearing_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first_image_path = Path(tmpdir) / "image_1.png"
            selected_image_path = Path(tmpdir) / "image_2.png"
            first_image_path.write_bytes(b"not-used")
            selected_image_path.write_bytes(b"not-used")

            scraper = Mock()
            scraper.fetch.return_value = PatentDocument(
                patent_id="US123",
                images=[
                    PatentImage(path=str(first_image_path)),
                    PatentImage(path=str(selected_image_path)),
                ],
            )
            selector = Mock()
            selector.select_main_markush_image.return_value = (
                MarkushImageSelection(
                    image_index=2,
                    image_path=str(selected_image_path),
                    is_markush=True,
                    is_main_markush=True,
                    score=0.9,
                ),
                [],
            )
            grapher = Mock()
            grapher.predict.side_effect = [
                MarkushStructure(cxsmiles="", substituent_table={}, caption=""),
                MarkushStructure(
                    cxsmiles="C*",
                    substituent_table={},
                    caption="<r>R1</r>C",
                    source_image_path=str(selected_image_path),
                ),
            ]

            structure, error, selection_record = _resolve_main_markush_structure(
                "US123",
                scraper,
                grapher,
                selector,
                target_smiles="CC",
                config={"pipelines": {"markush_image_selection": {"max_images": 5}}},
                caption_empty_retries=3,
            )

        self.assertIsNone(error)
        self.assertEqual(structure.caption, "<r>R1</r>C")
        self.assertEqual(selection_record["selected"]["image_index"], 2)
        grapher.clear_cache.assert_called_once_with(str(selected_image_path))


class GLMFirstImageDatasetRunnerTests(unittest.TestCase):
    @staticmethod
    def _glm_response(payload: dict) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(payload)),
                )
            ]
        )

    def test_select_main_markush_image_skips_non_main_images_until_main(self) -> None:
        from scripts.run_glm_first_image_infringement_dataset import (
            select_main_markush_image,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            patent_dir = Path(tmpdir) / "US123"
            patent_dir.mkdir()
            first_image_path = patent_dir / "image_1.png"
            selected_image_path = patent_dir / "image_2.png"
            first_image_path.write_bytes(b"not-used")
            selected_image_path.write_bytes(b"not-used")

            create = Mock(
                side_effect=[
                    self._glm_response(
                        {
                            "is_markush": True,
                            "is_main_markush": False,
                            "score": 0.95,
                            "image_role": "example",
                        }
                    ),
                    self._glm_response(
                        {
                            "is_markush": True,
                            "is_main_markush": True,
                            "score": 0.8,
                            "image_role": "main_markush",
                        }
                    ),
                ]
            )
            client = SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )

            with patch(
                "scripts.run_glm_first_image_infringement_dataset.OpenAI",
                return_value=client,
            ):
                image_path, selection = select_main_markush_image(
                    patent_id="US123",
                    smiles="CC",
                    patent_text="claim text",
                    cache_root=Path(tmpdir),
                    model="glm-5.1",
                    base_url="https://example.test/v1",
                    api_key="test-key",
                    temperature=0.0,
                    request_timeout=1.0,
                    max_images=5,
                    min_score=0.55,
                )

        self.assertEqual(image_path, selected_image_path)
        self.assertEqual(selection["selected"]["image_index"], 2)
        self.assertEqual(
            [item["image_index"] for item in selection["evaluations"]],
            [1, 2],
        )
        self.assertEqual(create.call_count, 2)

    def test_select_main_markush_image_does_not_fallback_to_non_main_markush(self) -> None:
        from scripts.run_glm_first_image_infringement_dataset import (
            select_main_markush_image,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            patent_dir = Path(tmpdir) / "US123"
            patent_dir.mkdir()
            for image_index in range(1, 3):
                (patent_dir / f"image_{image_index}.png").write_bytes(b"not-used")

            create = Mock(
                side_effect=[
                    self._glm_response(
                        {
                            "is_markush": True,
                            "is_main_markush": False,
                            "score": 0.95,
                        }
                    ),
                    self._glm_response(
                        {
                            "is_markush": True,
                            "is_main_markush": False,
                            "score": 0.9,
                        }
                    ),
                ]
            )
            client = SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )

            with patch(
                "scripts.run_glm_first_image_infringement_dataset.OpenAI",
                return_value=client,
            ):
                with self.assertRaisesRegex(RuntimeError, "No main Markush image"):
                    select_main_markush_image(
                        patent_id="US123",
                        smiles="CC",
                        patent_text="claim text",
                        cache_root=Path(tmpdir),
                        model="glm-5.1",
                        base_url="https://example.test/v1",
                        api_key="test-key",
                        temperature=0.0,
                        request_timeout=1.0,
                        max_images=5,
                        min_score=0.55,
                    )

        self.assertEqual(create.call_count, 2)


class PatentabilityPipelineTests(unittest.TestCase):
    def test_merge_prior_art_candidates_filters_invalid_and_dedupes(self) -> None:
        pipeline = PatentabilityPipeline.__new__(PatentabilityPipeline)
        pipeline.max_prior_arts = 10

        merged, notes = pipeline._merge_prior_art_candidates(
            suggested_ids=["us 123", "fake-id", "WO2020252229A2"],
            known_prior_art_ids=["US123", "  us123 "],
        )

        self.assertEqual(
            merged,
            [("US123", "user-supplied"), ("WO2020252229A2", "LLM-suggested")],
        )
        self.assertEqual(len(notes), 1)
        self.assertIn("fake-id", notes[0])

    def test_run_only_uses_verified_prior_arts(self) -> None:
        config = {
            "pipelines": {"patentability": {"max_prior_arts": 10}},
            "tools": {"markush_grapher": {"mode": "remote", "endpoint": "http://unused.test"}},
            "patent": {"cache_root": "cache/google_patent"},
            "llm": {"provider": "openai", "model": "dummy", "api_key_env": "OPENAI_API_KEY"},
        }

        with patch("pipelines.patentability.PatentScraperTool") as scraper_cls, patch(
            "pipelines.patentability.MarkushGrapherTool"
        ) as grapher_cls, patch("pipelines.patentability.LLMClient") as llm_cls:
            scraper = scraper_cls.return_value
            scraper.fetch.side_effect = [
                PatentDocument(patent_id="US123", images=[]),
                RuntimeError("not found"),
            ]
            grapher_cls.return_value.predict.return_value = MarkushStructure(
                cxsmiles="C*",
                substituent_table={},
            )
            llm_cls.return_value = Mock()

            pipeline = PatentabilityPipeline(config)
            pipeline.prior_art_searcher.run = Mock(
                return_value={"patent_ids": ["US123", "US404404404"], "reasoning": ""}
            )
            pipeline.novelty_analyzer.run = Mock(
                return_value={"novelty_score": 0.2, "risk_points": [], "suggestions": []}
            )
            pipeline.reporter.run = Mock(return_value={"detailed_analysis": "done"})

            result = pipeline.run(proposed_cxsmiles="C*")

        self.assertEqual([pa.patent_id for pa in result.prior_arts], ["US123"])
        self.assertTrue(any("US404404404" in note for note in result.risk_points))


class MarkushGrapherRemoteTests(unittest.TestCase):
    def test_remote_batch_preserves_order_and_skips_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "image.png"
            Image.new("RGB", (4, 4), color="white").save(image_path)
            missing_path = Path(tmpdir) / "missing.png"

            tool = MarkushGrapherTool(
                {
                    "tools": {
                        "markush_grapher": {
                            "mode": "remote",
                            "endpoint": "http://example.test/predict",
                        }
                    }
                }
            )

            response = Mock()
            response.json.return_value = {
                "data": {
                    "smi": ["C*"],
                    "caption": ["C*<sep><a>0:R[1]</a>"],
                    "score": [0.9],
                    "markush": [True],
                }
            }
            response.raise_for_status.return_value = None

            with patch("tools.markush_grapher.requests.post", return_value=response) as post_mock:
                results = tool.predict_batch([str(image_path), str(missing_path)])

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].is_markush)
        self.assertEqual(results[1].caption, "")
        post_mock.assert_called_once()

    def test_remote_batch_rejects_length_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "image.png"
            Image.new("RGB", (4, 4), color="white").save(image_path)

            tool = MarkushGrapherTool(
                {
                    "tools": {
                        "markush_grapher": {
                            "mode": "remote",
                            "endpoint": "http://example.test/predict",
                        }
                    }
                }
            )

            response = Mock()
            response.json.return_value = {
                "data": {
                    "smi": ["C*", "N*"],
                    "caption": ["c1", "c2"],
                    "score": [0.9, 0.8],
                    "markush": [True, False],
                }
            }
            response.raise_for_status.return_value = None

            with patch("tools.markush_grapher.requests.post", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "length mismatch"):
                    tool.predict_batch([str(image_path)])


class MarkushGrapherLocalTests(unittest.TestCase):
    def test_inline_r_caption_is_treated_as_markush(self) -> None:
        inline_result = MarkushGrapherTool._structure_from_result(
            "image.png",
            {
                "caption": "<r>R1</r>C(=O)N",
                "smi": "<r>R1</r>C(=O)N",
                "is_markush": False,
                "score": 1.0,
            },
        )
        plain_result = MarkushGrapherTool._structure_from_result(
            "image.png",
            {
                "caption": "O=C1CCCN1",
                "smi": "O=C1CCCN1",
                "is_markush": False,
                "score": 1.0,
            },
        )

        self.assertTrue(inline_result.is_markush)
        self.assertFalse(plain_result.is_markush)

    def test_local_batch_retries_on_cpu_after_cuda_oom(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "image.png"
            model_dir = Path(tmpdir) / "model"
            ocr_dir = Path(tmpdir) / "ocr"
            Image.new("RGB", (4, 4), color="white").save(image_path)
            model_dir.mkdir()
            ocr_dir.mkdir()

            tool = MarkushGrapherTool(
                {
                    "tools": {
                        "markush_grapher": {
                            "mode": "local",
                            "python_bin": sys.executable,
                            "model_dir": str(model_dir),
                            "ocr_model_dir": str(ocr_dir),
                        }
                    }
                }
            )

            oom_proc = Mock(
                returncode=1,
                stdout="",
                stderr="RuntimeError: CUDA error: out of memory",
            )
            ok_proc = Mock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "path": str(image_path),
                            "caption": "C*<sep><a>0:R[1]</a>",
                            "smi": "C*",
                            "is_markush": True,
                            "score": 0.9,
                        }
                    ]
                ),
                stderr="",
            )

            with patch(
                "tools.markush_grapher.subprocess.run",
                side_effect=[oom_proc, ok_proc],
            ) as run_mock:
                results = tool.predict_batch([str(image_path)])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].is_markush)
        self.assertEqual(run_mock.call_count, 2)
        self.assertNotIn("CUDA_VISIBLE_DEVICES", run_mock.call_args_list[0].kwargs["env"])
        self.assertEqual(run_mock.call_args_list[1].kwargs["env"]["CUDA_VISIBLE_DEVICES"], "")


if __name__ == "__main__":
    unittest.main()
