#!/usr/bin/env python3
"""Run direct GLM-5.1 infringement checks from cached patent text and image.

This bypasses the existing MarkushGrapher workflow. It reads patent IDs from the
dataset, takes the local patent text plus the first local PNG from
cache/google_patent/<patent_id>/, and asks GLM-5.1 for a direct infringement
decision.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from openai import OpenAI


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data/molpatent-240.infringement_input.json"
DEFAULT_OUTPUT = ROOT / "outputs/molpatent-240.glm5_1_text_first_image_infringement.json"
DEFAULT_IMAGE_CACHE = ROOT / "cache/google_patent"
DEFAULT_MODEL = "glm-5.1"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TEXT_SOURCE = "claim"
DEFAULT_MAX_TEXT_CHARS = 60_000


SYSTEM_PROMPT = """你是一名谨慎的化学专利侵权分析专家。
你会收到缓存的专利文本、一张缓存的专利图片，以及一个查询分子的 SMILES。
请判断该查询分子是否看起来落入这些证据所代表的专利保护范围。

只返回合法 JSON，字段如下：
- is_infringing: boolean
- judgment_zh: 一句话中文结论，例如 "判断：落入保护范围" 或 "判断：未落入保护范围"
- confidence: "high", "moderate", "low", or "very_low"
- reasoning: 基于专利文本、图片和 SMILES 的简洁中文推理
- evidence: 来自专利文本或图片的简短中文证据列表

请保持保守。如果专利证据没有足够的权利要求或结构信息来验证覆盖关系，
请将 is_infringing 设为 false，并给出 low 或 very_low 置信度。
"""


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    raise ValueError("Input must be a JSON array, or an object with a records array")


def _jsonl_path_for(path: Path) -> Path:
    return path.with_suffix(".jsonl") if path.suffix else path.with_name(path.name + ".jsonl")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _existing_records(output_path: Path) -> dict[int, dict[str, Any]]:
    if not output_path.exists():
        return {}
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = payload.get("records", []) if isinstance(payload, dict) else []
    return {
        int(record["index"]): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("index"), int)
    }


def _image_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"image_(\d+)\.png$", path.name)
    if match:
        return int(match.group(1)), path.name
    return 10**9, path.name


def first_cached_image(patent_id: str, cache_root: Path) -> Path:
    patent_dir = cache_root / patent_id
    images = sorted(patent_dir.glob("image_*.png"), key=_image_sort_key)
    images = [path for path in images if path.is_file() and path.stat().st_size > 0]
    if not images:
        raise FileNotFoundError(f"no cached image found under {patent_dir}")
    return images[0]


def patent_text_path(patent_id: str, cache_root: Path, text_source: str) -> Path:
    text_files = {
        "full": "full_text.txt",
        "claim": "claim_text.txt",
        "description": "description_text.txt",
        "abstract": "abstract_text.txt",
    }
    try:
        filename = text_files[text_source]
    except KeyError as e:
        choices = ", ".join(sorted(text_files))
        raise ValueError(f"unsupported text source {text_source!r}; choose one of: {choices}") from e
    return cache_root / patent_id / filename


def load_patent_text(
    *,
    patent_id: str,
    cache_root: Path,
    text_source: str,
    max_text_chars: int,
) -> tuple[str, dict[str, Any]]:
    path = patent_text_path(patent_id, cache_root, text_source)
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"no cached patent text found at {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    original_chars = len(text)
    truncated = max_text_chars > 0 and original_chars > max_text_chars
    if truncated:
        text = text[:max_text_chars]
    return text, {
        "path": str(path),
        "source": text_source,
        "chars": original_chars,
        "used_chars": len(text),
        "truncated": truncated,
    }


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {"raw_text": text, "is_infringing": False, "confidence": "very_low"}


def _resolve_api_key(explicit_env: str | None) -> tuple[str, str]:
    env_names = [explicit_env] if explicit_env else ["ZAI_API_KEY", "GLM_API_KEY", "OPENAI_API_KEY"]
    for env_name in env_names:
        if env_name and os.environ.get(env_name):
            return os.environ[env_name], env_name
    raise RuntimeError("No API key found. Set ZAI_API_KEY, GLM_API_KEY, or OPENAI_API_KEY.")


def call_glm_text_image(
    *,
    patent_id: str,
    smiles: str,
    patent_text: str,
    text_info: dict[str, Any],
    image_path: Path,
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int,
    temperature: float,
    request_timeout: float,
    response_language: str,
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=request_timeout)
    if response_language == "zh":
        output_instruction = """请用中文输出模型判断，不要只给布尔值。JSON 字段要求：
- is_infringing: boolean
- judgment_zh: 一句话中文结论，明确写“判断：落入保护范围”或“判断：未落入保护范围”
- confidence: "high", "moderate", "low", or "very_low"
- reasoning: 中文推理，说明权利要求文本、图片结构和 SMILES 的对应关系
- evidence: 中文证据列表，引用关键权利要求文本或图片中的结构信息"""
    else:
        output_instruction = """返回 JSON 字段：
