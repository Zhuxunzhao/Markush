from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "web" / "static"

STEP_SECONDS = 0.8

app = FastAPI(title="Mock Markush UI")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


BLUEPRINTS: dict[str, list[dict[str, Any]]] = {
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
        {"key": "search", "name": "现有技术检索", "detail": "生成检索线索并合并用户提供的 prior-art。"},
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

BLUEPRINTS["infringement_patentability"] = [
    {**item} for item in BLUEPRINTS["infringement"]
] + [{**PATENTABILITY_AS_INFRINGEMENT_NODE}]

JOBS: dict[str, dict[str, Any]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_blueprints() -> dict[str, list[dict[str, Any]]]:
    return {
        mode: [
            {**item, "order": index, "status": "pending"}
            for index, item in enumerate(items, start=1)
        ]
        for mode, items in BLUEPRINTS.items()
    }


def _create_job(mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    job_id = _timestamp_job_id()
    job = {
        "id": job_id,
        "mode": mode,
        "payload": payload,
        "started_monotonic": time.monotonic(),
        "created_at": _utc_now(),
    }
    JOBS[job_id] = job
    return job


def _timestamp_job_id() -> str:
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    if base not in JOBS:
        return base
    suffix = 2
    while f"{base}-{suffix:02d}" in JOBS:
        suffix += 1
    return f"{base}-{suffix:02d}"


def _mock_result(job: dict[str, Any]) -> dict[str, Any]:
    payload = job["payload"]
    infringement = {
        "patent_id": payload.get("patent_id") or "WO2020252229A2",
        "target_smiles": payload.get("smiles") or "CCc1cncc(NCc2cccnc2)n1",
        "is_protected": True,
        "confidence": "high",
        "fused_match": {
            "r_group_matching": {
                "R1": "ethyl-like substituent",
                "R2": "pyridylmethyl fragment",
                "core": "heteroaryl aminopyrimidine scaffold",
            }
        },
        "report": (
            "Mock infringement report:\n"
            "- The target molecule matches the representative core in the mocked claim scope.\n"
            "- R-group substitutions are treated as covered by the simulated Markush definition.\n"
            "- This is UI-only data and does not represent a legal or chemical conclusion."
        ),
    }
    patentability = {
        "novelty_score": 0.74,
        "prior_arts": [
            {"patent_id": "WO2020252229A2"},
            {"patent_id": "US20210123456A1"},
            {"patent_id": "EP3987654A1"},
        ],
        "risk_points": [
            "Close scaffold overlap with mocked kinase-inhibitor prior art.",
            "R1/R2 positions need narrower fallback claims.",
        ],
        "suggestions": [
            "Add examples around steric variants at R1.",
            "Prepare dependent claims for polar heteroaryl substitutions.",
        ],
        "report": (
            "Mock patentability report:\n"
            "- The proposed structure appears moderately differentiated in the mocked search set.\n"
            "- Novelty pressure is concentrated around the shared cyclic core.\n"
            "- This response is generated only to exercise the front-end workflow."
        ),
    }
    if job["mode"] == "infringement_patentability":
        return {"infringement": infringement, "patentability": patentability}
    if job["mode"] == "infringement":
        return infringement
    return patentability


def _event_for(job: dict[str, Any], index: int, total: int) -> dict[str, Any]:
    item = BLUEPRINTS[job["mode"]][index - 1]
    return {
        "timestamp": _utc_now(),
        "level": "step",
        "message": f"Mock step {index}/{total}: {item['name']} finished.",
        "step": index,
        "total_steps": total,
        "agent": item["name"],
        "agent_key": item["key"],
    }


def _step_output_for(job: dict[str, Any], index: int) -> dict[str, Any]:
    item = BLUEPRINTS[job["mode"]][index - 1]
    return {
        "timestamp": _utc_now(),
        "step": index,
        "agent_key": item["key"],
        "title": item["name"],
        "summary": f"Mock output for {item['name']}.",
        "data": {
            "mode": job["mode"],
            "step": index,
            "agent_key": item["key"],
            "sample": True,
            "image_selection": {
                "selected": {
                    "image_path": str(
                        ROOT
                        / "cache"
                        / "google_patent"
                        / "WO2020252229A2"
                        / "image_1.png"
                    )
                }
            }
            if index == 2 and job["mode"] in {"infringement", "infringement_patentability"}
            else None,
        },
    }


def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
    blueprint = BLUEPRINTS[job["mode"]]
    total = len(blueprint)
    elapsed = time.monotonic() - job["started_monotonic"]
    run_elapsed = max(0.0, elapsed - 0.35)
    complete_after = total * STEP_SECONDS + 0.35
    status = "queued" if elapsed < 0.35 else "running"
    if elapsed >= complete_after:
        status = "succeeded"
    if job.get("status") == "cancelled":
        status = "cancelled"

    active_step = min(int(run_elapsed // STEP_SECONDS) + 1, total) if status == "running" else None
    completed = total if status == "succeeded" else max((active_step or 1) - 1, 0)

    agents = []
    for index, item in enumerate(blueprint, start=1):
        if status == "succeeded" or index <= completed:
            agent_status = "done"
        elif active_step == index:
            agent_status = "active"
        else:
            agent_status = "pending"
        agents.append({**item, "order": index, "status": agent_status})

    events = [
        {
            "timestamp": job["created_at"],
            "level": "info",
            "message": "Mock task accepted. Simulating agent telemetry.",
            "step": None,
            "total_steps": total,
        }
    ]
    visible_steps = total if status == "succeeded" else completed + (1 if active_step else 0)
    events.extend(_event_for(job, index, total) for index in range(1, visible_steps + 1))
    step_outputs = [_step_output_for(job, index) for index in range(1, visible_steps + 1)]
    if status == "succeeded":
        events.append(
            {
                "timestamp": _utc_now(),
                "level": "info",
                "message": "Mock pipeline finished successfully.",
                "step": None,
                "total_steps": total,
            }
        )
    if status == "cancelled":
        events.append(
            {
                "timestamp": _utc_now(),
                "level": "warning",
                "message": "Mock pipeline stopped by user.",
                "step": None,
                "total_steps": total,
            }
        )

    return {
        "id": job["id"],
        "mode": job["mode"],
        "status": status,
        "created_at": job["created_at"],
        "updated_at": _utc_now(),
        "payload": job["payload"],
        "agents": agents,
        "events": events[-8:],
        "event_count": len(events),
        "step_outputs": step_outputs,
        "result": _mock_result(job) if status == "succeeded" else None,
        "error": {"message": "用户已手动停止任务。"} if status == "cancelled" else None,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "mock"}


@app.get("/api/blueprints")
def blueprints() -> dict[str, Any]:
    return _public_blueprints()


@app.get("/api/llm-defaults")
def llm_defaults() -> dict[str, Any]:
    return {
        "provider": "openai",
        "model": "gpt5.5",
        "model_options": [
            {"value": "qwen3.6-plus", "label": "qwen3.6-plus"},
            {"value": "gpt5.5", "label": "gpt5.5"},
            {"value": "glm5.1", "label": "glm5.1"},
        ],
        "api_key_configured": True,
    }


@app.post("/api/infringement")
async def submit_infringement(request: Request) -> dict[str, Any]:
    payload = await request.json()
    mode = "infringement_patentability" if payload.get("include_patentability") else "infringement"
    job = _create_job(
        mode,
        {
            "evaluation_name": str(payload.get("evaluation_name") or "").strip() or None,
            "patent_id": str(payload.get("patent_id") or "").strip(),
            "smiles": str(payload.get("smiles") or "").strip(),
            "caption": str(payload.get("caption") or "").strip() or None,
        },
    )
    return {"job_id": job["id"]}


@app.post("/api/infringement/load-previous")
async def load_previous_infringement(request: Request) -> dict[str, Any]:
    payload = await request.json()
    job = _create_job(
        "infringement",
        {
            "evaluation_name": str(payload.get("evaluation_name") or "").strip() or None,
            "patent_id": str(payload.get("patent_id") or "").strip(),
            "smiles": str(payload.get("smiles") or "").strip(),
            "caption": str(payload.get("caption") or "").strip() or None,
        },
    )
    job["started_monotonic"] = time.monotonic() - 999
    return {"job_id": job["id"], "source": "mock"}


@app.post("/api/infringement/previous-results")
async def previous_infringement_results(request: Request) -> dict[str, Any]:
    await request.json()
    return {
        "count": 2,
        "candidates": [
            {
                "id": "mock-success-1",
                "label": "mock-model | protected | latest",
                "evaluation_name": "mock-eval",
                "source_file": "mock/results/latest.json",
                "model": "mock-model",
                "confidence": "high",
                "analysis_status": "protected",
                "updated_at": _utc_now(),
            },
            {
                "id": "mock-success-2",
                "label": "mock-model | not_protected | previous",
                "evaluation_name": "mock-eval",
                "source_file": "mock/results/previous.json",
                "model": "mock-model",
                "confidence": "moderate",
                "analysis_status": "not_protected",
                "updated_at": _utc_now(),
            },
        ],
    }


@app.post("/api/patentability")
async def submit_patentability() -> dict[str, Any]:
    job = _create_job("patentability", {"cxsmiles": None, "domain": "mock", "prior_arts": []})
    return {"job_id": job["id"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(_snapshot(job))


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    job["status"] = "cancelled"
    return {"job_id": job_id, "status": "cancelled"}


@app.post("/api/jobs/{job_id}/rerun-step")
async def rerun_step(job_id: str, request: Request) -> dict[str, Any]:
    source = JOBS.get(job_id)
    if source is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = await request.json()
    job = _create_job(source["mode"], {**source["payload"], "rerun": payload})
    return {
        "job_id": job["id"],
        "mode": source["mode"],
        "step_key": payload.get("agent_key"),
        "step_name": payload.get("agent_key"),
    }


@app.get("/api/files")
def get_public_file(path: str) -> FileResponse:
    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)


@app.get("/api/jobs/{job_id}/report.md")
def download_job_markdown(job_id: str) -> FileResponse:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="job not found")
    target = ROOT / "outputs" / "ui-reports" / f"{job_id}.mock.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Mock infringement report\n\n## 最终结论\n\n- 结论：落入保护范围\n", encoding="utf-8-sig")
    return FileResponse(target, media_type="text/markdown; charset=utf-8", filename=target.name)


@app.get("/api/jobs/{job_id}/reports/{report_type}.md")
def download_typed_job_markdown(job_id: str, report_type: str) -> FileResponse:
    return download_job_markdown(job_id)


@app.get("/api/jobs/{job_id}/reports/{report_type}.pdf")
def download_typed_job_pdf(job_id: str, report_type: str) -> FileResponse:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="job not found")
    from PIL import Image, ImageDraw, ImageFont

    target = ROOT / "outputs" / "ui-reports" / f"{job_id}.{report_type}.mock.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    page = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default()
    draw.text((64, 64), "Mock report PDF", fill="black", font=font)
    page.save(target, "PDF", resolution=120)
    return FileResponse(target, media_type="application/pdf", filename=target.name)
