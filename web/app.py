from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipelines.llm_infringement import LLMInfringementPipeline
from pipelines.llm_patentability import LLMPatentabilityPipeline
from tools.llm_client import load_config
from tools.logger import log


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "web" / "static"
UPLOAD_DIR = ROOT / "web" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR = ROOT / "outputs" / "results"
UI_RESULTS_DIR = RESULTS_DIR / "ui"
UI_INFRINGEMENT_RESULTS_PATH = UI_RESULTS_DIR / "web_infringement_results.jsonl"
UI_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = ROOT / "outputs" / "ui-reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_FILE_ROOTS = [ROOT / "cache", ROOT / "outputs", UPLOAD_DIR]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
UI_RESULT_WRITE_LOCK = threading.Lock()

CONFIG = load_config(str(ROOT / "config.yaml"))
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt5.5"
DEFAULT_LLM_BASE_URL = (
    os.environ.get("OHMYGPT_API_BASE") or "https://api.ohmygpt.com/v1"
)
DEFAULT_LLM_API_KEY_ENV = "OHMYGPT_API_KEY"
LLM_MODEL_OPTIONS = [
    {"value": "qwen3.6-plus", "label": "qwen3.6-plus"},
    {"value": "gpt5.5", "label": "gpt5.5"},
    {"value": "glm5.1", "label": "glm5.1"},
]
DEFAULT_GPT_MAX_TOKENS = 4096
DEFAULT_GPT_REQUEST_TIMEOUT = 360.0
DEFAULT_GPT_TOKEN_LIMIT_PARAM = "max_completion_tokens"
DEFAULT_GPT_OMIT_TEMPERATURE = True
DEFAULT_GPT_REASONING_EFFORT = "medium"
DEFAULT_GPT_VERBOSITY = "medium"

app = FastAPI(title="Markush Patent Intelligence Workbench")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class LLMSettings(BaseModel):
    provider: str = DEFAULT_LLM_PROVIDER
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None


class InfringementPayload(BaseModel):
    evaluation_name: Optional[str] = None
    patent_id: str
    smiles: str
    caption: Optional[str] = None
    llm: Optional[LLMSettings] = None
    previous_result_id: Optional[str] = None
    include_patentability: bool = False


class StepRerunPayload(BaseModel):
    agent_key: str