- is_infringing: boolean
- judgment_zh: 简洁中文判断句
- confidence: "high", "moderate", "low", or "very_low"
- reasoning: 简洁中文推理
- evidence: 中文证据列表"""
    user_text = f"""专利号: {patent_id}
查询分子 SMILES: `{smiles}`

专利文本来源: {text_info["source"]}（使用 {text_info["used_chars"]} 个字符；truncated={text_info["truncated"]}）

专利文本:
```text
{patent_text}
```

请使用专利文本和随附的第一张缓存专利图片作为证据。
判断查询分子是否侵权/是否落入图文证据显示的专利保护范围。

{output_instruction}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ],
            },
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    parsed = _parse_json_response(content)
    parsed.setdefault("is_infringing", False)
    parsed.setdefault("judgment_zh", "判断：未落入保护范围" if not parsed["is_infringing"] else "判断：落入保护范围")
    parsed.setdefault("confidence", "very_low")
    parsed.setdefault("reasoning", "")
    parsed.setdefault("evidence", [])
    return parsed


def process_record(
    *,
    index: int,
    record: dict[str, Any],
    image_cache: Path,
    text_source: str,
    max_text_chars: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int,
    temperature: float,
    request_timeout: float,
    dry_run: bool,
    response_language: str,
) -> dict[str, Any]:
    patent_id = str(record.get("patent_id", "")).strip()
    smiles = str(record.get("smiles") or record.get("target_smiles") or "").strip()
    started = time.time()
    out: dict[str, Any] = {
        "index": index,
        "input": {
            "patent_id": patent_id,
            "smiles": smiles,
            "source_index": record.get("source_index"),
            "expected_is_protected": record.get("expected_is_protected"),
            "selection_type": record.get("selection_type"),
        },
        "model": model,
        "status": "error",
    }
    try:
        if not patent_id or not smiles:
            raise ValueError("missing patent_id or smiles")
        image_path = first_cached_image(patent_id, image_cache)
        patent_text, text_info = load_patent_text(
            patent_id=patent_id,
            cache_root=image_cache,
            text_source=text_source,
            max_text_chars=max_text_chars,
        )
        out["image"] = {
            "path": str(image_path),
            "bytes": image_path.stat().st_size,
        }
        out["text"] = text_info
        if dry_run:
            out["status"] = "dry_run_ok"
            out["result"] = {
                "is_infringing": None,
                "confidence": None,
                "reasoning": "已找到缓存的专利文本和第一张缓存图片；dry-run 跳过 GLM 调用。",
                "evidence": [],
            }
        else:
            if not api_key:
                raise RuntimeError("API key is required unless --dry-run is used")
            out["result"] = call_glm_text_image(
                patent_id=patent_id,
                smiles=smiles,
                patent_text=patent_text,
                text_info=text_info,
                image_path=image_path,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=max_tokens,
                temperature=temperature,
                request_timeout=request_timeout,
                response_language=response_language,
            )
            out["status"] = "ok"
    except Exception as e:
        out["error"] = str(e)
    finally:
        out["elapsed_sec"] = round(time.time() - started, 2)
    return out


def _build_payload(
    input_path: Path,
    output_path: Path,
    summary: dict[str, Any],
    records: list[dict[str, Any] | None],
) -> dict[str, Any]:
    return {
        "input": str(input_path),
        "output": str(output_path),
        "summary": summary,
        "records": [record for record in records if record is not None],
    }


def _run_one_task(
    task: tuple[int, dict[str, Any]],
    *,
    image_cache: Path,
    text_source: str,
    max_text_chars: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int,
    temperature: float,
    request_timeout: float,
    dry_run: bool,
    response_language: str,
) -> dict[str, Any]:
    index, record = task
    return process_record(
        index=index,
        record=record,
        image_cache=image_cache,
        text_source=text_source,
        max_text_chars=max_text_chars,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        request_timeout=request_timeout,
        dry_run=dry_run,
        response_language=response_language,
    )


