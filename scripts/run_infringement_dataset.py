#!/usr/bin/env python3
"""Run infringement workflow in batch using a prepared dataset.

Key behavior:
- Load records from data/molpatent-240.infringement_input.json by default.
- If record caption is missing, only the first patent image is sent to
  MarkushGrapher. Empty captions are retried up to --caption-empty-retries.
- Process records concurrently (--workers, default 3).
- Persist progress after every completed record to the JSON output and a JSONL file.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipelines.infringement import InfringementPipeline
from pipelines.patentability import PatentabilityPipeline
from tools.llm_client import load_config
from tools.markush_caption import normalize_markush_caption
from tools.markush_grapher import MarkushGrapherTool
from tools.patent_scraper import PatentScraperTool
from schemas.types import MarkushStructure


_WORKER_STATE = threading.local()


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(dataclasses.asdict(value))
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _serialize_infringement_result(result) -> dict[str, Any]:
    return {
        "patent_id": result.patent_id,
        "target_smiles": result.target_smiles,
        "is_protected": result.is_protected,
        "confidence": result.confidence.value,
        "markush_structure": _to_jsonable(result.markush_structure),
        "fused_match": _to_jsonable(result.fused_match),
        "requirements": _to_jsonable(result.requirements),
        "llm_outputs": _to_jsonable(result.llm_outputs),
        "report": result.report,
    }


def _serialize_patentability_result(result) -> dict[str, Any]:
    return {
        "proposed_structure": _to_jsonable(result.proposed_structure),
        "novelty_score": result.novelty_score,
        "prior_arts": _to_jsonable(result.prior_arts),
        "risk_points": result.risk_points,
        "suggestions": result.suggestions,
        "success_analysis": _to_jsonable(result.success_analysis),
        "llm_outputs": _to_jsonable(result.llm_outputs),
        "report": result.report,
    }


def _load_records(input_path: Path) -> list[dict[str, Any]]:
    with input_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    raise ValueError("Input must be a JSON array, or an object containing a records array")


def _jsonl_path_for(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_suffix(".jsonl")
    return output_path.with_name(f"{output_path.name}.jsonl")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def _get_worker_tools(
    config: dict,
) -> tuple[InfringementPipeline, PatentabilityPipeline, PatentScraperTool, MarkushGrapherTool]:
    tools = getattr(_WORKER_STATE, "tools", None)
    if tools is None:
        tools = (
            InfringementPipeline(config),
            PatentabilityPipeline(config),
            PatentScraperTool(config),
            MarkushGrapherTool(config),
        )
        _WORKER_STATE.tools = tools
    return tools


def _resolve_first_image_markush_structure(
    patent_id: str,
    scraper: PatentScraperTool,
    grapher: MarkushGrapherTool,
    *,
    caption_empty_retries: int = 3,
) -> tuple[MarkushStructure | None, str | None]:
    try:
        patent = scraper.fetch(patent_id)
    except Exception as e:
        return None, f"failed to fetch patent: {e}"

    if not patent.images:
        return None, "no images found in patent"

    first_image_path = patent.images[0].path
    if not first_image_path or not os.path.exists(first_image_path):
        return None, "first image path missing on disk"

    max_attempts = max(1, caption_empty_retries)
    last_structure: MarkushStructure | None = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            grapher.clear_cache(first_image_path)
        try:
            structure = grapher.predict(first_image_path)
        except Exception as e:
            return None, f"markushgrapher failed on first image attempt {attempt}: {e}"

        last_structure = structure
        if (structure.caption or "").strip():
            return structure, None

    return (
        last_structure,
        f"first image produced empty caption after {max_attempts} attempt(s)",
    )


def _process_record(
    idx: int,
    total: int,
    record: dict[str, Any],
    config: dict,
    caption_empty_retries: int,
) -> dict[str, Any]:
    patent_id = str(record.get("patent_id", "")).strip()
    smiles = str(record.get("smiles") or record.get("target_smiles") or "").strip()
    provided_caption = (record.get("caption") or "").strip()

    stats = {
        "ok": 0,
        "error": 0,
        "patentability_ok": 0,
        "patentability_error": 0,
        "caption_from_first_image": 0,
        "caption_from_dataset": 0,
    }

    if not patent_id or not smiles:
        stats["error"] = 1
        output_record = {
            "index": idx,
            "input": record,
            "status": "error",
            "error": "missing patent_id or smiles",
        }
        return {
            "record": output_record,
            "stats": stats,
            "message": f"[{idx}/{total}] {patent_id or '<missing patent_id>'}: ERROR (missing patent_id or smiles)",
        }

    pipeline, patentability_pipeline, scraper, grapher = _get_worker_tools(config)

    caption = provided_caption or None
    markush_structure = None
    caption_source = "dataset" if caption else "first_image"
    markush_image_path = None
    if caption_source == "dataset":
        stats["caption_from_dataset"] = 1

    if caption is None:
        markush_structure, caption_error = _resolve_first_image_markush_structure(
            patent_id=patent_id,
            scraper=scraper,
            grapher=grapher,
            caption_empty_retries=caption_empty_retries,
        )
        if markush_structure is None:
            stats["error"] = 1
            output_record = {
                "index": idx,
                "input": {
                    "patent_id": patent_id,
                    "smiles": smiles,
                    "source_index": record.get("source_index"),
                },
                "caption_source": caption_source,
                "markush_image_path": markush_image_path,
                "status": "error",
                "error": caption_error,
            }
            return {
                "record": output_record,
                "stats": stats,
                "message": f"[{idx}/{total}] {patent_id}: ERROR ({caption_error})",
            }
        caption = markush_structure.caption
        markush_image_path = markush_structure.source_image_path
        if caption_error:
            stats["error"] = 1
            output_record = {
                "index": idx,
                "input": {
                    "patent_id": patent_id,
                    "smiles": smiles,
                    "source_index": record.get("source_index"),
                },
                "caption_source": caption_source,
                "markush_image_path": markush_image_path,
                "status": "error",
                "error": caption_error,
            }
            return {
                "record": output_record,
                "stats": stats,
                "message": f"[{idx}/{total}] {patent_id}: ERROR ({caption_error})",
            }
        stats["caption_from_first_image"] = 1

    try:
        result = pipeline.run(
            patent_id=patent_id,
            target_smiles=smiles,
            markush_caption=caption,
            markush_structure=markush_structure,
        )
        patentability_record: dict[str, Any]
        try:
            patentability_result = patentability_pipeline.run(
                proposed_cxsmiles=smiles,
                tech_domain=str(record.get("tech_domain") or "chemical compounds"),
                known_prior_art_ids=[patent_id],
                verify_prior_art=False,
            )
            stats["patentability_ok"] = 1
            patentability_record = {
                "status": "ok",
                "result": _serialize_patentability_result(patentability_result),
            }
        except Exception as e:
            stats["patentability_error"] = 1
            patentability_record = {
                "status": "error",
                "error": str(e),
            }

        stats["ok"] = 1
        output_record = {
            "index": idx,
            "input": {
                "patent_id": patent_id,
                "smiles": smiles,
                "source_index": record.get("source_index"),
                "expected_is_protected": record.get("expected_is_protected"),
                "selection_type": record.get("selection_type"),
            },
            "caption_source": caption_source,
            "markush_image_path": markush_image_path,
            "normalized_markush_caption": normalize_markush_caption(caption or ""),
            "status": "ok",
            "result": _serialize_infringement_result(result),
            "patentability": patentability_record,
        }
        patentability_suffix = (
            "patentability=OK"
            if patentability_record["status"] == "ok"
            else "patentability=ERROR"
        )
        return {
            "record": output_record,
            "stats": stats,
            "message": f"[{idx}/{total}] {patent_id}: OK ({patentability_suffix})",
        }
    except Exception as e:
        stats["error"] = 1
        output_record = {
            "index": idx,
            "input": {
                "patent_id": patent_id,
                "smiles": smiles,
                "source_index": record.get("source_index"),
            },
            "caption_source": caption_source,
            "markush_image_path": markush_image_path,
            "status": "error",
            "error": str(e),
        }
        return {
            "record": output_record,
            "stats": stats,
            "message": f"[{idx}/{total}] {patent_id}: ERROR ({e})",
        }


def _build_output_payload(
    input_path: Path,
    output_path: Path,
    summary: dict[str, Any],
    output_records: list[dict[str, Any] | None],
) -> dict[str, Any]:
    return {
        "input": str(input_path),
        "output": str(output_path),
        "summary": summary,
        "records": [record for record in output_records if record is not None],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run infringement workflow with dataset input")
    parser.add_argument(
        "--input",
        default="data/molpatent-240.infringement_input.json",
        help="Dataset JSON path",
    )
    parser.add_argument(
        "--output",
        default="outputs/results/molpatent-240/legacy/molpatent-240.infringement_results.first_image_retry.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config file path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only run first N records (0 means all)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of records to process concurrently",
    )
    parser.add_argument(
        "--caption-empty-retries",
        type=int,
        default=3,
        help="Retry first-image MarkushGrapher recognition when caption is empty",
    )
    args = parser.parse_args()

    input_path = (ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)

    config = load_config(str(config_path))
    records = _load_records(input_path)
    if args.limit > 0:
        records = records[: args.limit]

    workers = max(1, args.workers)
    total = len(records)
    output_records: list[dict[str, Any] | None] = [None] * total

    summary = {
        "total": total,
        "completed": 0,
        "ok": 0,
        "error": 0,
        "patentability_ok": 0,
        "patentability_error": 0,
        "caption_from_first_image": 0,
        "caption_from_dataset": 0,
        "workers": workers,
        "caption_empty_retries": max(1, args.caption_empty_retries),
    }
    jsonl_path = _jsonl_path_for(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text("", encoding="utf-8")
    _write_json_atomic(
        output_path,
        _build_output_payload(input_path, output_path, summary, output_records),
    )

    print(f"Running {total} record(s) with workers={workers}")
    print(f"Incremental JSON: {output_path}")
    print(f"Per-record JSONL: {jsonl_path}")

    with ThreadPoolExecutor(max_workers=workers) as executor, jsonl_path.open(
        "a", encoding="utf-8"
    ) as jsonl_file:
        futures = {
            executor.submit(
                _process_record,
                idx,
                total,
                record,
                config,
                max(1, args.caption_empty_retries),
            ): idx
            for idx, record in enumerate(records, start=1)
        }

        for future in as_completed(futures):
            idx = futures[future]
            try:
                item = future.result()
            except Exception as e:
                item = {
                    "record": {
                        "index": idx,
                        "input": records[idx - 1],
                        "status": "error",
                        "error": f"worker failed: {e}",
                    },
                    "stats": {
                        "ok": 0,
                        "error": 1,
                        "patentability_ok": 0,
                        "patentability_error": 0,
                        "caption_from_first_image": 0,
                        "caption_from_dataset": 0,
                    },
                    "message": f"[{idx}/{total}] ERROR (worker failed: {e})",
                }

            output_record = item["record"]
            output_records[idx - 1] = output_record
            stats = item["stats"]
            summary["completed"] += 1
            summary["ok"] += stats["ok"]
            summary["error"] += stats["error"]
            summary["patentability_ok"] += stats.get("patentability_ok", 0)
            summary["patentability_error"] += stats.get("patentability_error", 0)
            summary["caption_from_first_image"] += stats["caption_from_first_image"]
            summary["caption_from_dataset"] += stats["caption_from_dataset"]

            jsonl_file.write(json.dumps(output_record, ensure_ascii=False) + "\n")
            jsonl_file.flush()
            os.fsync(jsonl_file.fileno())
            _write_json_atomic(
                output_path,
                _build_output_payload(input_path, output_path, summary, output_records),
            )
            print(item["message"], flush=True)

    print("\nDone.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved result to: {output_path}")
    print(f"Saved per-record JSONL to: {jsonl_path}")


if __name__ == "__main__":
    main()