class JobStopped(Exception):
    """Raised inside pipeline callbacks when the user stops a running job."""


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(
        self,
        mode: str,
        payload: dict[str, Any],
        runner_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._lock:
            job_id = _timestamp_job_id(self._jobs)
            job = {
                "id": job_id,
                "mode": mode,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "payload": payload,
                "events": [],
                "step_outputs": [],
                "result": None,
                "error": None,
                "_cancel_requested": False,
                "_runner_payload": runner_payload or payload,
            }
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            public_job = {key: value for key, value in job.items() if not key.startswith("_")}
            return {
                **public_job,
                "events": list(job["events"]),
                "step_outputs": list(job["step_outputs"]),
            }

    def get_runner_payload(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return dict(job.get("_runner_payload") or job["payload"])

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.get("status") == "cancelled":
                blocked_statuses = {"queued", "running", "succeeded"}
                if changes.get("status") in blocked_statuses:
                    changes = {key: value for key, value in changes.items() if key != "status"}
                if "result" in changes and changes.get("status") != "failed":
                    changes = {key: value for key, value in changes.items() if key != "result"}
            job.update(changes)
            job["updated_at"] = _utc_now()

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["events"].append(event)
            job["updated_at"] = _utc_now()

    def append_step_output(self, job_id: str, output: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["step_outputs"].append(output)
            job["updated_at"] = _utc_now()

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                return {key: value for key, value in job.items() if not key.startswith("_")}
            job["_cancel_requested"] = True
            job["status"] = "cancelled"
            job["error"] = {"message": "用户已手动停止任务。"}
            job["updated_at"] = _utc_now()
            return {key: value for key, value in job.items() if not key.startswith("_")}

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs[job_id]
            return bool(job.get("_cancel_requested")) or job.get("status") == "cancelled"

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = []
            for job in self._jobs.values():
                public_job = {key: value for key, value in job.items() if not key.startswith("_")}
                jobs.append(
                    {
                        **public_job,
                        "events": list(job["events"]),
                        "step_outputs": list(job["step_outputs"]),
                    }
                )
            return jobs


JOBS = JobStore()


PIPELINE_BLUEPRINTS = {
    "infringement": [
        {"key": "fetch", "name": "专利文本抓取", "detail": "读取专利权利要求、说明书与附图索引。"},
        {"key": "markush", "name": "LLM Markush 结构解析", "detail": "用 LLM 解析主 Markush 通式与变量定义。"},
        {"key": "claim", "name": "权利要求解析", "detail": "抽取保护范围、R-group 约束与关键 claim 语义。"},
        {"key": "llm_match", "name": "LLM 分子结构匹配", "detail": "判断待评估分子骨架和 R-group 映射。"},
        {"key": "fusion", "name": "匹配融合验证", "detail": "融合 LLM 结构匹配与 claim 语义证据。"},
        {"key": "alignment", "name": "R-group 标签对齐", "detail": "把结构局部变量对齐到权利要求法律变量。"},
        {"key": "requirements", "name": "保护范围判断", "detail": "逐项检查是否落入权利要求覆盖范围。"},
        {"key": "report", "name": "侵权分析报告", "detail": "生成结论、置信度、理由与风险提示。"},
    ],
    "patentability": [
        {"key": "resolve", "name": "拟申请结构解析", "detail": "解析拟申请 CXSMILES 或上传结构图。"},
        {"key": "search", "name": "现有技术检索", "detail": "基于侵权分析结果生成现有技术检索线索。"},
        {"key": "prior_markush", "name": "Prior-art Markush 解析", "detail": "用 LLM 提取候选专利中的可比较 Markush。"},
        {"key": "novelty", "name": "新颖性分析", "detail": "比较重叠特征、差异特征与新颖性风险。"},
        {"key": "authorization", "name": "授权可能性分析", "detail": "综合创造性、清楚性与授权风险。"},
        {"key": "report", "name": "可授权分析报告", "detail": "生成申请策略、风险点与改进建议。"},
    ],
}

PATENTABILITY_AS_INFRINGEMENT_NODE = {
    "key": "patentability",
    "name": "可授权分析",
    "detail": "基于侵权分析结果评估新颖性、创造性与授权风险。",
}

PIPELINE_BLUEPRINTS["infringement_patentability"] = [
    {**item} for item in PIPELINE_BLUEPRINTS["infringement"]
] + [{**PATENTABILITY_AS_INFRINGEMENT_NODE}]


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _timestamp_job_id(existing_jobs: dict[str, dict[str, Any]]) -> str:
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    if base not in existing_jobs:
        return base
    suffix = 2
    while f"{base}-{suffix:02d}" in existing_jobs:
        suffix += 1
    return f"{base}-{suffix:02d}"


def _uses_gpt_reasoning_defaults(model: str) -> bool:
    normalized = str(model or "").strip().lower().replace("_", "-")
    return normalized.startswith("gpt-5") or normalized.startswith("gpt5")


def _llm_model_candidates(model_or_profile: str) -> list[str]:
    raw = str(model_or_profile or "").strip()
    lowered = raw.lower().replace("_", "-")
    candidates = [raw, lowered]
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
    if lowered in {"gpt5.5", "gpt-5.5"}:
        candidates.extend(["gpt5.5", "gpt-5.5"])
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        candidates.extend(["glm5.1", "glm-5.1"])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _canonical_ui_model_name(model_or_profile: str) -> str:
    lowered = str(model_or_profile or "").strip().lower().replace("_", "-")
    if lowered in {
        "3.6plus",
        "3.6-plus",
        "qwen3.6plus",
        "qwen3.6-plus",
        "qwen-3.6plus",
        "qwen-3.6-plus",
    }:
        return "qwen3.6-plus"
    if lowered in {"gpt5.5", "gpt-5.5"}:
        return "gpt5.5"
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        return "glm5.1"
    return str(model_or_profile).strip()


def _llm_profile_for_model(model_or_profile: str) -> dict[str, Any]:
    profiles = CONFIG.get("llm_profiles", {}) if isinstance(CONFIG.get("llm_profiles"), dict) else {}
    for candidate in _llm_model_candidates(model_or_profile):
        profile = profiles.get(candidate)
        if isinstance(profile, dict):
            return profile
    return {}


def _serialize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {key: _serialize(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _parse_iso_timestamp(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def _record_timestamp(record: dict[str, Any], fallback_mtime: float) -> tuple[float, str]:
    for key in ("completed_at", "finished_at", "updated_at", "created_at"):
        value = record.get(key)
        parsed = _parse_iso_timestamp(value)
        if parsed is not None:
            return parsed, str(value)
    return fallback_mtime, datetime.utcfromtimestamp(fallback_mtime).isoformat() + "Z"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _remap_project_path(raw_path: str) -> Optional[Path]:
    normalized = raw_path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    for marker in ("cache", "outputs", "web"):
        if marker in parts:
            candidate = ROOT.joinpath(*parts[parts.index(marker):])
            if candidate.exists():
                return candidate
    return None


def _resolve_public_file(raw_path: str) -> Path:
    if not raw_path:
        raise HTTPException(status_code=404, detail="file not found")

    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        remapped = _remap_project_path(raw_path)
        if remapped is not None:
            path = remapped

    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if resolved.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=403, detail="unsupported file type")

    allowed_roots = [root.resolve() for root in PUBLIC_FILE_ROOTS if root.exists()]
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="file is outside public roots")
    return resolved


def _iter_json_records(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [item for item in data["records"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _iter_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
    except Exception:
        return []
    return records


def _record_input(record: dict[str, Any]) -> dict[str, Any]:
    raw_input = record.get("input") if isinstance(record.get("input"), dict) else {}
    raw_result = record.get("result") if isinstance(record.get("result"), dict) else {}
    return {
        "evaluation_name": raw_input.get("evaluation_name")
        or record.get("evaluation_name"),
        "patent_id": raw_input.get("patent_id") or raw_result.get("patent_id"),
        "smiles": raw_input.get("smiles") or raw_result.get("target_smiles"),
    }


def _normalize_evaluation_name(value: Any) -> str:
    return str(value or "").strip()


def _record_matches(
    record: dict[str, Any],
    patent_id: str,
    smiles: str,
    evaluation_name: str = "",
) -> bool:
    record_input = _record_input(record)
    normalized_name = _normalize_evaluation_name(evaluation_name)
    if normalized_name:
        return (
            _normalize_evaluation_name(record_input.get("evaluation_name")).lower()
            == normalized_name.lower()
        )
    return (
        str(record_input.get("patent_id") or "").strip().lower()
        == patent_id.strip().lower()
        and str(record_input.get("smiles") or "").strip() == smiles.strip()
    )


def _infringement_result_from_record(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    if not isinstance(result, dict):
        return {}
    infringement = result.get("infringement")
    if isinstance(infringement, dict):
        return infringement
    return result


def _is_valid_infringement_result(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict) or not result:
        return False
    status = str(result.get("analysis_status") or "").strip().lower()
    if status in {"failed", "error", "cancelled", "canceled", "running", "queued", "undetermined"}:
        return False
    is_protected = result.get("is_protected")
    if is_protected is None:
        is_protected = result.get("is_infringing")
    if not isinstance(is_protected, bool):
        return False
    if result.get("is_conclusive") is False:
        return False
    if not (result.get("report") or result.get("reasoning") or result.get("judgment_zh")):
        return False
    return True


def _is_success_record(record: dict[str, Any]) -> bool:
    status = str(record.get("status") or "").strip().lower()
    if status and status not in {"ok", "success", "succeeded", "completed", "done"}:
        return False
    if (
        record.get("source") == "web-ui"
        and record.get("mode") == "infringement_patentability"
        and record.get("workflow_complete") is not True
    ):
        return False
    return _is_valid_infringement_result(_infringement_result_from_record(record))


def _record_has_patentability_result(record: dict[str, Any]) -> bool:
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    return isinstance(result.get("patentability"), dict) and bool(result.get("patentability"))


def _ui_infringement_record_from_job(
    job: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    llm = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
    evaluation_name = _normalize_evaluation_name(payload.get("evaluation_name"))
    infringement = _infringement_result_from_record({"result": result})
    patent_id = payload.get("patent_id") or infringement.get("patent_id") or result.get("patent_id")
    smiles = payload.get("smiles") or infringement.get("target_smiles") or result.get("target_smiles")
    return {
        "source": "web-ui",
        "job_id": job.get("id"),
        "mode": job.get("mode"),
        "workflow_complete": job.get("status") == "succeeded"
        and (
            job.get("mode") != "infringement_patentability"
            or isinstance((job.get("result") or {}).get("patentability"), dict)
        ),
        "input": {
            "evaluation_name": evaluation_name or None,
            "patent_id": patent_id,
            "smiles": smiles,
            "caption_provided": bool(payload.get("caption")),
        },
        "model": llm.get("model"),
        "provider": llm.get("provider"),
        "status": "ok",
        "result": _serialize(result),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "completed_at": _utc_now(),
    }


def _persist_ui_infringement_result(job_id: str, result: dict[str, Any]) -> None:
    try:
        job = JOBS.get(job_id)
        record = _ui_infringement_record_from_job(job, result)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with UI_RESULT_WRITE_LOCK:
            with UI_INFRINGEMENT_RESULTS_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        JOBS.append_event(
            job_id,
            {
                "timestamp": _utc_now(),
                "level": "info",
                "message": f"Persisted UI result to {UI_INFRINGEMENT_RESULTS_PATH.relative_to(ROOT).as_posix()}.",
            },
        )
    except Exception as exc:
        JOBS.append_event(
            job_id,
            {
                "timestamp": _utc_now(),
                "level": "warning",
                "message": f"Could not persist UI result: {exc}",
            },
        )


def _in_memory_infringement_result(job: dict[str, Any]) -> Optional[dict[str, Any]]:
    if job.get("status") != "succeeded":
        return None
    result = job.get("result")
    if not isinstance(result, dict):
        return None
    if job.get("mode") == "infringement" and "is_protected" in result:
        return result
    infringement = result.get("infringement")
    if isinstance(infringement, dict) and "is_protected" in infringement:
        return infringement
    return None


def _record_from_ui_report(path: Path) -> Optional[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception:
        return None

    patent_match = re.search(r"-\s*目标专利：\s*(.+)", text)
    smiles_match = re.search(r"-\s*目标分子：`([^`]+)`", text)
    if not patent_match or not smiles_match:
        return None

    status_match = re.search(r"-\s*分析状态：\s*(.+)", text)
    confidence_match = re.search(r"-\s*置信度：\s*(.+)", text)
    conclusion_match = re.search(r"-\s*结论：\s*(.+)", text)
    analysis_status = (status_match.group(1).strip() if status_match else "") or "completed"
    conclusion = conclusion_match.group(1).strip() if conclusion_match else ""
    is_protected: Optional[bool]
    if analysis_status == "not_protected" or "未落入" in conclusion:
        is_protected = False
    elif analysis_status == "protected" or "落入" in conclusion:
        is_protected = True
    else:
        is_protected = None

    report = ""
    report_start = text.find("## 侵权分析报告原始内容")
    if report_start >= 0:
        body = text[report_start + len("## 侵权分析报告原始内容") :]
        next_section = body.find("\n## ")
        report = (body[:next_section] if next_section >= 0 else body).strip()

    result = {
        "patent_id": patent_match.group(1).strip(),
        "target_smiles": smiles_match.group(1).strip(),
        "is_protected": bool(is_protected) if is_protected is not None else False,
        "is_conclusive": is_protected is not None,
        "analysis_status": analysis_status,
        "confidence": confidence_match.group(1).strip() if confidence_match else "unknown",
        "fused_match": {"r_group_matching": {}},
        "llm_outputs": {"loaded_from_ui_report": path.name},
        "report": report,
    }
    return {
        "source": "web-ui-report",
        "input": {
            "patent_id": result["patent_id"],
            "smiles": result["target_smiles"],
        },
        "status": "ok",
        "result": result,
        "finished_at": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z",
    }


def _previous_result_id(path: Path, offset: int) -> str:
    try:
        rel_path = path.resolve().relative_to(ROOT)
    except ValueError:
        rel_path = path.resolve()
    raw = f"{rel_path.as_posix()}::{offset}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _memory_previous_result_id(job_id: str) -> str:
    return hashlib.sha1(f"memory::{job_id}".encode("utf-8")).hexdigest()


def _iter_previous_infringement_results(
    patent_id: str,
    smiles: str,
    evaluation_name: str = "",
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    disk_job_ids: set[str] = set()
    if RESULTS_DIR.exists():
        for path in RESULTS_DIR.rglob("*"):
            if path.suffix.lower() not in {".json", ".jsonl"}:
                continue
            records = (
                _iter_jsonl_records(path)
                if path.suffix.lower() == ".jsonl"
                else _iter_json_records(path)
            )
            mtime = path.stat().st_mtime
            for offset, record in enumerate(records):
                if not _is_success_record(record) or not _record_matches(
                    record,
                    patent_id,
                    smiles,
                    evaluation_name,
                ):
                    continue
                timestamp, updated_at = _record_timestamp(record, mtime)
                if record.get("job_id"):
                    disk_job_ids.add(str(record["job_id"]))
                matches.append(
                    {
                        "id": _previous_result_id(path, offset),
                        "record": record,
                        "path": path,
                        "offset": offset,
                        "score": (timestamp, offset),
                        "updated_at": updated_at,
                    }
                )

    if REPORT_DIR.exists():
        for offset, path in enumerate(REPORT_DIR.glob("*.infringement_report.md")):
            record = _record_from_ui_report(path)
            if not record or not _is_success_record(record) or not _record_matches(
                record,
                patent_id,
                smiles,
                evaluation_name,
            ):
                continue
            timestamp, updated_at = _record_timestamp(record, path.stat().st_mtime)
            matches.append(
                {
                    "id": _previous_result_id(path, offset),
                    "record": record,
                    "path": path,
                    "offset": offset,
                    "score": (timestamp, offset),
                    "updated_at": updated_at,
                }
            )

    for job in JOBS.list():
        job_id = str(job.get("id") or "")
        if not job_id or job_id in disk_job_ids:
            continue
        result = _in_memory_infringement_result(job)
        if not result:
            continue
        record = _ui_infringement_record_from_job(job, result)
        if not _record_matches(record, patent_id, smiles, evaluation_name):
            continue
        fallback = _parse_iso_timestamp(job.get("updated_at")) or time.time()
        timestamp, updated_at = _record_timestamp(record, fallback)
        matches.append(
            {
                "id": _memory_previous_result_id(job_id),
                "record": record,
                "path": None,
                "offset": 0,
                "score": (timestamp, 0),
                "updated_at": updated_at,
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches


def _previous_result_candidate(match: dict[str, Any]) -> dict[str, Any]:
    record = match["record"]
    result = _infringement_result_from_record(record)
    record_input = _record_input(record)
    evaluation_name = _normalize_evaluation_name(record_input.get("evaluation_name"))
    is_protected = result.get("is_protected")
    if is_protected is None:
        is_protected = result.get("is_infringing")
    analysis_status = result.get("analysis_status")
    if not analysis_status:
        analysis_status = (
            "protected"
            if is_protected is True
            else "not_protected"
            if is_protected is False
            else "completed"
        )
    path = match.get("path")
    if isinstance(path, Path):
        try:
            rel_path = path.relative_to(ROOT)
        except ValueError:
            rel_path = path
        source_file = rel_path.as_posix()
    else:
        source_file = "current-session"
    label = (
        f"{evaluation_name or record.get('model') or 'unknown-model'} | "
        f"{analysis_status} | {match['updated_at']}"
    )
    image = record.get("image") if isinstance(record.get("image"), dict) else {}
    return {
        "id": match["id"],
        "label": label,
        "source_file": source_file,
        "record_index": record.get("index") or match["offset"],
        "evaluation_name": evaluation_name or None,
        "model": record.get("model"),
        "confidence": result.get("confidence"),
        "analysis_status": analysis_status,
        "is_protected": is_protected,
        "elapsed_sec": record.get("elapsed_sec"),
        "updated_at": match["updated_at"],
        "patent_id": record_input.get("patent_id"),
        "smiles": record_input.get("smiles"),
        "image_path": image.get("path"),
    }


def _find_previous_infringement_result(
    patent_id: str,
    smiles: str,
    evaluation_name: str = "",
    result_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    matches = _iter_previous_infringement_results(
        patent_id,
        smiles,
        evaluation_name,
    )
    if result_id:
        return next((item for item in matches if item["id"] == result_id), None)
    return matches[0] if matches else None


def _normalize_loaded_infringement_record(record: dict[str, Any]) -> dict[str, Any]:
    record_input = _record_input(record)
    raw_result = dict(_infringement_result_from_record(record))
    image_path = (
        (record.get("image") or {}).get("path")
        if isinstance(record.get("image"), dict)
        else None
    )
    image_selection = record.get("image_selection")

    if "is_protected" in raw_result:
        result = raw_result
    else:
        is_protected = raw_result.get("is_infringing")
        result = {
            "patent_id": record_input.get("patent_id"),
            "target_smiles": record_input.get("smiles"),
            "is_protected": bool(is_protected) if is_protected is not None else False,
            "is_conclusive": is_protected is not None,
            "analysis_status": (
                "protected"
                if is_protected is True
                else "not_protected"
                if is_protected is False
                else "undetermined"
            ),
            "confidence": raw_result.get("confidence") or "unknown",
            "markush_structure": {
                "cxsmiles": "",
                "substituent_table": {},
                "caption": "",
                "source_image_path": image_path or "",
                "score": 0.0,
                "is_markush": True,
            },
            "fused_match": {"r_group_matching": {}},
            "requirements": None,
            "llm_outputs": {},
            "report": raw_result.get("reasoning") or raw_result.get("judgment_zh") or "",
        }

    result.setdefault("patent_id", record_input.get("patent_id"))
    result.setdefault("target_smiles", record_input.get("smiles"))
    result.setdefault("confidence", raw_result.get("confidence") or "unknown")
    result.setdefault("report", raw_result.get("reasoning") or "")
    result.setdefault("fused_match", {"r_group_matching": {}})
    if result.get("is_conclusive") is None:
        result["is_conclusive"] = True
    if not result.get("analysis_status"):
        result["analysis_status"] = (
            "protected" if result.get("is_protected") else "not_protected"
        )
    if image_path and not result.get("markush_structure"):
        result["markush_structure"] = {
            "cxsmiles": "",
            "substituent_table": {},
            "caption": "",
            "source_image_path": image_path,
            "score": 0.0,
            "is_markush": True,
        }
    result.setdefault("llm_outputs", {})
    result["llm_outputs"]["loaded_previous_record"] = {
        "model": record.get("model"),
        "elapsed_sec": record.get("elapsed_sec"),
    }
    if image_selection:
        result["llm_outputs"]["markush_image_selection"] = image_selection
    return result


def _loaded_step_outputs(record: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    now = _utc_now()
    record_input = _record_input(record)
    image = record.get("image") if isinstance(record.get("image"), dict) else {}
    text = record.get("text") if isinstance(record.get("text"), dict) else {}
    image_selection = (
        record.get("image_selection")
        or result.get("llm_outputs", {}).get("markush_image_selection")
    )
    llm_outputs = result.get("llm_outputs") if isinstance(result.get("llm_outputs"), dict) else {}
    fused_match = result.get("fused_match") if isinstance(result.get("fused_match"), dict) else {}
    requirements = result.get("requirements")
    report = result.get("report")
    outputs_by_key = {
        "fetch": {
            "summary": f"Loaded cached result for {record_input.get('patent_id')}.",
            "data": {
                "patent_id": record_input.get("patent_id"),
                "claims_text_path": text.get("path"),
                "text_chars": text.get("chars"),
                "source": record.get("source"),
            },
        },
        "markush": {
            "summary": "Loaded selected Markush image and extraction context.",
            "data": {
                "image": image,
                "image_selection": image_selection,
                "markush_structure": result.get("markush_structure"),
                "llm_response": llm_outputs.get("llm_markush_extraction"),
            },
        },
        "claim": {
            "summary": "Loaded claim-analysis evidence from the previous result.",
            "data": {
                "claim_analysis": llm_outputs.get("claim_analysis")
                or result.get("claim_analysis")
                or "历史记录未保存独立的权利要求解析输出，最终结论已包含该步骤结果。",
            },
        },
        "llm_match": {
            "summary": "Loaded molecule matching evidence from the previous result.",
            "data": {
                "target_smiles": result.get("target_smiles"),
                "r_group_matching": fused_match.get("r_group_matching"),
                "substructure_match": llm_outputs.get("llm_substructure_match")
                or result.get("substructure_match"),
            },
        },
        "fusion": {
            "summary": "Loaded fused matching judgment from the previous result.",
            "data": {
                "fused_match": fused_match,
                "is_protected": result.get("is_protected"),
                "analysis_status": result.get("analysis_status"),
            },
        },
        "alignment": {
            "summary": "Loaded R-group alignment evidence from the previous result.",
            "data": {
                "alignment": llm_outputs.get("r_group_alignment") or result.get("alignment"),
                "r_group_matching": fused_match.get("r_group_matching"),
            },
        },
        "requirements": {
            "summary": "Loaded protection-scope judgment from the previous result.",
            "data": {
                "requirements": requirements,
                "analysis_status": result.get("analysis_status"),
                "confidence": result.get("confidence"),
            },
        },
        "report": {
            "summary": "Loaded previous successful final judgment.",
            "data": {
                "analysis_status": result.get("analysis_status"),
                "confidence": result.get("confidence"),
                "report": report,
            },
        },
    }
    outputs: list[dict[str, Any]] = []
    for step_index, blueprint in enumerate(PIPELINE_BLUEPRINTS["infringement"], start=1):
        payload = outputs_by_key.get(blueprint["key"], {})
        outputs.append(
            {
                "step": step_index,
                "agent_key": blueprint["key"],
                "title": f"Loaded {blueprint['name']}",
                "summary": payload.get("summary") or "Loaded from previous successful result.",
                "data": payload.get("data") or {"message": "历史记录未保存该步骤的独立输出。"},
                "timestamp": now,
            }
        )
    return outputs


def _loaded_patentability_step_output(record: dict[str, Any], patentability: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": len(PIPELINE_BLUEPRINTS["infringement"]) + 1,
        "agent_key": PATENTABILITY_AS_INFRINGEMENT_NODE["key"],
        "title": "Loaded 可授权分析",
        "summary": "Loaded previous successful patentability analysis.",
        "data": patentability,
        "timestamp": _utc_now(),
    }


def _json_block(value: Any) -> str:
    return json.dumps(_serialize(value), ensure_ascii=False, indent=2)


def _image_paths_from_result(result: dict[str, Any]) -> list[str]:
    llm_outputs = result.get("llm_outputs") if isinstance(result.get("llm_outputs"), dict) else {}
    image_selection = (
        llm_outputs.get("markush_image_selection")
        if isinstance(llm_outputs.get("markush_image_selection"), dict)
        else {}
    )
    markush = (
        result.get("markush_structure")
        if isinstance(result.get("markush_structure"), dict)
        else {}
    )
    candidates = [
        markush.get("source_image_path"),
        (image_selection.get("selected") or {}).get("image_path")
        if isinstance(image_selection.get("selected"), dict)
        else None,
        (llm_outputs.get("llm_markush_extraction") or {}).get("image_path")
        if isinstance(llm_outputs.get("llm_markush_extraction"), dict)
        else None,
    ]
    for item in image_selection.get("evaluations") or []:
        if isinstance(item, dict):
            candidates.append(item.get("image_path"))
    return _unique_image_paths(candidates)


def _image_paths_from_step(output: dict[str, Any]) -> list[str]:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    image_selection = (
        data.get("image_selection")
        if isinstance(data.get("image_selection"), dict)
        else {}
    )
    markush = (
        data.get("markush_structure")
        if isinstance(data.get("markush_structure"), dict)
        else {}
    )
    llm_response = (
        data.get("llm_response") if isinstance(data.get("llm_response"), dict) else {}
    )
    image = data.get("image") if isinstance(data.get("image"), dict) else {}
    candidates = [
        data.get("image_path"),
        image.get("path"),
        (image_selection.get("selected") or {}).get("image_path")
        if isinstance(image_selection.get("selected"), dict)
        else None,
        markush.get("source_image_path"),
        llm_response.get("image_path"),
        llm_response.get("source_image_path"),
    ]
    for item in image_selection.get("evaluations") or []:
        if isinstance(item, dict):
            candidates.append(item.get("image_path"))
    return _unique_image_paths(candidates)


def _unique_image_paths(candidates: list[Any]) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        suffix = Path(candidate.split("?", 1)[0]).suffix.lower()
        if suffix not in IMAGE_SUFFIXES or candidate in seen:
            continue
        seen.add(candidate)
        paths.append(candidate)
    return paths


def _markdown_image(path: str, label: str) -> str:
    try:
        image_path = _resolve_public_file(path)
        media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        image_url = f"data:{media_type};base64,{encoded}"
    except Exception:
        image_url = f"/api/files?path={quote(path)}"
    return (
        f"![{label}]({image_url})\n\n"
        f"`{path}`"
    )


def _analysis_conclusion(result: dict[str, Any]) -> str:
    status = result.get("analysis_status")
    is_conclusive = result.get("is_conclusive") is not False
    if not is_conclusive:
        judgment = "无法判断"
    elif result.get("is_protected") is True:
        judgment = "落入保护范围"
    elif result.get("is_protected") is False:
        judgment = "未落入保护范围"
    else:
        judgment = status or "未知"
    return (
        f"- 结论：{judgment}\n"
        f"- 分析状态：{status or '-'}\n"
        f"- 置信度：{result.get('confidence') or '-'}"
    )


def _write_infringement_markdown(job: dict[str, Any]) -> Path:
    if job.get("mode") != "infringement" or not isinstance(job.get("result"), dict):
        raise HTTPException(status_code=400, detail="markdown report is only available for infringement jobs")

    result = job["result"]
    output_path = REPORT_DIR / f"{job['id']}.infringement_report.md"
    lines = [
        "# 侵权分析报告",
        "",
        "## 最终结论",
        "",
        _analysis_conclusion(result),
        "",
        "## 相关分析及证据",
        "",
    ]

    if result.get("report"):
        lines.extend(["### 分析/证据1", "", result.get("report") or "", ""])

    r_group_matching = (
        result.get("fused_match", {}).get("r_group_matching")
        if isinstance(result.get("fused_match"), dict)
        else None
    )
    if r_group_matching:
        lines.extend(["### 分析/证据2", "", "R-group 映射：", "", "```json", _json_block(r_group_matching), "```", ""])

    if result.get("failure_reason"):
        lines.extend(["### 分析/证据3", "", str(result.get("failure_reason")), ""])

    image_paths = _image_paths_from_result(result)
    if image_paths:
        lines.extend(["## 报告图片", ""])
        for index, image_path in enumerate(image_paths, start=1):
            lines.extend([_markdown_image(image_path, f"report-image-{index}"), ""])

    output_path.write_text("\n".join(lines), encoding="utf-8-sig")
    return output_path


def _patentability_conclusion(result: dict[str, Any]) -> str:
    success = (
        result.get("success_analysis")
        if isinstance(result.get("success_analysis"), dict)
        else {}
    )
    proposed = (
        result.get("proposed_structure")
        if isinstance(result.get("proposed_structure"), dict)
        else {}
    )
    return (
        f"- 新颖性评分：{result.get('novelty_score') if result.get('novelty_score') is not None else '-'}\n"
        f"- 授权可能性：{success.get('success_rate_estimation') or '-'}"
    )


def _write_patentability_markdown(job: dict[str, Any]) -> Path:
    if job.get("mode") != "patentability" or not isinstance(job.get("result"), dict):
        raise HTTPException(status_code=400, detail="markdown report is only available for patentability jobs")

    result = job["result"]
    success = (
        result.get("success_analysis")
        if isinstance(result.get("success_analysis"), dict)
        else {}
    )
    output_path = REPORT_DIR / f"{job['id']}.patentability_report.md"
    lines = [
        "# 可授权分析报告",
        "",
        "## 一.最终结论",
        "",
        _patentability_conclusion(result),
        "",
        "## 二.相关分析及证据",
        "",
        "### 分析/证据1",
        "",
        result.get("report") or success.get("comprehensive_report") or "无报告内容",
        "",
    ]

    evidence_index = 2
    prior_arts = result.get("prior_arts") if isinstance(result.get("prior_arts"), list) else []
    if prior_arts:
        lines.extend([f"### 分析/证据{evidence_index}", "", "相关现有技术：", ""])
        for item in prior_arts:
            if isinstance(item, dict):
                lines.append(f"- {item.get('patent_id') or item}")
            else:
                lines.append(f"- {item}")
        lines.append("")
        evidence_index += 1

    risk_points = result.get("risk_points") if isinstance(result.get("risk_points"), list) else []
    if risk_points:
        lines.extend([f"### 分析/证据{evidence_index}", "", "风险点：", ""])
        lines.extend([f"- {item}" for item in risk_points])
        lines.append("")
        evidence_index += 1

    suggestions = result.get("suggestions") if isinstance(result.get("suggestions"), list) else []
    success_suggestions = (
        success.get("improvement_suggestions")
        if isinstance(success.get("improvement_suggestions"), list)
        else []
    )
    suggestions = suggestions or success_suggestions
    if suggestions:
        lines.extend([f"### 分析/证据{evidence_index}", "", "改进建议：", ""])
        lines.extend([f"- {item}" for item in suggestions])
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8-sig")
    return output_path


def _report_job_view(job: dict[str, Any], report_type: str) -> dict[str, Any]:
    report_type = report_type.strip().lower()
    if report_type not in {"infringement", "patentability"}:
        raise HTTPException(status_code=404, detail="unknown report type")

    mode = job.get("mode")
    result = job.get("result")
    if mode == "infringement_patentability":
        if not isinstance(result, dict) or not isinstance(result.get(report_type), dict):
            raise HTTPException(status_code=400, detail=f"{report_type} report is not ready")
        def is_patentability_output(output: dict[str, Any]) -> bool:
            agent_key = str(output.get("agent_key") or "")
            return agent_key == PATENTABILITY_AS_INFRINGEMENT_NODE["key"] or agent_key.startswith(
                "patentability_"
            )

        step_outputs = [
            output
            for output in job.get("step_outputs") or []
            if isinstance(output, dict)
            and (
                is_patentability_output(output)
                if report_type == "patentability"
                else not is_patentability_output(output)
            )
        ]
        return {
            **job,
            "mode": report_type,
            "result": result[report_type],
            "step_outputs": step_outputs,
            "id": f"{job['id']}.{report_type}",
        }

    if mode != report_type:
        raise HTTPException(status_code=400, detail=f"{report_type} report is not available for this job")
    return job


def _write_job_markdown(job: dict[str, Any], report_type: str) -> Path:
    report_job = _report_job_view(job, report_type)
    if report_type == "infringement":
        return _write_infringement_markdown(report_job)
    return _write_patentability_markdown(report_job)


def _report_image_paths(job: dict[str, Any]) -> list[str]:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    candidates = _image_paths_from_result(result)
    for output in job.get("step_outputs") or []:
        if isinstance(output, dict):
            candidates.extend(_image_paths_from_step(output))
    return _unique_image_paths(candidates)


def _plain_report_lines(markdown_text: str) -> list[str]:
    lines: list[str] = []
    skip_next_path = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if line.startswith("!["):
            skip_next_path = True
            continue
        if skip_next_path and line.startswith("`") and line.endswith("`"):
            skip_next_path = False
            continue
        skip_next_path = False
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*]\s+", "• ", line)
        line = line.replace("`", "").replace("**", "")
        lines.append(line)
    return lines


def _pdf_font(size: int):
    from PIL import ImageFont

    candidates = [
        Path(os.environ["MARKUSH_PDF_FONT"]) if os.environ.get("MARKUSH_PDF_FONT") else None,
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_pdf_line(text: str, font: Any, max_width: int, draw: Any) -> list[str]:
    if not text:
        return [""]
    chunks: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
            continue
        chunks.append(current)
        current = char
    if current:
        chunks.append(current)
    return chunks


def _write_job_pdf(job: dict[str, Any], report_type: str) -> Path:
    from PIL import Image, ImageDraw

    report_job = _report_job_view(job, report_type)
    markdown_path = _write_job_markdown(job, report_type)
    output_path = markdown_path.with_suffix(".pdf")
    page_size = (1240, 1754)
    margin = 92
    body_font = _pdf_font(26)
    title_font = _pdf_font(34)
    small_font = _pdf_font(20)
    line_height = 40

    pages: list[Any] = []

    def new_page() -> tuple[Any, Any, int]:
        page = Image.new("RGB", page_size, "white")
        return page, ImageDraw.Draw(page), margin

    page, draw, y = new_page()
    max_width = page_size[0] - margin * 2
    for raw_line in _plain_report_lines(markdown_path.read_text(encoding="utf-8-sig")):
        font = title_font if raw_line and not raw_line.startswith(("•", "  ")) and len(raw_line) < 24 else body_font
        wrapped = _wrap_pdf_line(raw_line, font, max_width, draw)
        needed = max(line_height, len(wrapped) * line_height)
        if y + needed > page_size[1] - margin:
            pages.append(page)
            page, draw, y = new_page()
        for line in wrapped:
            draw.text((margin, y), line, fill="#111111", font=font)
            y += line_height
        if not raw_line:
            y += 10

    for image_path in _report_image_paths(report_job):
        try:
            source = Image.open(_resolve_public_file(image_path)).convert("RGB")
        except Exception:
            continue
        source.thumbnail((max_width, page_size[1] - margin * 2), Image.LANCZOS)
        needed = source.height + 72
        if y + needed > page_size[1] - margin:
            pages.append(page)
            page, draw, y = new_page()
        draw.text((margin, y), Path(image_path).name, fill="#555555", font=small_font)
        y += 34
        page.paste(source, (margin, y))
        y += source.height + 36

    pages.append(page)
    pages[0].save(output_path, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return output_path


def _llm_settings_dict(settings: Optional[LLMSettings | dict[str, Any]]) -> dict[str, str]:
    raw = (
        settings.model_dump()
        if isinstance(settings, LLMSettings)
        else dict(settings or {})
    )
    selected_model = str(raw.get("model") or DEFAULT_LLM_MODEL).strip()
    profile = _llm_profile_for_model(selected_model)
    model = str(profile.get("model") or _canonical_ui_model_name(selected_model)).strip()
    uses_gpt_defaults = _uses_gpt_reasoning_defaults(model)
    return {
        "provider": str(raw.get("provider") or profile.get("provider") or DEFAULT_LLM_PROVIDER).strip()
        or DEFAULT_LLM_PROVIDER,
        "model": model,
        "base_url": str(raw.get("base_url") or profile.get("base_url") or DEFAULT_LLM_BASE_URL).strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
        "api_key_env": str(raw.get("api_key_env") or profile.get("api_key_env") or DEFAULT_LLM_API_KEY_ENV).strip(),
        "max_tokens": profile.get("max_tokens") or DEFAULT_GPT_MAX_TOKENS,
        "request_timeout": profile.get("request_timeout") or DEFAULT_GPT_REQUEST_TIMEOUT,
        "token_limit_param": (
            profile.get("token_limit_param")
            or (DEFAULT_GPT_TOKEN_LIMIT_PARAM if uses_gpt_defaults else "max_tokens")
        ),
        "omit_temperature": profile.get(
            "omit_temperature",
            DEFAULT_GPT_OMIT_TEMPERATURE if uses_gpt_defaults else False,
        ),
        "reasoning_effort": profile.get("reasoning_effort")
        or (DEFAULT_GPT_REASONING_EFFORT if uses_gpt_defaults else ""),
        "verbosity": profile.get("verbosity")
        or (DEFAULT_GPT_VERBOSITY if uses_gpt_defaults else ""),
    }


def _public_llm_settings(settings: dict[str, str]) -> dict[str, Any]:
    api_key_env = settings.get("api_key_env") or DEFAULT_LLM_API_KEY_ENV
    return {
        "provider": settings.get("provider") or "openai",
        "model": settings.get("model") or None,
        "api_key_configured": bool(
            settings.get("api_key") or os.environ.get(api_key_env)
        ),
        "max_tokens": settings.get("max_tokens") or DEFAULT_GPT_MAX_TOKENS,
        "request_timeout": settings.get("request_timeout") or DEFAULT_GPT_REQUEST_TIMEOUT,
        "token_limit_param": settings.get("token_limit_param") or DEFAULT_GPT_TOKEN_LIMIT_PARAM,
        "omit_temperature": settings.get("omit_temperature"),
        "reasoning_effort": settings.get("reasoning_effort") or None,
        "verbosity": settings.get("verbosity") or None,
    }


def _llm_pipeline_kwargs(settings: dict[str, str]) -> dict[str, Optional[str]]:
    return {
        "llm_provider": settings.get("provider") or None,
        "llm_model": settings.get("model") or None,
        "llm_base_url": settings.get("base_url") or None,
        "llm_api_key": settings.get("api_key") or None,
        "llm_api_key_env": settings.get("api_key_env") or DEFAULT_LLM_API_KEY_ENV,
        "llm_request_timeout": settings.get("request_timeout") or DEFAULT_GPT_REQUEST_TIMEOUT,
        "llm_max_tokens": settings.get("max_tokens") or DEFAULT_GPT_MAX_TOKENS,
        "llm_temperature": None,
        "llm_token_limit_param": settings.get("token_limit_param")
        or DEFAULT_GPT_TOKEN_LIMIT_PARAM,
        "llm_omit_temperature": settings.get("omit_temperature"),
        "llm_reasoning_effort": settings.get("reasoning_effort") or None,
        "llm_verbosity": settings.get("verbosity") or None,
    }


def _format_event(raw_event: dict[str, Any], mode: str) -> dict[str, Any]:
    event = {
        "timestamp": _utc_now(),
        "level": raw_event.get("level", "info"),
        "message": raw_event.get("message", ""),
        "step": raw_event.get("step"),
        "total_steps": raw_event.get("total_steps"),
    }
    step = raw_event.get("step")
    if isinstance(step, int):
        blueprint = PIPELINE_BLUEPRINTS.get(mode, [])
        if 1 <= step <= len(blueprint):
            event["agent"] = blueprint[step - 1]["name"]
            event["agent_key"] = blueprint[step - 1]["key"]
    return event


def _build_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    events = job["events"]
    mode = job["mode"]
    blueprint = PIPELINE_BLUEPRINTS[mode]
    completed_steps = 0
    active_key = None
    current_step = None
    for event in events:
        if event["level"] == "step" and isinstance(event.get("step"), int):
            completed_steps = max(completed_steps, event["step"] - 1)
            current_step = event["step"]
            active_key = event.get("agent_key")
    if job["status"] == "succeeded":
        completed_steps = len(blueprint)
        active_key = None

    agents = []
    for idx, item in enumerate(blueprint, start=1):
        if job["status"] == "failed" and current_step is not None and idx == current_step:
            status = "active"
        elif job["status"] == "failed" and idx <= completed_steps:
            status = "done"
        elif idx <= completed_steps:
            status = "done"
        elif item["key"] == active_key and job["status"] == "running":
            status = "active"
        elif job["status"] == "succeeded":
            status = "done"
        else:
            status = "pending"
        agents.append({**item, "order": idx, "status": status})

    return {
        "id": job["id"],
        "mode": mode,
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "payload": job["payload"],
        "agents": agents,
        "events": events[-20:],
        "event_count": len(events),
        "step_outputs": job["step_outputs"],
        "result": job["result"],
        "error": job["error"],
    }


def _run_infringement(job_id: str, payload: dict[str, Any]) -> None:
    def stop_if_requested() -> None:
        if JOBS.is_cancel_requested(job_id):
            raise JobStopped()

    def record_step(output: dict[str, Any]) -> None:
        stop_if_requested()
        JOBS.append_step_output(job_id, _serialize(output))
        stop_if_requested()

    stop_if_requested()
    pipeline = LLMInfringementPipeline(
        CONFIG,
        **_llm_pipeline_kwargs(payload.get("llm", {})),
        step_output_callback=record_step,
    )
    result = pipeline.run(
        patent_id=payload["patent_id"],
        target_smiles=payload["smiles"],
        markush_caption=payload.get("caption"),
    )
    stop_if_requested()
    serialized = _serialize(result)
    if serialized.get("analysis_status") == "failed":
        JOBS.update(
            job_id,
            status="failed",
            result=serialized,
            error={
                "message": serialized.get("failure_reason")
                or serialized.get("report")
                or "Infringement analysis failed.",
            },
        )
        return
    JOBS.update(job_id, status="succeeded", result=serialized)
    _persist_ui_infringement_result(job_id, serialized)


def _run_patentability(job_id: str, payload: dict[str, Any]) -> None:
    def stop_if_requested() -> None:
        if JOBS.is_cancel_requested(job_id):
            raise JobStopped()

    def record_step(output: dict[str, Any]) -> None:
        stop_if_requested()
        JOBS.append_step_output(job_id, _serialize(output))
        stop_if_requested()

    stop_if_requested()
    pipeline = LLMPatentabilityPipeline(
        CONFIG,
        **_llm_pipeline_kwargs(payload.get("llm", {})),
        step_output_callback=record_step,
    )
    result = pipeline.run(
        proposed_cxsmiles=payload.get("cxsmiles"),
        proposed_image_path=payload.get("image_path"),
        tech_domain=payload.get("domain", ""),
        known_prior_art_ids=payload.get("prior_arts") or None,
    )
    stop_if_requested()
    JOBS.update(job_id, status="succeeded", result=_serialize(result))


def _run_infringement_patentability(job_id: str, payload: dict[str, Any]) -> None:
    def stop_if_requested() -> None:
        if JOBS.is_cancel_requested(job_id):
            raise JobStopped()

    def record_infringement_step(output: dict[str, Any]) -> None:
        stop_if_requested()
        JOBS.append_step_output(job_id, _serialize(output))
        stop_if_requested()

    stop_if_requested()
    infringement_pipeline = LLMInfringementPipeline(
        CONFIG,
        **_llm_pipeline_kwargs(payload.get("llm", {})),
        step_output_callback=record_infringement_step,
    )
    infringement_result = infringement_pipeline.run(
        patent_id=payload["patent_id"],
        target_smiles=payload["smiles"],
        markush_caption=payload.get("caption"),
    )
    stop_if_requested()
    serialized_infringement = _serialize(infringement_result)
    combined_result = {
        "infringement": serialized_infringement,
        "patentability": None,
    }
    if serialized_infringement.get("analysis_status") == "failed":
        JOBS.update(
            job_id,
            status="failed",
            result=combined_result,
            error={
                "message": serialized_infringement.get("failure_reason")
                or serialized_infringement.get("report")
                or "Infringement analysis failed.",
            },
        )
        return

    JOBS.update(job_id, result=combined_result)

    offset = len(PIPELINE_BLUEPRINTS["infringement"])
    payload["_event_step_offset"] = offset

    def record_patentability_step(output: dict[str, Any]) -> None:
        stop_if_requested()
        adjusted = _serialize(output)
        original_title = adjusted.get("title") or adjusted.get("agent_key") or "可授权分析"
        adjusted["step"] = offset + 1
        adjusted["agent_key"] = PATENTABILITY_AS_INFRINGEMENT_NODE["key"]
        adjusted["title"] = PATENTABILITY_AS_INFRINGEMENT_NODE["name"]
        adjusted["summary"] = f"可授权分析进展：{original_title}"
        JOBS.append_step_output(job_id, adjusted)
        stop_if_requested()

    stop_if_requested()
    patentability_pipeline = LLMPatentabilityPipeline(
        CONFIG,
        **_llm_pipeline_kwargs(payload.get("llm", {})),
        step_output_callback=record_patentability_step,
    )
    patentability_result = patentability_pipeline.run(
        proposed_cxsmiles=serialized_infringement.get("target_smiles") or payload["smiles"],
        proposed_image_path=None,
        tech_domain=payload.get("domain", ""),
        known_prior_art_ids=[payload["patent_id"]],
    )
    stop_if_requested()
    combined_result["patentability"] = _serialize(patentability_result)
    JOBS.update(job_id, status="succeeded", result=combined_result)
    _persist_ui_infringement_result(job_id, combined_result)


def _event_with_payload_offset(raw_event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    offset = int(payload.get("_event_step_offset") or 0)
    if not offset or not isinstance(raw_event.get("step"), int):
        if raw_event.get("level") == "step":
            raw_event = dict(raw_event)
            raw_event["total_steps"] = len(PIPELINE_BLUEPRINTS["infringement_patentability"])
        return raw_event
    adjusted = dict(raw_event)
    adjusted["step"] = offset + 1
    adjusted["total_steps"] = len(PIPELINE_BLUEPRINTS["infringement_patentability"])
    return adjusted


def _launch_job(
    job_id: str,
    runner,
    payload: dict[str, Any],
    mode: str,
    event_transform=None,
) -> None:
    def worker() -> None:
        JOBS.update(job_id, status="running")

        def listener(raw_event: dict[str, Any]) -> None:
            if event_transform is not None:
                raw_event = event_transform(raw_event)
            JOBS.append_event(job_id, _format_event(raw_event, mode))

        remove_listener = log.add_listener(listener)
        JOBS.append_event(
            job_id,
            {
                "timestamp": _utc_now(),
                "level": "info",
                "message": "LLM-only pipeline task accepted.",
            },
        )
        start = time.time()
        try:
            runner(job_id, payload)
            current = JOBS.get(job_id)
            finished_message = (
                f"Pipeline stopped in {time.time() - start:.1f}s."
                if current.get("status") in {"failed", "cancelled"}
                else f"Pipeline finished in {time.time() - start:.1f}s."
            )
            JOBS.append_event(
                job_id,
                {
                    "timestamp": _utc_now(),
                    "level": "info",
                    "message": finished_message,
                },
            )
        except JobStopped:
            JOBS.update(
                job_id,
                status="cancelled",
                error={"message": "用户已手动停止任务。"},
            )
            JOBS.append_event(
                job_id,
                {
                    "timestamp": _utc_now(),
                    "level": "warning",
                    "message": f"Pipeline stopped by user after {time.time() - start:.1f}s.",
                },
            )
        except Exception as exc:
            if JOBS.is_cancel_requested(job_id):
                JOBS.update(
                    job_id,
                    status="cancelled",
                    error={"message": "用户已手动停止任务。"},
                )
                JOBS.append_event(
                    job_id,
                    {
                        "timestamp": _utc_now(),
                        "level": "warning",
                        "message": f"Pipeline stopped by user after {time.time() - start:.1f}s.",
                    },
                )
                return
            JOBS.update(
                job_id,
                status="failed",
                error={
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            JOBS.append_event(
                job_id,
                {
                    "timestamp": _utc_now(),
                    "level": "error",
                    "message": f"Pipeline failed: {exc}",
                },
            )
        finally:
            remove_listener()

    threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "workflow": "llm-only"}


@app.get("/api/blueprints")
def blueprints() -> dict[str, Any]:
    return {
        mode: [
            {**item, "order": index, "status": "pending"}
            for index, item in enumerate(items, start=1)
        ]
        for mode, items in PIPELINE_BLUEPRINTS.items()
    }


@app.get("/api/llm-defaults")
def llm_defaults() -> dict[str, Any]:
    return {
        "provider": DEFAULT_LLM_PROVIDER,
        "model": DEFAULT_LLM_MODEL,
        "model_options": LLM_MODEL_OPTIONS,
        "api_key_configured": any(
            bool(
                os.environ.get(
                    (_llm_profile_for_model(option["value"]) or {}).get("api_key_env")
                    or DEFAULT_LLM_API_KEY_ENV
                )
            )
            for option in LLM_MODEL_OPTIONS
        ),
        "max_tokens": DEFAULT_GPT_MAX_TOKENS,
        "request_timeout": DEFAULT_GPT_REQUEST_TIMEOUT,
        "token_limit_param": DEFAULT_GPT_TOKEN_LIMIT_PARAM,
        "omit_temperature": DEFAULT_GPT_OMIT_TEMPERATURE,
        "reasoning_effort": DEFAULT_GPT_REASONING_EFFORT,
        "verbosity": DEFAULT_GPT_VERBOSITY,
    }


@app.post("/api/infringement")
def submit_infringement(payload: InfringementPayload) -> dict[str, Any]:
    llm_settings = _llm_settings_dict(payload.llm)
    include_patentability = bool(payload.include_patentability)
    evaluation_name = _normalize_evaluation_name(payload.evaluation_name)
    stored_payload = {
        "evaluation_name": evaluation_name or None,
        "patent_id": payload.patent_id.strip(),
        "smiles": payload.smiles.strip(),
        "caption": (payload.caption or "").strip() or None,
        "include_patentability": include_patentability,
        "llm": _public_llm_settings(llm_settings),
    }
    runner_payload = {
        **stored_payload,
        "llm": llm_settings,
    }
    if include_patentability:
        job = JOBS.create("infringement_patentability", stored_payload, runner_payload)
        _launch_job(
            job["id"],
            _run_infringement_patentability,
            runner_payload,
            "infringement_patentability",
            event_transform=lambda raw: _event_with_payload_offset(raw, runner_payload),
        )
    else:
        job = JOBS.create("infringement", stored_payload, runner_payload)
        _launch_job(job["id"], _run_infringement, runner_payload, "infringement")
    return {"job_id": job["id"]}


@app.post("/api/infringement/previous-results")
def previous_infringement_results(payload: InfringementPayload) -> dict[str, Any]:
    evaluation_name = _normalize_evaluation_name(payload.evaluation_name)
    patent_id = payload.patent_id.strip()
    smiles = payload.smiles.strip()
    if not evaluation_name and (not patent_id or not smiles):
        raise HTTPException(
            status_code=400,
            detail="evaluation_name or both patent_id and smiles are required",
        )

    matches = _iter_previous_infringement_results(patent_id, smiles, evaluation_name)
    if payload.include_patentability:
        matches = [match for match in matches if _record_has_patentability_result(match["record"])]
    return {
        "candidates": [_previous_result_candidate(match) for match in matches],
        "count": len(matches),
    }


@app.post("/api/infringement/load-previous")
def load_previous_infringement(payload: InfringementPayload) -> dict[str, Any]:
    evaluation_name = _normalize_evaluation_name(payload.evaluation_name)
    patent_id = payload.patent_id.strip()
    smiles = payload.smiles.strip()
    if not evaluation_name and (not patent_id or not smiles):
        raise HTTPException(
            status_code=400,
            detail="evaluation_name or both patent_id and smiles are required",
        )

    match = _find_previous_infringement_result(
        patent_id,
        smiles,
        evaluation_name=evaluation_name,
        result_id=payload.previous_result_id,
    )
    if match is None:
        raise HTTPException(status_code=404, detail="no previous successful result found")

    llm_settings = _llm_settings_dict(payload.llm)
    record_input = _record_input(match["record"])
    stored_payload = {
        "evaluation_name": evaluation_name
        or _normalize_evaluation_name(record_input.get("evaluation_name"))
        or None,
        "patent_id": patent_id or str(record_input.get("patent_id") or "").strip(),
        "smiles": smiles or str(record_input.get("smiles") or "").strip(),
        "caption": (payload.caption or "").strip() or None,
        "llm": _public_llm_settings(llm_settings),
        "loaded_from": str(match["path"]) if match.get("path") else "current-session",
    }
    result = _normalize_loaded_infringement_record(match["record"])
    raw_record_result = (
        match["record"].get("result")
        if isinstance(match["record"].get("result"), dict)
        else {}
    )
    patentability_result = (
        raw_record_result.get("patentability")
        if isinstance(raw_record_result.get("patentability"), dict)
        else None
    )
    if payload.include_patentability and not patentability_result:
        raise HTTPException(
            status_code=404,
            detail="selected previous result does not include patentability analysis",
        )
    load_combined = bool(payload.include_patentability and patentability_result)
    mode = "infringement_patentability" if load_combined else "infringement"
    job = JOBS.create(mode, stored_payload)
    for output in _loaded_step_outputs(match["record"], result):
        JOBS.append_step_output(job["id"], _serialize(output))
    if load_combined:
        JOBS.append_step_output(
            job["id"],
            _serialize(_loaded_patentability_step_output(match["record"], patentability_result)),
        )
    JOBS.append_event(
        job["id"],
        {
            "timestamp": _utc_now(),
            "level": "info",
            "message": (
                f"Loaded previous successful result from {match['path'].name}."
                if match.get("path")
                else "Loaded previous successful result from current session."
            ),
        },
    )
    loaded_result = (
        {"infringement": result, "patentability": patentability_result}
        if load_combined
        else result
    )
    JOBS.update(job["id"], status="succeeded", result=_serialize(loaded_result))
    return {
        "job_id": job["id"],
        "source": str(match["path"]) if match.get("path") else "current-session",
        "mode": mode,
    }


@app.post("/api/patentability")
async def submit_patentability(
    cxsmiles: Optional[str] = Form(default=None),
    domain: str = Form(default=""),
    prior_arts: str = Form(default=""),
    image: Optional[UploadFile] = File(default=None),
    llm_provider: str = Form(default=DEFAULT_LLM_PROVIDER),
    llm_model: str = Form(default=""),
    llm_base_url: str = Form(default=""),
    llm_api_key: str = Form(default=""),
    llm_api_key_env: str = Form(default=DEFAULT_LLM_API_KEY_ENV),
) -> dict[str, Any]:
    cxsmiles = (cxsmiles or "").strip()
    domain = domain.strip()
    prior_art_ids = [item.strip() for item in prior_arts.split(",") if item.strip()]
    llm_settings = _llm_settings_dict(
        {
            "provider": llm_provider,
            "model": llm_model,
            "base_url": llm_base_url,
            "api_key": llm_api_key,
            "api_key_env": llm_api_key_env,
        }
    )

    image_path = None
    image_name = None
    if image and image.filename:
        suffix = Path(image.filename).suffix or ".png"
        target = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        with target.open("wb") as fh:
            fh.write(await image.read())
        image_path = str(target)
        image_name = image.filename

    if not cxsmiles and not image_path:
        raise HTTPException(status_code=400, detail="cxsmiles or image is required")

    stored_payload = {
        "cxsmiles": cxsmiles or None,
        "domain": domain,
        "prior_arts": prior_art_ids,
        "image_path": image_path,
        "image_name": image_name,
        "llm": _public_llm_settings(llm_settings),
    }
    runner_payload = {
        **stored_payload,
        "llm": llm_settings,
    }
    job = JOBS.create("patentability", stored_payload, runner_payload)
    _launch_job(job["id"], _run_patentability, runner_payload, "patentability")
    return {"job_id": job["id"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    return JSONResponse(_build_snapshot(job))


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str) -> dict[str, Any]:
    try:
        job = JOBS.request_cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if job.get("status") in {"succeeded", "failed", "cancelled"} and (job.get("error") or {}).get(
        "message"
    ) != "用户已手动停止任务。":
        return {"job_id": job_id, "status": job.get("status")}
    JOBS.append_event(
        job_id,
        {
            "timestamp": _utc_now(),
            "level": "warning",
            "message": "用户手动停止了任务。",
        },
    )
    return {"job_id": job_id, "status": job.get("status", "cancelled")}


@app.post("/api/jobs/{job_id}/rerun-step")
def rerun_step(job_id: str, payload: StepRerunPayload) -> dict[str, Any]:
    try:
        source_job = JOBS.get(job_id)
        runner_payload = JOBS.get_runner_payload(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc

    mode = source_job["mode"]
    if mode == "infringement_patentability":
        raise HTTPException(status_code=400, detail="step rerun is not available for chained jobs")
    blueprint = PIPELINE_BLUEPRINTS.get(mode, [])
    step_index = next(
        (
            index
            for index, item in enumerate(blueprint, start=1)
            if item["key"] == payload.agent_key
        ),
        None,
    )
    step = blueprint[step_index - 1] if step_index is not None else None
    if step is None:
        raise HTTPException(status_code=400, detail="unknown step for this job mode")

    rerun_meta = {
        "source_job_id": job_id,
        "agent_key": payload.agent_key,
        "step_name": step["name"],
    }
    stored_payload = {**source_job["payload"], "rerun": rerun_meta}
    new_runner_payload = {**runner_payload, "rerun": rerun_meta}
    new_job = JOBS.create(mode, stored_payload, new_runner_payload)
    JOBS.append_event(
        new_job["id"],
        {
            "timestamp": _utc_now(),
            "level": "info",
            "message": f"Step rerun requested: {step['name']}.",
            "step": step_index,
            "total_steps": len(blueprint),
        },
    )
    runner = _run_infringement if mode == "infringement" else _run_patentability
    _launch_job(new_job["id"], runner, new_runner_payload, mode)
    return {
        "job_id": new_job["id"],
        "mode": mode,
        "step_key": payload.agent_key,
        "step_name": step["name"],
    }


@app.get("/api/jobs/{job_id}/report.md")
def download_job_markdown(job_id: str) -> FileResponse:
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    report_type = "patentability" if job.get("mode") == "patentability" else "infringement"
    report_path = _write_job_markdown(job, report_type)
    return FileResponse(
        report_path,
        media_type="text/markdown; charset=utf-8",
        filename=report_path.name,
    )


@app.get("/api/jobs/{job_id}/reports/{report_type}.md")
def download_typed_job_markdown(job_id: str, report_type: str) -> FileResponse:
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    report_path = _write_job_markdown(job, report_type)
    return FileResponse(
        report_path,
        media_type="text/markdown; charset=utf-8",
        filename=report_path.name,
    )


@app.get("/api/jobs/{job_id}/reports/{report_type}.pdf")
def download_typed_job_pdf(job_id: str, report_type: str) -> FileResponse:
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    report_path = _write_job_pdf(job, report_type)
    return FileResponse(
        report_path,
        media_type="application/pdf",
        filename=report_path.name,
    )


@app.get("/api/files")
def get_public_file(path: str) -> FileResponse:
    return FileResponse(_resolve_public_file(path))