def main() -> None:
    _load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Direct GLM-5.1 infringement analysis from cached patent text and first cached image")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input dataset JSON path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--image-cache", default=str(DEFAULT_IMAGE_CACHE), help="cache/google_patent path")
    parser.add_argument(
        "--text-source",
        default=os.environ.get("GLM_PATENT_TEXT_SOURCE", DEFAULT_TEXT_SOURCE),
        choices=["full", "claim", "description", "abstract"],
        help="Cached patent text file to include",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=int(os.environ.get("GLM_PATENT_MAX_TEXT_CHARS", DEFAULT_MAX_TEXT_CHARS)),
        help="Maximum patent text characters sent per record; 0 means no truncation",
    )
    parser.add_argument("--model", default=os.environ.get("GLM_MODEL") or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL)
    parser.add_argument(
        "--base-url",
        default=(
            os.environ.get("GLM_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("ZAI_BASE_URL")
            or DEFAULT_BASE_URL
        ),
    )
    parser.add_argument("--api-key-env", default=None, help="Specific env var containing the GLM API key")
    parser.add_argument("--limit", type=int, default=0, help="Only run first N selected records")
    parser.add_argument("--start-index", type=int, default=1, help="1-based first record index")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent model requests")
    parser.add_argument(
        "--response-language",
        choices=["en", "zh"],
        default="zh",
        help="Language/style requested for model reasoning fields",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only verify local image lookup; skip GLM")
    parser.add_argument("--force", action="store_true", help="Re-run records already present in output")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    image_cache = Path(args.image_cache).resolve()
    jsonl_path = _jsonl_path_for(output_path)
    records = _load_records(input_path)

    start_index = max(1, args.start_index)
    selected = list(enumerate(records[start_index - 1 :], start=start_index))
    if args.limit > 0:
        selected = selected[: args.limit]

    existing = {} if args.force else _existing_records(output_path)
    api_key: str | None = None
    api_key_env: str | None = None
    if not args.dry_run:
        api_key, api_key_env = _resolve_api_key(args.api_key_env)

    summary = {
        "total": len(selected),
        "completed": 0,
        "ok": 0,
        "error": 0,
        "dry_run_ok": 0,
        "skipped_existing": 0,
        "model": args.model,
        "base_url": args.base_url,
        "api_key_env": api_key_env,
        "image_cache": str(image_cache),
        "text_source": args.text_source,
        "max_text_chars": args.max_text_chars,
        "workers": max(1, args.workers),
        "response_language": args.response_language,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    output_records: list[dict[str, Any] | None] = [None] * len(selected)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    workers = max(1, args.workers)
    print(f"Running {len(selected)} record(s); model={args.model}; dry_run={args.dry_run}; workers={workers}", flush=True)
    print(f"Base URL: {args.base_url}", flush=True)
    print(f"Incremental JSON: {output_path}", flush=True)
    print(f"Per-record JSONL: {jsonl_path}", flush=True)

    with jsonl_path.open("a", encoding="utf-8") as jsonl:
        pending: list[tuple[int, dict[str, Any]]] = []
        positions: dict[int, int] = {}
        for position, (index, record) in enumerate(selected):
            positions[index] = position
            if index in existing:
                existing_record = existing[index]
                output_records[position] = existing_record
                summary["skipped_existing"] += 1
                summary["completed"] += 1
                summary[existing_record.get("status", "error")] = summary.get(existing_record.get("status", "error"), 0) + 1
                print(f"[{index}] {record.get('patent_id')}: SKIP existing", flush=True)
            else:
                pending.append((index, record))

        def handle_result(result: dict[str, Any]) -> None:
            index = int(result["index"])
            output_records[positions[index]] = result
            summary["completed"] += 1
            summary[result["status"]] = summary.get(result["status"], 0) + 1
            jsonl.write(json.dumps(result, ensure_ascii=False) + "\n")
            jsonl.flush()
            os.fsync(jsonl.fileno())
            verdict = result.get("result", {}).get("is_infringing")
            judgment = result.get("result", {}).get("judgment_zh")
            detail = f"is_infringing={verdict}"
            if judgment:
                detail += f" {judgment}"
            if result["status"] != "ok":
                detail = result.get("error", "")
            print(f"[{index}/{start_index + len(selected) - 1}] {result['input'].get('patent_id')}: {result['status']} {detail}", flush=True)
            _write_json_atomic(output_path, _build_payload(input_path, output_path, summary, output_records))

        if workers == 1:
            for task in pending:
                result = _run_one_task(
                    task,
                    image_cache=image_cache,
                    text_source=args.text_source,
                    max_text_chars=args.max_text_chars,
                    model=args.model,
                    base_url=args.base_url,
                    api_key=api_key,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    request_timeout=args.request_timeout,
                    dry_run=args.dry_run,
                    response_language=args.response_language,
                )
                handle_result(result)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        _run_one_task,
                        task,
                        image_cache=image_cache,
                        text_source=args.text_source,
                        max_text_chars=args.max_text_chars,
                        model=args.model,
                        base_url=args.base_url,
                        api_key=api_key,
                        max_tokens=args.max_tokens,
                        temperature=args.temperature,
                        request_timeout=args.request_timeout,
                        dry_run=args.dry_run,
                        response_language=args.response_language,
                    )
                    for task in pending
                ]
                for future in as_completed(futures):
                    result = future.result()
                    handle_result(result)

        if not pending:
            _write_json_atomic(output_path, _build_payload(input_path, output_path, summary, output_records))

    summary["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json_atomic(output_path, _build_payload(input_path, output_path, summary, output_records))
    print("Done.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
