const state = {
  mode: "infringement",
  jobId: null,
  pollTimer: null,
  blueprints: {},
  includePatentability: false,
  chain: null,
};

const els = {
  infringementForm: document.getElementById("infringement-form"),
  infringementSubmit: document.getElementById("infringement-submit"),
  patentabilityToggle: document.getElementById("patentability-toggle"),
  patentabilityOptions: document.getElementById("patentability-options"),
  workflowList: document.getElementById("workflow-list"),
  workflowCount: document.getElementById("workflow-count"),
  eventLog: document.getElementById("event-log"),
  resultPanel: document.getElementById("result-panel"),
  jobMode: document.getElementById("job-mode"),
  jobStatus: document.getElementById("job-status"),
  jobId: document.getElementById("job-id"),
  jobEvents: document.getElementById("job-events"),
  llmProvider: document.getElementById("llm-provider"),
  llmModel: document.getElementById("llm-model"),
  llmBaseUrl: document.getElementById("llm-base-url"),
  llmApiKey: document.getElementById("llm-api-key"),
};

async function init() {
  try {
    const response = await fetch("/api/blueprints");
    state.blueprints = await parseResponse(response);
  } catch (error) {
    state.blueprints = {};
    renderClientError(error);
  }
  bindEvents();
  renderWorkflow(state.blueprints.infringement || [], []);
  els.jobMode.textContent = modeLabel("infringement");
}

function bindEvents() {
  els.infringementForm.addEventListener("submit", submitInfringement);
  els.patentabilityToggle.addEventListener("click", togglePatentability);
}

function togglePatentability() {
  state.includePatentability = !state.includePatentability;
  els.patentabilityToggle.classList.toggle("is-active", state.includePatentability);
  els.patentabilityToggle.setAttribute("aria-pressed", String(state.includePatentability));
  els.patentabilityToggle.textContent = state.includePatentability
    ? "可授权分析：开启"
    : "可授权分析：关闭";
  els.patentabilityOptions.classList.toggle("is-hidden", !state.includePatentability);
  els.infringementSubmit.textContent = state.includePatentability
    ? "启动侵权分析 + 可授权分析"
    : "启动侵权分析";
}

async function submitInfringement(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.mode = "infringement";
  const payload = {
    patent_id: String(form.get("patent_id") || "").trim(),
    smiles: String(form.get("smiles") || "").trim(),
    caption: String(form.get("caption") || "").trim(),
    llm: collectLlmSettings(),
  };
  state.chain = state.includePatentability
    ? {
        infringementSnapshot: null,
        patentability: collectPatentabilitySettings(form, payload),
      }
    : null;

  try {
    setSubmitting(true);
    const response = await fetch("/api/infringement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseResponse(response);
    startPolling(data.job_id, "侵权分析", {
      mode: "infringement",
      onSucceeded: state.chain ? submitPatentabilityFollowup : null,
    });
  } catch (error) {
    renderClientError(error);
  } finally {
    setSubmitting(false);
  }
}

function collectLlmSettings() {
  return {
    provider: els.llmProvider.value.trim() || "openai",
    model: els.llmModel.value.trim(),
    base_url: els.llmBaseUrl.value.trim(),
    api_key: els.llmApiKey.value.trim(),
  };
}

function collectPatentabilitySettings(form, infringementPayload) {
  return {
    cxsmiles: infringementPayload.smiles,
    domain: String(form.get("patentability_domain") || "").trim(),
    prior_arts: String(form.get("patentability_prior_arts") || "").trim(),
    llm: { ...infringementPayload.llm },
  };
}

async function submitPatentabilityFollowup(infringementSnapshot) {
  if (!state.chain) return;

  state.chain.infringementSnapshot = infringementSnapshot;
  const form = buildPatentabilityFormData(state.chain.patentability, infringementSnapshot);

  try {
    setSubmitting(true);
    els.resultPanel.innerHTML = `
      ${resultTitle("侵权分析")}
      ${infringementResultHtml(infringementSnapshot.result)}
      <div class="empty-state">可授权分析正在启动。</div>
    `;
    const response = await fetch("/api/patentability", {
      method: "POST",
      body: form,
    });
    const data = await parseResponse(response);
    startPolling(data.job_id, "可授权分析", { mode: "patentability" });
  } catch (error) {
    renderClientError(error);
  } finally {
    setSubmitting(false);
  }
}

function buildPatentabilityFormData(settings, infringementSnapshot) {
  const result = infringementSnapshot?.result || {};
  const llm = settings.llm || collectLlmSettings();
  const form = new FormData();
  form.set("cxsmiles", String(result.target_smiles || settings.cxsmiles || "").trim());
  form.set("domain", settings.domain || "");
  form.set("prior_arts", settings.prior_arts || "");
  form.set("llm_provider", llm.provider || "openai");
  form.set("llm_model", llm.model || "");
  form.set("llm_base_url", llm.base_url || "");
  form.set("llm_api_key", llm.api_key || "");
  return form;
}

function setSubmitting(isSubmitting) {
  document.querySelectorAll(".primary-action").forEach((button) => {
    button.disabled = isSubmitting;
  });
  els.patentabilityToggle.disabled = isSubmitting;
}

function startPolling(jobId, label, options = {}) {
  state.jobId = jobId;
  state.mode = options.mode || state.mode;
  els.jobMode.textContent = label;
  els.jobStatus.textContent = "Queued";
  els.jobId.textContent = jobId;
  els.jobEvents.textContent = "0";
  els.eventLog.innerHTML = `<div class="empty-state">&gt; job ${escapeHtml(jobId)} accepted...</div>`;
  els.resultPanel.innerHTML = `<div class="empty-state">Pipeline 正在运行。</div>`;
  renderWorkflow(state.blueprints[state.mode] || [], []);

  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
  }

  const tick = async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      const snapshot = await parseResponse(response);
      renderSnapshot(snapshot);
      if (snapshot.status === "succeeded" || snapshot.status === "failed") {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
        if (snapshot.status === "succeeded" && typeof options.onSucceeded === "function") {
          await options.onSucceeded(snapshot);
        }
      }
    } catch (error) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      renderClientError(error);
    }
  };

  tick();
  state.pollTimer = window.setInterval(tick, 1200);
}

