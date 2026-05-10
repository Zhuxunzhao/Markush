from __future__ import annotations

import dataclasses
import threading
import time
import traceback
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

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

CONFIG = load_config(str(ROOT / "config.yaml"))

app = FastAPI(title="Markush Patent Intelligence Workbench")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class LLMSettings(BaseModel):
    provider: str = "openai"
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class InfringementPayload(BaseModel):
    patent_id: str
    smiles: str
    caption: Optional[str] = None
    llm: Optional[LLMSettings] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now()
        job_id = uuid.uuid4().hex
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
        }
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return {
                **job,
                "events": list(job["events"]),
                "step_outputs": list(job["step_outputs"]),
            }

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
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


JOBS = JobStore()


PIPELINE_BLUEPRINTS = {
    "infringement": [
        {"key": "fetch", "name": "专利文本抓取", "detail": "读取专利权利要求、说明书与附图索引。"},
        {"key": "markush", "name": "LLM Markush 结构解析", "detail": "用 LLM 解析主 Markush 通式与变量定义。"},
        {"key": "claim", "name": "权利要求解析", "detail": "抽取保护范围、R-group 约束与关键 claim 语义。"},
        {"key": "llm_match", "name": "LLM 分子结构匹配", "detail": "判断目标分子骨架和 R-group 映射。"},
        {"key": "fusion", "name": "匹配融合验证", "detail": "融合 LLM 结构匹配与 claim 语义证据。"},
        {"key": "alignment", "name": "R-group 标签对齐", "detail": "把结构局部变量对齐到权利要求法律变量。"},
        {"key": "requirements", "name": "保护范围判断", "detail": "逐项检查是否落入权利要求覆盖范围。"},
        {"key": "report", "name": "侵权分析报告", "detail": "生成结论、置信度、理由与风险提示。"},
    ],
    "patentability": [
        {"key": "resolve", "name": "拟申请结构解析", "detail": "解析拟申请 CXSMILES 或上传结构图。"},
        {"key": "search", "name": "现有技术检索", "detail": "生成检索线索并合并用户提供的 prior-art。"},
        {"key": "prior_markush", "name": "Prior-art Markush 解析", "detail": "用 LLM 提取候选专利中的可比较 Markush。"},
        {"key": "novelty", "name": "新颖性分析", "detail": "比较重叠特征、差异特征与新颖性风险。"},
        {"key": "authorization", "name": "授权可能性分析", "detail": "综合创造性、清楚性与授权风险。"},
        {"key": "report", "name": "可授权分析报告", "detail": "生成申请策略、风险点与改进建议。"},
    ],
}


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


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


def _llm_settings_dict(settings: Optional[LLMSettings | dict[str, Any]]) -> dict[str, str]:
    if settings is None:
        return {}
    raw = settings.model_dump() if isinstance(settings, LLMSettings) else dict(settings)
    return {
        "provider": str(raw.get("provider") or "openai").strip() or "openai",
        "model": str(raw.get("model") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
    }


def _public_llm_settings(settings: dict[str, str]) -> dict[str, Any]:
    return {
        "provider": settings.get("provider") or "openai",
        "model": settings.get("model") or None,
        "base_url": settings.get("base_url") or None,
        "api_key_configured": bool(settings.get("api_key")),
    }


def _llm_pipeline_kwargs(settings: dict[str, str]) -> dict[str, Optional[str]]:
    return {
        "llm_provider": settings.get("provider") or None,
        "llm_model": settings.get("model") or None,
        "llm_base_url": settings.get("base_url") or None,
        "llm_api_key": settings.get("api_key") or None,
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
    def record_step(output: dict[str, Any]) -> None:
        JOBS.append_step_output(job_id, _serialize(output))

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
    JOBS.update(job_id, status="succeeded", result=_serialize(result))


def _run_patentability(job_id: str, payload: dict[str, Any]) -> None:
    def record_step(output: dict[str, Any]) -> None:
        JOBS.append_step_output(job_id, _serialize(output))

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
    JOBS.update(job_id, status="succeeded", result=_serialize(result))


def _launch_job(job_id: str, runner, payload: dict[str, Any], mode: str) -> None:
    def worker() -> None:
        JOBS.update(job_id, status="running")

        def listener(raw_event: dict[str, Any]) -> None:
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
            JOBS.append_event(
                job_id,
                {
                    "timestamp": _utc_now(),
                    "level": "info",
                    "message": f"Pipeline finished in {time.time() - start:.1f}s.",
                },
            )
        except Exception as exc:
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


@app.post("/api/infringement")
def submit_infringement(payload: InfringementPayload) -> dict[str, Any]:
    llm_settings = _llm_settings_dict(payload.llm)
    stored_payload = {
        "patent_id": payload.patent_id.strip(),
        "smiles": payload.smiles.strip(),
        "caption": (payload.caption or "").strip() or None,
        "llm": _public_llm_settings(llm_settings),
    }
    runner_payload = {
        **stored_payload,
        "llm": llm_settings,
    }
    job = JOBS.create("infringement", stored_payload)
    _launch_job(job["id"], _run_infringement, runner_payload, "infringement")
    return {"job_id": job["id"]}


@app.post("/api/patentability")
async def submit_patentability(
    cxsmiles: Optional[str] = Form(default=None),
    domain: str = Form(default=""),
    prior_arts: str = Form(default=""),
    image: Optional[UploadFile] = File(default=None),
    llm_provider: str = Form(default="openai"),
    llm_model: str = Form(default=""),
    llm_base_url: str = Form(default=""),
    llm_api_key: str = Form(default=""),
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
    job = JOBS.create("patentability", stored_payload)
    _launch_job(job["id"], _run_patentability, runner_payload, "patentability")
    return {"job_id": job["id"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    return JSONResponse(_build_snapshot(job))
