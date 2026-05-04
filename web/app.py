from __future__ import annotations

import dataclasses
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipelines.infringement import InfringementPipeline
from pipelines.patentability import PatentabilityPipeline
from schemas.types import Confidence, MatchMethod
from tools.llm_client import load_config
from tools.logger import log


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "web" / "static"
UPLOAD_DIR = ROOT / "web" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = load_config(str(ROOT / "config.yaml"))

app = FastAPI(title="Multi-Agent for Markush UI")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class InfringementPayload(BaseModel):
    patent_id: str
    smiles: str
    caption: Optional[str] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "mode": mode,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
            "events": [],
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
            }

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            job["updated_at"] = datetime.utcnow().isoformat() + "Z"

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["events"].append(event)
            job["updated_at"] = datetime.utcnow().isoformat() + "Z"


JOBS = JobStore()


PIPELINE_BLUEPRINTS = {
    "infringement": [
        {"key": "fetch", "name": "PatentScraperTool", "detail": "专利抓取与文本装载"},
        {"key": "graph", "name": "LLM Image Selector + MarkushGrapher", "detail": "主 Markush 图筛选与结构识别"},
        {"key": "claim", "name": "ClaimAnalyzerAgent", "detail": "权利要求解析"},
        {"key": "rdkit", "name": "RDKitMatcherTool", "detail": "子结构匹配"},
        {"key": "fusion", "name": "SubsMatcherAgent", "detail": "R 基团映射验证"},
        {"key": "rule", "name": "RequirementsExaminerAgent", "detail": "保护范围判断"},
        {"key": "report", "name": "ReportGeneratorAgent", "detail": "分析报告生成"},
    ],
    "patentability": [
        {"key": "resolve", "name": "Markush Resolver", "detail": "结构标准化"},
        {"key": "search", "name": "PriorArtSearcherAgent", "detail": "先有技术检索"},
        {"key": "verify", "name": "PatentScraper + LLM Image Selector + MarkushGrapher", "detail": "候选专利主 Markush 验证"},
        {"key": "novelty", "name": "NoveltyAnalyzerAgent", "detail": "新颖性评估"},
        {"key": "report", "name": "ReportGeneratorAgent", "detail": "申请策略报告"},
    ],
}


def _serialize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {_key: _serialize(_val) for _key, _val in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, tuple):
        return [_serialize(v) for v in value]
    if isinstance(value, (Confidence, MatchMethod)):
        return value.value
    return value


def _format_event(raw_event: dict[str, Any], mode: str) -> dict[str, Any]:
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
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

    latest = events[-8:]
    return {
        "id": job["id"],
        "mode": mode,
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "payload": job["payload"],
        "agents": agents,
        "events": latest,
        "event_count": len(events),
        "result": job["result"],
        "error": job["error"],
    }


def _run_infringement(job_id: str, payload: dict[str, Any]) -> None:
    pipeline = InfringementPipeline(CONFIG)
    result = pipeline.run(
        patent_id=payload["patent_id"],
        target_smiles=payload["smiles"],
        markush_caption=payload.get("caption"),
    )
    JOBS.update(job_id, status="succeeded", result=_serialize(result))


def _run_patentability(job_id: str, payload: dict[str, Any]) -> None:
    pipeline = PatentabilityPipeline(CONFIG)
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
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "info",
                "message": "Pipeline task accepted and queued for execution.",
            },
        )
        start = time.time()
        try:
            runner(job_id, payload)
            JOBS.append_event(
                job_id,
                {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
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
                    "timestamp": datetime.utcnow().isoformat() + "Z",
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
    return {"status": "ok"}


@app.get("/api/blueprints")
def blueprints() -> dict[str, Any]:
    return PIPELINE_BLUEPRINTS


@app.post("/api/infringement")
def submit_infringement(payload: InfringementPayload) -> dict[str, Any]:
    job = JOBS.create(
        "infringement",
        {
            "patent_id": payload.patent_id.strip(),
            "smiles": payload.smiles.strip(),
            "caption": (payload.caption or "").strip() or None,
        },
    )
    _launch_job(job["id"], _run_infringement, job["payload"], "infringement")
    return {"job_id": job["id"]}


@app.post("/api/patentability")
async def submit_patentability(
    cxsmiles: Optional[str] = Form(default=None),
    domain: str = Form(default=""),
    prior_arts: str = Form(default=""),
    image: Optional[UploadFile] = File(default=None),
) -> dict[str, Any]:
    cxsmiles = (cxsmiles or "").strip()
    domain = domain.strip()
    prior_art_ids = [item.strip() for item in prior_arts.split(",") if item.strip()]

    image_path = None
    if image and image.filename:
        suffix = Path(image.filename).suffix or ".png"
        target = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        with target.open("wb") as fh:
            fh.write(await image.read())
        image_path = str(target)

    if not cxsmiles and not image_path:
        raise HTTPException(status_code=400, detail="cxsmiles or image is required")

    job = JOBS.create(
        "patentability",
        {
            "cxsmiles": cxsmiles or None,
            "domain": domain,
            "prior_arts": prior_art_ids,
            "image_path": image_path,
            "image_name": image.filename if image and image.filename else None,
        },
    )
    _launch_job(job["id"], _run_patentability, job["payload"], "patentability")
    return {"job_id": job["id"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    return JSONResponse(_build_snapshot(job))