function renderSnapshot(snapshot) {
  state.mode = snapshot.mode || state.mode;
  els.jobMode.textContent = modeLabel(snapshot.mode);
  els.jobStatus.textContent = statusText(snapshot.status);
  els.jobId.textContent = snapshot.id || "---";
  els.jobEvents.textContent = String(snapshot.event_count || 0);
  renderWorkflow(snapshot.agents || [], snapshot.step_outputs || []);
  renderEventLog(snapshot.events || []);
  renderResult(snapshot);
}

function renderWorkflow(agents, stepOutputs) {
  const outputsByKey = new Map();
  stepOutputs.forEach((output) => outputsByKey.set(output.agent_key, output));
  const completed = agents.filter((agent) => agent.status === "done").length;
  els.workflowCount.textContent = `${completed} / ${agents.length}`;

  if (!agents.length) {
    els.workflowList.innerHTML = `<div class="empty-state">暂无工作流定义。</div>`;
    return;
  }

  els.workflowList.innerHTML = agents
    .map((agent, index) => {
      const order = agent.order ?? index + 1;
      const status = agent.status || "pending";
      const output = outputsByKey.get(agent.key);
      const hasOutput = Boolean(output);
      const details = hasOutput
        ? `
          <details class="step-output" ${agent.status === "active" ? "open" : ""}>
            <summary>${escapeHtml(output.summary || "查看步骤输出")}</summary>
            <pre>${escapeHtml(formatData(output.data))}</pre>
          </details>
        `
        : `<div class="step-placeholder">等待输出</div>`;
      return `
        <article class="workflow-step is-${status}">
          <div class="step-index">${order}</div>
          <div class="step-body">
            <div class="step-head">
              <div>
                <h3>${escapeHtml(agent.name)}</h3>
                <p>${escapeHtml(agent.detail)}</p>
              </div>
              <span class="step-status">${statusText(status)}</span>
            </div>
            ${details}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderEventLog(events) {
  if (!events.length) {
    els.eventLog.innerHTML = `<div class="empty-state">&gt; awaiting workflow...</div>`;
    return;
  }
  els.eventLog.innerHTML = events
    .map(
      (event) => `
        <article class="event-item">
          <div class="event-line">
            <span class="event-level level-${escapeHtml(event.level)}">${escapeHtml(event.level)}</span>
            <span>${formatTime(event.timestamp)}</span>
          </div>
          <p>${escapeHtml(event.message)}</p>
          <small>${escapeHtml(event.agent || "Pipeline")}${
            event.step ? ` · Step ${escapeHtml(event.step)}/${escapeHtml(event.total_steps || "?")}` : ""
          }</small>
        </article>
      `,
    )
    .join("");
  els.eventLog.scrollTop = els.eventLog.scrollHeight;
}

function renderResult(snapshot) {
  if (snapshot.status === "failed") {
    const previous = state.chain?.infringementSnapshot?.result;
    if (snapshot.mode === "patentability" && previous) {
      els.resultPanel.innerHTML = `
        ${resultTitle("侵权分析")}
        ${infringementResultHtml(previous)}
        ${resultTitle("可授权分析")}
        <article class="result-block danger">
          <h3>任务失败</h3>
          <pre>${escapeHtml(snapshot.error?.message || "Unknown error")}</pre>
        </article>
        ${
          snapshot.error?.traceback
            ? `<article class="result-block"><h3>Traceback</h3><pre>${escapeHtml(snapshot.error.traceback)}</pre></article>`
            : ""
        }
      `;
      return;
    }

    els.resultPanel.innerHTML = `
      <article class="result-block danger">
        <h3>任务失败</h3>
        <pre>${escapeHtml(snapshot.error?.message || "Unknown error")}</pre>
      </article>
      ${
        snapshot.error?.traceback
          ? `<article class="result-block"><h3>Traceback</h3><pre>${escapeHtml(snapshot.error.traceback)}</pre></article>`
          : ""
      }
    `;
    return;
  }

  if (snapshot.status !== "succeeded" || !snapshot.result) {
    const previous = state.chain?.infringementSnapshot?.result;
    if (snapshot.mode === "patentability" && previous) {
      els.resultPanel.innerHTML = `
        ${resultTitle("侵权分析")}
        ${infringementResultHtml(previous)}
        ${resultTitle("可授权分析")}
        <div class="empty-state">Pipeline 正在运行。</div>
      `;
      return;
    }

    els.resultPanel.innerHTML = `<div class="empty-state">Pipeline 正在运行。</div>`;
    return;
  }

  if (snapshot.mode === "infringement") {
    renderInfringementResult(snapshot.result);
    return;
  }

  if (state.chain?.infringementSnapshot?.result) {
    renderCombinedResult(state.chain.infringementSnapshot.result, snapshot.result);
    return;
  }

  renderPatentabilityResult(snapshot.result);
}

function renderInfringementResult(result) {
  els.resultPanel.innerHTML = infringementResultHtml(result);
}

function renderPatentabilityResult(result) {
  els.resultPanel.innerHTML = patentabilityResultHtml(result);
}

function renderCombinedResult(infringementResult, patentabilityResult) {
  els.resultPanel.innerHTML = `
    ${resultTitle("侵权分析")}
    ${infringementResultHtml(infringementResult)}
    ${resultTitle("可授权分析")}
    ${patentabilityResultHtml(patentabilityResult)}
  `;
}

function resultTitle(title) {
  return `<div class="result-title">${escapeHtml(title)}</div>`;
}

function infringementResultHtml(result) {
  return `
    <div class="result-metrics">
      ${metric("保护范围", result.is_protected ? "落入" : "未落入")}
      ${metric("置信度", result.confidence || "-")}
    </div>
    ${textBlock("目标专利", result.patent_id || "-")}
    ${textBlock("目标分子", result.target_smiles || "-")}
    ${listBlock("R-group 映射", objectToItems(result.fused_match?.r_group_matching))}
    ${reportBlock("分析报告", result.report)}
  `;
}

function patentabilityResultHtml(result) {
  const success = result.success_analysis || {};
  return `
    <div class="result-metrics">
      ${metric("新颖性评分", formatScore(result.novelty_score))}
      ${metric("授权可能性", success.success_rate_estimation || "-")}
    </div>
    ${listBlock("相关现有技术", (result.prior_arts || []).map((item) => escapeHtml(item.patent_id || item)))}
    ${listBlock("风险点", (result.risk_points || []).map((item) => escapeHtml(item)))}
    ${listBlock("改进建议", (result.suggestions || success.improvement_suggestions || []).map((item) => escapeHtml(item)))}
    ${reportBlock("分析报告", result.report || success.comprehensive_report)}
  `;
}

function metric(title, value) {
  return `
    <article class="metric-box">
      <span>${escapeHtml(title)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

function textBlock(title, value) {
  return `
    <article class="result-block">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(value)}</p>
    </article>
  `;
}

function listBlock(title, items) {
  if (!items || !items.length) {
    return `
      <article class="result-block">
        <h3>${escapeHtml(title)}</h3>
        <p>无</p>
      </article>
    `;
  }
  return `
    <article class="result-block">
      <h3>${escapeHtml(title)}</h3>
      <ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>
    </article>
  `;
}

function reportBlock(title, content) {
  return `
    <article class="result-block">
      <h3>${escapeHtml(title)}</h3>
      <pre>${escapeHtml(content || "无报告内容")}</pre>
    </article>
  `;
}

async function parseResponse(response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

function renderClientError(error) {
  els.jobStatus.textContent = "Client Error";
  els.resultPanel.innerHTML = `
    <article class="result-block danger">
      <h3>请求失败</h3>
      <pre>${escapeHtml(error.message || String(error))}</pre>
    </article>
  `;
}

function objectToItems(obj) {
  if (!obj || typeof obj !== "object") return [];
  return Object.entries(obj).map(([key, value]) => `${escapeHtml(key)}: ${escapeHtml(String(value))}`);
}

function formatData(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_error) {
    return String(value ?? "");
  }
}

function formatScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(2);
}

function formatTime(isoString) {
  if (!isoString) return "-";
  return new Date(isoString).toLocaleTimeString();
}

function modeLabel(mode) {
  if (mode === "infringement") return "侵权分析";
  if (mode === "patentability") return "可授权分析";
  return "待命";
}

function statusText(status) {
  const map = {
    queued: "排队中",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
    pending: "等待",
    active: "运行中",
    done: "完成",
  };
  return map[status] || status || "等待";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

init();
