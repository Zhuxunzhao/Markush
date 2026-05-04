"""Multi-Agent for Markush — CLI 入口

Usage:
  # 专利侵权分析
  python main.py infringement --patent_id US10676478 --smiles "CC(=O)Oc1ccccc1C(=O)O"

  # 专利侵权分析（直接提供 Markush caption）
  python main.py infringement --patent_id US10676478 --smiles "..." --caption "*C1CCON1..."

  # 可专利性分析
  python main.py patentability --cxsmiles "*C1CC(*)CC1<sep>..." --domain "kinase inhibitors"

  # 可专利性分析（从图片）
  python main.py patentability --image structure.png --domain "kinase inhibitors"
"""

import argparse
import dataclasses
import json
import os
import sys
from typing import Any

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.llm_client import load_config


def _print_summary(lines: list[tuple[str, Any]], report: str | None = None) -> None:
    print("\n" + "=" * 60)
    for label, value in lines:
        print(f"{label:<11} {value}")
    print("=" * 60)
    if report:
        print(report)


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(dataclasses.asdict(value))
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _write_json(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nResult saved to {path}")


def _serialize_infringement_result(result) -> dict[str, Any]:
    return {
        "patent_id": result.patent_id,
        "target_smiles": result.target_smiles,
        "is_protected": result.is_protected,
        "confidence": result.confidence.value,
        "markush_structure": _to_jsonable(result.markush_structure),
        "fused_match": _to_jsonable(result.fused_match),
        "requirements": _to_jsonable(result.requirements),
        "llm_outputs": result.llm_outputs,
        "report": result.report,
    }


def _serialize_patentability_result(result) -> dict[str, Any]:
    return {
        "proposed_structure": _to_jsonable(result.proposed_structure),
        "novelty_score": result.novelty_score,
        "prior_arts": [pa.patent_id for pa in result.prior_arts],
        "risk_points": result.risk_points,
        "suggestions": result.suggestions,
        "success_analysis": result.success_analysis,
        "llm_outputs": result.llm_outputs,
        "report": result.report,
    }


def cmd_infringement(args, config):
    from pipelines.infringement import InfringementPipeline

    pipeline = InfringementPipeline(config)
    result = pipeline.run(
        patent_id=args.patent_id,
        target_smiles=args.smiles,
        markush_caption=args.caption,
    )

    _print_summary(
        [
            ("Patent:", result.patent_id),
            ("Molecule:", result.target_smiles),
            ("Protected:", result.is_protected),
            ("Confidence:", result.confidence.value),
        ],
        report=result.report,
    )

    # Always save result (default: result.json)
    output_path = args.output or "result.json"
    _write_json(output_path, _serialize_infringement_result(result))


def cmd_llm_infringement(args, config):
    from pipelines.llm_infringement import LLMInfringementPipeline

    pipeline = LLMInfringementPipeline(
        config,
        llm_model=args.llm_model,
        llm_base_url=args.llm_base_url,
        llm_api_key_env=args.llm_api_key_env,
    )
    result = pipeline.run(
        patent_id=args.patent_id,
        target_smiles=args.smiles,
        markush_caption=args.caption,
    )

    _print_summary(
        [
            ("Patent:", result.patent_id),
            ("Molecule:", result.target_smiles),
            ("Protected:", result.is_protected),
            ("Confidence:", result.confidence.value),
            ("Workflow:", "llm-only"),
        ],
        report=result.report,
    )

    output_path = args.output or "result.json"
    _write_json(output_path, _serialize_infringement_result(result))


def cmd_patentability(args, config):
    from pipelines.patentability import PatentabilityPipeline

    pipeline = PatentabilityPipeline(config)

    known_ids = args.prior_arts.split(",") if args.prior_arts else None

    result = pipeline.run(
        proposed_cxsmiles=args.cxsmiles,
        proposed_image_path=args.image,
        tech_domain=args.domain or "",
        known_prior_art_ids=known_ids,
    )

    _print_summary(
        [
            ("Novelty Score:", f"{result.novelty_score:.2f}"),
            ("Prior Arts:", len(result.prior_arts)),
            ("Risk Points:", len(result.risk_points)),
        ],
        report=result.report,
    )

    output_path = args.output or "result.json"
    _write_json(output_path, _serialize_patentability_result(result))


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent for Markush — 专利侵权分析 & 可专利性评估"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="配置文件路径"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # --- infringement ---
    p_inf = subparsers.add_parser("infringement", help="专利侵权分析")
    p_inf.add_argument("--patent_id", required=True, help="专利号 (e.g. US10676478)")
    p_inf.add_argument("--smiles", required=True, help="目标分子 SMILES")
    p_inf.add_argument("--caption", default=None, help="直接提供 Markush caption，跳过图片识别")
    p_inf.add_argument("--output", "-o", default=None, help="结果输出 JSON 路径")

    # --- llm-only infringement ---
    p_llm_inf = subparsers.add_parser(
        "llm-infringement",
        aliases=["infringement-llm"],
        help="LLM-only 专利侵权分析（不用 MarkushGrapher/RDKit）",
    )
    p_llm_inf.add_argument("--patent_id", required=True, help="专利号 (e.g. US10676478)")
    p_llm_inf.add_argument("--smiles", required=True, help="目标分子 SMILES")
    p_llm_inf.add_argument("--caption", default=None, help="直接提供 Markush caption/描述，跳过 LLM 图片识别")
    p_llm_inf.add_argument("--llm-model", default=None, help="覆盖 LLM 型号/配置档，例如 glm5.1 或 qwen-max")
    p_llm_inf.add_argument("--llm-base-url", default=None, help="覆盖 LLM OpenAI-compatible base_url")
    p_llm_inf.add_argument("--llm-api-key-env", default=None, help="覆盖读取 API key 的环境变量名")
    p_llm_inf.add_argument("--output", "-o", default=None, help="结果输出 JSON 路径")

    # --- patentability ---
    p_pat = subparsers.add_parser("patentability", help="专利申请成功率分析")
    group = p_pat.add_mutually_exclusive_group(required=True)
    group.add_argument("--cxsmiles", help="拟申请的 CXSMILES")
    group.add_argument("--image", help="拟申请结构的图片路径")
    p_pat.add_argument("--domain", default="", help="技术领域描述")
    p_pat.add_argument("--prior_arts", default=None, help="已知相关专利号，逗号分隔")
    p_pat.add_argument("--output", "-o", default=None, help="结果输出 JSON 路径")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), args.config
    )
    config = load_config(config_path)

    commands = {
        "infringement": cmd_infringement,
        "llm-infringement": cmd_llm_infringement,
        "infringement-llm": cmd_llm_infringement,
        "patentability": cmd_patentability,
    }
    commands[args.command](args, config)


if __name__ == "__main__":
    main()
