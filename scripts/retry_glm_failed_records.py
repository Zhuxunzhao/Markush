#!/usr/bin/env python3
"""Retry failed GLM direct-infringement records and merge successes.

This script is intentionally narrow: it reads an existing dataset output JSON,
retries selected failed rows with the same direct text+image GLM worker used by
scripts/run_glm_first_image_infringement_dataset.py, and replaces records in the
output JSON only when retry attempts succeed by default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from run_glm_first_image_infringement_dataset import (
    DEFAULT_BASE_URL,
    DEFAULT_IMAGE_CACHE,
    DEFAULT_MAX_TEXT_CHARS,
    DEFAULT_MODEL,
    DEFAULT_TEXT_SOURCE,
    ROOT,
    _load_dotenv,
    _resolve_api_key,
    process_record,
)


DEFAULT_OUTPUT = ROOT / "outputs/results/molpatent-240/final/molpatent-240.glm5_1_claim_text_first_image_infringement.json"
DEFAULT_ERROR_CONTAINS = "Request timed out"


def _load_output(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("Output must be a JSON object with a records array")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _parse_indices(value: str | None) -> set[int] | None:
    if not value:
        return None
    indices: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Invalid descending index range: {part}")
            indices.update(range(start, end + 1))
        else:
            indices.add(int(part))
    return indices


def _record_payload(existing_record: dict[str, Any]) -> dict[str, Any]:
    inp = existing_record.get("input")
    if not isinstance(inp, dict):
        raise ValueError(f"Record {existing_record.get('index')} has no input object")
    return {
        "patent_id": inp.get("patent_id"),
        "smiles": inp.get("smiles"),
        "expected_is_protected": inp.get("expected_is_protected"),
        "selection_type": inp.get("selection_type"),
        "source_index": inp.get("source_index"),
    }


def _select_targets(
    records: list[dict[str, Any]],
    *,
    explicit_indices: set[int] | None,
    error_contains: str,
    retry_all_errors: bool,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for record in records:
        index = record.get("index")
        if not isinstance(index, int):
            continue
        if explicit_indices is not None:
            if index in explicit_indices:
                targets.append(record)
            continue
        if record.get("status") == "ok":
            continue
        if retry_all_errors or error_contains in str(record.get("error", "")):
            targets.append(record)
    return targets


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"ok": 0, "error": 0, "dry_run_ok": 0}
    for record in records:
        status = str(record.get("status") or "error")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _refresh_summary(
    payload: dict[str, Any],
    *,
    attempted: list[int],
    replaced: list[int],
    retry_log: Path,
) -> None:
    records = payload["records"]
    summary = payload.setdefault("summary", {})
    counts = _status_counts(records)
    summary["total"] = len(records)
    summary["completed"] = len(records)
    summary["ok"] = counts.get("ok", 0)
    summary["error"] = counts.get("error", 0)
    summary["dry_run_ok"] = counts.get("dry_run_ok", 0)
    summary["retry_last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary["retry_attempted_indices"] = attempted
    summary["retry_replaced_indices"] = replaced
    summary["retry_log"] = str(retry_log)


def _default_image_cache(summary: dict[str, Any]) -> Path:
    configured = summary.get("image_cache")
    if configured:
        path = Path(str(configured))
        if path.exists():
            return path
    return DEFAULT_IMAGE_CACHE


def main() -> int:
    _load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Existing output JSON to patch")
    parser.add_argument(
        "--indices",
        default=None,
        help="Comma-separated 1-based output indices to retry, e.g. 5,27,35 or 5-8",
    )
    parser.add_argument(
        "--error-contains",
        default=DEFAULT_ERROR_CONTAINS,
        help="Retry failed records whose error contains this text when --indices is omitted",
    )
    parser.add_argument("--retry-all-errors", action="store_true", help="Retry every non-ok record")
    parser.add_argument("--image-cache", type=Path, default=None, help="cache/google_patent path")
    parser.add_argument("--text-source", default=None, choices=["full", "claim", "description", "abstract"])
    parser.add_argument("--max-text-chars", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=900.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--response-language", choices=["en", "zh"], default="zh")
    parser.add_argument("--dry-run", action="store_true", help="Verify target selection and cached files only")
    parser.add_argument(
        "--replace-errors",
        action="store_true",
        help="Replace existing error records even when retry attempts fail again",
    )
    parser.add_argument(
        "--retry-log",
        type=Path,
        default=None,
        help="JSONL log for retry attempts; defaults to <output>.retry.jsonl",
    )
    args = parser.parse_args()

    output_path = args.output.resolve()
    payload = _load_output(output_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    records: list[dict[str, Any]] = payload["records"]
    positions = {
        int(record["index"]): pos
        for pos, record in enumerate(records)
        if isinstance(record, dict) and isinstance(record.get("index"), int)
    }
    explicit_indices = _parse_indices(args.indices)
    targets = _select_targets(
        records,
        explicit_indices=explicit_indices,
        error_contains=args.error_contains,
        retry_all_errors=args.retry_all_errors,
    )
    if not targets:
        print("No matching failed records to retry.")
        return 0

    retry_log = (args.retry_log or output_path.with_suffix(".retry.jsonl")).resolve()
    retry_log.parent.mkdir(parents=True, exist_ok=True)
    image_cache = (args.image_cache.resolve() if args.image_cache else _default_image_cache(summary).resolve())
    text_source = args.text_source or str(summary.get("text_source") or DEFAULT_TEXT_SOURCE)
    max_text_chars = args.max_text_chars
    if max_text_chars is None:
        max_text_chars = int(summary.get("max_text_chars") or DEFAULT_MAX_TEXT_CHARS)
    model = args.model or str(summary.get("model") or DEFAULT_MODEL)
    base_url = args.base_url or str(summary.get("base_url") or DEFAULT_BASE_URL)

    api_key: str | None = None
    api_key_env: str | None = None
    if not args.dry_run:
        api_key, api_key_env = _resolve_api_key(args.api_key_env)

    target_indices = [int(record["index"]) for record in targets]
    print(f"Retrying {len(targets)} record(s): {target_indices}")
    print(f"Output JSON: {output_path}")
    print(f"Retry log: {retry_log}")
    print(f"Model={model}; base_url={base_url}; text_source={text_source}; max_text_chars={max_text_chars}")
    print(f"Image cache: {image_cache}")
    if api_key_env:
        print(f"API key env: {api_key_env}")

    attempted: list[int] = []
    replaced: list[int] = []
    workers = max(1, args.workers)

    def run_one(existing_record: dict[str, Any]) -> dict[str, Any]:
        index = int(existing_record["index"])
        return process_record(
            index=index,
            record=_record_payload(existing_record),
            image_cache=image_cache,
            text_source=text_source,
            max_text_chars=max_text_chars,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            request_timeout=args.request_timeout,
            dry_run=args.dry_run,
            response_language=args.response_language,
        )

    def handle_result(result: dict[str, Any]) -> None:
        index = int(result["index"])
        attempted.append(index)
        previous = records[positions[index]]
        should_replace = result.get("status") == "ok" or args.replace_errors
        if should_replace:
            records[positions[index]] = result
            replaced.append(index)

        log_record = dict(result)
        log_record["retry"] = {
            "previous_status": previous.get("status"),
            "previous_error": previous.get("error"),
            "replaced_output_record": should_replace,
        }
        with retry_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_record, ensure_ascii=False) + "\n")

        if not args.dry_run:
            _refresh_summary(payload, attempted=attempted, replaced=replaced, retry_log=retry_log)
        if should_replace and not args.dry_run:
            _write_json_atomic(output_path, payload)

        verdict = result.get("result", {}).get("is_infringing") if isinstance(result.get("result"), dict) else None
        detail = f"is_infringing={verdict}" if result.get("status") == "ok" else str(result.get("error", ""))
        print(f"[{index}] {result.get('status')} {detail}", flush=True)

    if workers == 1:
        for target in targets:
            handle_result(run_one(target))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {executor.submit(run_one, target): int(target["index"]) for target in targets}
            for future in as_completed(future_to_index):
                handle_result(future.result())

    if not args.dry_run:
        _refresh_summary(payload, attempted=attempted, replaced=replaced, retry_log=retry_log)
        _write_json_atomic(output_path, payload)
    print(f"Done. Attempted={attempted}; replaced={replaced}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
