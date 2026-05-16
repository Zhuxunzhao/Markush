#!/usr/bin/env python3
"""Run the LLM-only infringement workflow on a prepared dataset.

This batch runner deliberately uses the LangGraph-backed LLM-only infringement
pipeline instead of the legacy MarkushGrapher/RDKit infringement pipeline.
Progress is persisted after each completed record to one JSON file; no JSONL
sidecar is produced.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipelines.langgraph_llm_infringement import (  # noqa: E402
    LangGraphLLMInfringementPipeline as LLMInfringementPipeline,
)
from pipelines.llm_infringement import _config_with_llm_overrides  # noqa: E402
from tools.llm_client import LLMClient, load_config  # noqa: E402


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


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_records(input_path: Path) -> list[dict[str, Any]]:
    with input_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    raise ValueError("Input must be a JSON array, or an object containing a records array")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    tmp_path.replace(path)


def _existing_records(output_path: Path) -> dict[int, dict[str, Any]]:
    if not output_path.exists():
        return {}
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = payload.get("records", []) if isinstance(payload, dict) else []
    existing: dict[int, dict[str, Any]] = {}
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("index"), int):
            existing[int(record["index"])] = record
    return existing


def _collect_llm_errors(value: Any, *, path: str = "llm_outputs", limit: int = 8) -> list[str]:
    errors: list[str] = []

    def visit(item: Any, current_path: str) -> None:
        if len(errors) >= limit:
            return
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{current_path}.{key}"
                if key == "error" and child:
                    errors.append(f"{child_path}: {child}")
                    if len(errors) >= limit:
                        return
                visit(child, child_path)
        elif isinstance(item, list):
            for idx, child in enumerate(item):
                visit(child, f"{current_path}[{idx}]")
                if len(errors) >= limit:
                    return

    visit(value, path)
    return errors


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_worker_pipeline(
    config: dict[str, Any],
    *,
    llm_model: str | None,
    llm_base_url: str | None,
    llm_api_key_env: str | None,
    generate_report: bool,
) -> LLMInfringementPipeline:
    key = (llm_model or "", llm_base_url or "", llm_api_key_env or "", generate_report)
    cached = getattr(_WORKER_STATE, "pipeline", None)
    cached_key = getattr(_WORKER_STATE, "pipeline_key", None)
    if cached is None or cached_key != key:
        cached = LLMInfringementPipeline(
            config,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key_env=llm_api_key_env,
            generate_report=generate_report,
        )
        _WORKER_STATE.pipeline = cached
        _WORKER_STATE.pipeline_key = key
    return cached


def _preflight_llm(
    config: dict[str, Any],
    *,
    llm_model: str | None,
    llm_base_url: str | None,
    llm_api_key_env: str | None,
    generate_report: bool,
) -> dict[str, Any]:
    resolved = _config_with_llm_overrides(
        config,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_key_env=llm_api_key_env,
    )
    llm = LLMClient(resolved)
    response = llm.chat(
        system_prompt="Return a tiny JSON health check.",
        user_prompt='Return exactly {"ok": true}.',
        max_tokens=32,
        max_retries=1,
    )
    return {
        "status": "ok",
        "model": resolved.get("llm", {}).get("model"),
        "base_url": resolved.get("llm", {}).get("base_url"),
        "api_key_env": resolved.get("llm", {}).get("api_key_env"),
        "response": _to_jsonable(response),
    }


def _process_record(
    idx: int,
    total: int,
    record: dict[str, Any],
    config: dict[str, Any],
    *,
    llm_model: str | None,
    llm_base_url: str | None,
    llm_api_key_env: str | None,
    generate_report: bool,
    fail_on_llm_errors: bool,
) -> dict[str, Any]:
    patent_id = str(record.get("patent_id", "")).strip()
    smiles = str(record.get("smiles") or record.get("target_smiles") or "").strip()
    caption = (record.get("caption") or "").strip() or None

    stats = {"ok": 0, "error": 0}
    if not patent_id or not smiles:
        stats["error"] = 1
        return {
            "record": {
                "index": idx,
                "input": record,
                "status": "error",
                "error": "missing patent_id or smiles",
                "finished_at": _utc_now(),
            },
            "stats": stats,
            "message": f"[{idx}/{total}] {patent_id or '<missing patent_id>'}: ERROR (missing patent_id or smiles)",
        }

    try:
        pipeline = _get_worker_pipeline(
            config,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key_env=llm_api_key_env,
            generate_report=generate_report,
        )
        result = pipeline.run(
            patent_id=patent_id,
            target_smiles=smiles,
            markush_caption=caption,
        )
        serialized_result = _serialize_infringement_result(result)
        llm_errors = (
            _collect_llm_errors(serialized_result.get("llm_outputs", {}))
            if fail_on_llm_errors
            else []
        )
        if llm_errors:
            stats["error"] = 1
            return {
                "record": {
                    "index": idx,
                    "input": {
                        "patent_id": patent_id,
                        "smiles": smiles,
                        "source_index": record.get("source_index"),
                        "expected_is_protected": record.get("expected_is_protected"),
                        "selection_type": record.get("selection_type"),
                        "caption_provided": bool(caption),
                    },
                    "status": "error",
                    "error": "LLM error(s) occurred: " + "; ".join(llm_errors),
                    "result": serialized_result,
                    "finished_at": _utc_now(),
                },
                "stats": stats,
                "message": f"[{idx}/{total}] {patent_id}: ERROR (LLM error(s) occurred)",
            }
        stats["ok"] = 1
        return {
            "record": {
                "index": idx,
                "input": {
                    "patent_id": patent_id,
                    "smiles": smiles,
                    "source_index": record.get("source_index"),
                    "expected_is_protected": record.get("expected_is_protected"),
                    "selection_type": record.get("selection_type"),
                    "caption_provided": bool(caption),
                },
                "status": "ok",
                "result": serialized_result,
                "finished_at": _utc_now(),
            },
            "stats": stats,
            "message": f"[{idx}/{total}] {patent_id}: OK protected={result.is_protected} confidence={result.confidence.value}",
        }
    except Exception as e:
        stats["error"] = 1
        return {
            "record": {
                "index": idx,
                "input": {
                    "patent_id": patent_id,
                    "smiles": smiles,
                    "source_index": record.get("source_index"),
                    "expected_is_protected": record.get("expected_is_protected"),
                    "selection_type": record.get("selection_type"),
                    "caption_provided": bool(caption),
                },
                "status": "error",
                "error": str(e),
                "finished_at": _utc_now(),
            },
            "stats": stats,
            "message": f"[{idx}/{total}] {patent_id}: ERROR ({e})",
        }


def _build_output_payload(
    *,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="data/molpatent-240.infringement_input.json",
        help="Dataset JSON path",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON path",
    )
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--llm-model", default=None, help="LLM model/profile, e.g. glm5.1 or qwen-max")
    parser.add_argument("--llm-base-url", default=None, help="Override OpenAI-compatible base URL")
    parser.add_argument("--llm-api-key-env", default=None, help="Override API-key environment variable name")
    parser.add_argument("--limit", type=int, default=0, help="Run first N records only; 0 means all")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent records")
    parser.add_argument("--no-resume", action="store_true", help="Do not reuse completed records in output JSON")
    parser.add_argument("--no-preflight", action="store_true", help="Skip the one-call LLM auth/model check")
    parser.add_argument("--skip-report", action="store_true", help="Skip final narrative report generation")
    parser.add_argument(
        "--fail-on-record-errors",
        action="store_true",
        help="Exit with status 1 if any input record finishes with status=error",
    )
    parser.add_argument(
        "--fail-on-llm-errors",
        action="store_true",
        help="Treat captured LLM sub-call errors as record errors instead of silent very_low fallbacks",
    )
    args = parser.parse_args()

    _load_dotenv(ROOT / ".env")

    input_path = (ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)

    config = load_config(str(config_path))
    records = _load_records(input_path)
    if args.limit > 0:
        records = records[: args.limit]

    total = len(records)
    workers = max(1, args.workers)
    existing = {} if args.no_resume else _existing_records(output_path)
    output_records: list[dict[str, Any] | None] = [
        existing.get(idx) for idx in range(1, total + 1)
    ]

    summary = {
        "workflow": "llm-only-infringement",
        "input_total": total,
        "completed": sum(1 for record in output_records if record is not None),
        "ok": sum(1 for record in output_records if record and record.get("status") == "ok"),
        "error": sum(1 for record in output_records if record and record.get("status") == "error"),
        "workers": workers,
        "llm_model": args.llm_model,
        "llm_base_url": args.llm_base_url,
        "llm_api_key_env": args.llm_api_key_env,
        "generate_report": not args.skip_report,
        "fail_on_llm_errors": args.fail_on_llm_errors,
        "started_at": _utc_now(),
    }

    if not args.no_preflight:
        print("Running LLM preflight...", flush=True)
        summary["preflight"] = _preflight_llm(
            config,
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            llm_api_key_env=args.llm_api_key_env,
            generate_report=not args.skip_report,
        )

    _write_json_atomic(
        output_path,
        _build_output_payload(
            input_path=input_path,
            output_path=output_path,
            summary=summary,
            output_records=output_records,
        ),
    )

    pending = [
        (idx, record)
        for idx, record in enumerate(records, start=1)
        if output_records[idx - 1] is None
    ]
    print(f"Running {len(pending)} pending record(s) / {total} total with workers={workers}", flush=True)
    print(f"Incremental JSON: {output_path}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _process_record,
                idx,
                total,
                record,
                config,
                llm_model=args.llm_model,
                llm_base_url=args.llm_base_url,
                llm_api_key_env=args.llm_api_key_env,
                generate_report=not args.skip_report,
                fail_on_llm_errors=args.fail_on_llm_errors,
            ): idx
            for idx, record in pending
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
                        "finished_at": _utc_now(),
                    },
                    "stats": {"ok": 0, "error": 1},
                    "message": f"[{idx}/{total}] ERROR (worker failed: {e})",
                }

            output_records[idx - 1] = item["record"]
            stats = item["stats"]
            summary["completed"] += 1
            summary["ok"] += stats["ok"]
            summary["error"] += stats["error"]
            summary["last_update_at"] = _utc_now()

            _write_json_atomic(
                output_path,
                _build_output_payload(
                    input_path=input_path,
                    output_path=output_path,
                    summary=summary,
                    output_records=output_records,
                ),
            )
            print(item["message"], flush=True)

    summary["finished_at"] = _utc_now()
    _write_json_atomic(
        output_path,
        _build_output_payload(
            input_path=input_path,
            output_path=output_path,
            summary=summary,
            output_records=output_records,
        ),
    )
    print("\nDone.", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if args.fail_on_record_errors and summary["error"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
