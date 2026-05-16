const state = {
  mode: "infringement",
  jobId: null,
  pollTimer: null,
  currentSnapshot: null,
  blueprints: {},
  llmDefaults: {
    provider: "openai",
    model: "gpt5.5",
    base_url: "https://api.ohmygpt.com/v1",
    api_key_env: "OHMYGPT_API_KEY",
  },
  includePatentability: false,
  chain: null,
  previousLoadPayload: null,
  previousResults: {
    signature: null,
    candidates: null,
    isOpen: false,
  },
  stepOutputOpen: new Map(),
  stepOutputScroll: new Map(),
  eventAutoScroll: true,
};

const els = {
  infringementForm: document.getElementById("infringement-form"),
  infringementSubmit: document.getElementById("infringement-submit"),
  loadPreviousButton: document.getElementById("load-previous-result"),
  previousResultDropdown: document.getElementById("previous-result-dropdown"),
  patentabilityToggle: document.getElementById("patentability-toggle"),
  workflowList: document.getElementById("workflow-list"),
  workflowCount: document.getElementById("workflow-count"),
  eventLog: document.getElementById("event-log"),
  resultPanel: document.getElementById("result-panel"),
  jobMode: document.getElementById("job-mode"),
  jobStatus: document.getElementById("job-status"),
  jobId: document.getElementById("job-id"),
  jobEvents: document.getElementById("job-events"),
  stopJob: document.getElementById("stop-job"),
  llmModel: document.getElementById("llm-model"),
};

async function init() {
  try {
    const [blueprintsResponse, llmDefaultsResponse] = await Promise.all([
      fetch("/api/blueprints"),
      fetch("/api/llm-defaults"),
    ]);
    state.blueprints = await parseResponse(blueprintsResponse);
    state.llmDefaults = {
      ...state.llmDefaults,
      ...(await parseResponse(llmDefaultsResponse)),
    };
  } catch (error) {
    state.blueprints = {};
    renderClientError(error);
  }
  applyLlmDefaults();
  bindEvents();
  renderSelectedInfringementWorkflow();
}

function bindEvents() {
  els.infringementForm.addEventListener("submit", submitInfringement);
  if (els.loadPreviousButton) {
    els.loadPreviousButton.addEventListener("click", loadPreviousInfringement);
  }
  if (els.previousResultDropdown) {
    els.previousResultDropdown.addEventListener("click", handlePreviousDropdownClick);
  }
  els.patentabilityToggle.addEventListener("click", togglePatentability);
  els.workflowList.addEventListener("toggle", handleStepOutputToggle, true);
  els.workflowList.addEventListener("scroll", handleStepOutputScroll, true);
  els.workflowList.addEventListener("click", handleWorkflowClick);
  els.resultPanel.addEventListener("click", handleResultPanelClick);
  els.eventLog.addEventListener("scroll", handleEventLogScroll);
  if (els.stopJob) {
    els.stopJob.addEventListener("click", stopCurrentJob);
  }
}

function togglePatentability() {
  state.includePatentability = !state.includePatentability;
  state.previousResults = {
    signature: null,
    candidates: null,
    isOpen: false,
  };
  setPreviousDropdownOpen(false);
  els.patentabilityToggle.classList.toggle("is-active", state.includePatentability);
  els.patentabilityToggle.setAttribute("aria-pressed", String(state.includePatentability));
  els.patentabilityToggle.textContent = state.includePatentability
    ? "可授权分析：开启"
    : "可授权分析：关闭";
  els.infringementSubmit.textContent = state.includePatentability
    ? "启动侵权分析 + 可授权分析"
    : "启动侵权分析";
  renderCurrentWorkflowView();
  if (state.currentSnapshot) {
    renderResult(state.currentSnapshot);
  }
}

function selectedInfringementMode() {
  return state.includePatentability ? "infringement_patentability" : "infringement";
}

function renderSelectedInfringementWorkflow() {
  state.mode = "infringement";
  renderCurrentWorkflowView();
  els.jobMode.textContent = visibleWorkflowLabel();
}

async function submitInfringement(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.mode = selectedInfringementMode();
  state.currentSnapshot = null;
  const payload = {
    evaluation_name: String(form.get("evaluation_name") || "").trim(),
    patent_id: String(form.get("patent_id") || "").trim(),
    smiles: String(form.get("smiles") || "").trim(),
    caption: String(form.get("caption") || "").trim(),
    include_patentability: state.includePatentability,
    llm: collectLlmSettings(),
  };
  state.chain = null;

  try {
    setSubmitting(true);
    const response = await fetch("/api/infringement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseResponse(response);
    startPolling(data.job_id, state.includePatentability ? "侵权分析 + 可授权分析" : "侵权分析", {
      mode: state.includePatentability ? "infringement_patentability" : "infringement",
    });
  } catch (error) {
    renderClientError(error);
  } finally {
    setSubmitting(false);
  }
}

async function loadPreviousInfringement() {
  const form = new FormData(els.infringementForm);
  const payload = {
    evaluation_name: String(form.get("evaluation_name") || "").trim(),
    patent_id: String(form.get("patent_id") || "").trim(),
    smiles: String(form.get("smiles") || "").trim(),
    caption: String(form.get("caption") || "").trim(),
    include_patentability: state.includePatentability,
    llm: collectLlmSettings(),
  };
  const signature = previousResultSignature(payload);
  state.previousLoadPayload = payload;

  if (state.previousResults.signature === signature && state.previousResults.candidates) {
    const shouldOpen = !state.previousResults.isOpen;
    renderPreviousResultChoices(state.previousResults.candidates, payload);
    setPreviousDropdownOpen(shouldOpen);
    return;
  }

  try {
    setSubmitting(true);
    setPreviousDropdownOpen(true);
    renderPreviousDropdownMessage("正在查找匹配的成功结果...");
    const response = await fetch("/api/infringement/previous-results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseResponse(response);
    state.previousResults = {
      signature,
      candidates: data.candidates || [],
      isOpen: true,
    };
    renderPreviousResultChoices(data.candidates || [], payload);
  } catch (error) {
    renderPreviousDropdownMessage(error.message || String(error), true);
  } finally {
    setSubmitting(false);
  }
}

function collectLlmSettings() {
  return {
    model: els.llmModel.value.trim() || state.llmDefaults.model || "gpt5.5",
  };
}

function applyLlmDefaults() {
  const defaults = state.llmDefaults || {};
  const options = defaults.model_options || [
    { value: "qwen3.6-plus", label: "qwen3.6-plus" },
    { value: "gpt5.5", label: "gpt5.5" },
    { value: "glm5.1", label: "glm5.1" },
  ];
  els.llmModel.innerHTML = options
    .map(
      (option) =>
        `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value)}</option>`,
    )
    .join("");
  els.llmModel.value = defaults.model || "gpt5.5";
  if (!els.llmModel.value && options.length) {
    els.llmModel.value = options[0].value;
  }
}

async function submitPatentabilityFollowup(infringementSnapshot) {
  if (!state.chain) return;

  state.chain.infringementSnapshot = infringementSnapshot;
  const form = buildPatentabilityFormData(state.chain.patentability, infringementSnapshot);

  try {
    setSubmitting(true);
    els.resultPanel.innerHTML = `
      ${resultTitle("侵权分析")}
      ${infringementResultHtml(infringementSnapshot.result, infringementSnapshot.id)}
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
  form.set("cxsmiles", String(result.target_smiles || "").trim());
  form.set("prior_arts", String(result.patent_id || "").trim());
  form.set("llm_model", llm.model || state.llmDefaults.model || "gpt5.5");
  return form;
}

function setSubmitting(isSubmitting) {
  document.querySelectorAll(".primary-action").forEach((button) => {
    button.disabled = isSubmitting;
  });
  if (els.loadPreviousButton) {
    els.loadPreviousButton.disabled = isSubmitting;
  }
  els.patentabilityToggle.disabled = isSubmitting;
}

function startPolling(jobId, label, options = {}) {
  state.jobId = jobId;
  state.mode = options.mode || state.mode;
  state.currentSnapshot = null;
  state.stepOutputOpen = new Map();
  state.stepOutputScroll = new Map();
  state.eventAutoScroll = true;
  els.jobMode.textContent = label;
  els.jobStatus.textContent = "Queued";
  els.jobId.textContent = jobId;
  els.jobEvents.textContent = "0";
  setStopEnabled(true);
  els.eventLog.innerHTML = `<div class="empty-state">&gt; job ${escapeHtml(jobId)} accepted...</div>`;
  els.resultPanel.innerHTML = `<div class="empty-state">Pipeline 正在运行。</div>`;
  renderCurrentWorkflowView();

  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
  }

  const tick = async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      const snapshot = await parseResponse(response);
      renderSnapshot(snapshot);
      if (isTerminalStatus(snapshot.status)) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
        setStopEnabled(false);
        if (snapshot.status === "succeeded" && typeof options.onSucceeded === "function") {
          await options.onSucceeded(snapshot);
        }
      }
    } catch (error) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      setStopEnabled(false);
      renderClientError(error);
    }
  };

  tick();
  state.pollTimer = window.setInterval(tick, 1200);
}

async function stopCurrentJob() {
  if (!state.jobId || !els.stopJob || els.stopJob.disabled) return;
  try {
    els.stopJob.disabled = true;
    els.stopJob.textContent = "停止中";
    const response = await fetch(`/api/jobs/${encodeURIComponent(state.jobId)}/stop`, {
      method: "POST",
    });
    await parseResponse(response);
    const snapshotResponse = await fetch(`/api/jobs/${encodeURIComponent(state.jobId)}`);
    renderSnapshot(await parseResponse(snapshotResponse));
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  } catch (error) {
    renderClientError(error);
  } finally {
    setStopEnabled(false);
  }
}

function setStopEnabled(isEnabled) {
  if (!els.stopJob) return;
  els.stopJob.disabled = !isEnabled;
  els.stopJob.textContent = "停止";
}

function handleStepOutputToggle(event) {
  const details = event.target;
  if (!details.classList?.contains("step-output")) return;
  const key = details.dataset.agentKey;
  if (!key) return;
  state.stepOutputOpen.set(key, details.open);
}

function handleStepOutputScroll(event) {
  const target = event.target;
  if (!target.classList?.contains("step-output-scroll")) return;
  const key = target.dataset.scrollKey;
  if (!key) return;
  state.stepOutputScroll.set(key, target.scrollTop);
}

function handleWorkflowClick(event) {
  const button = event.target.closest("[data-rerun-step]");
  if (!button || button.disabled) return;
  const agentKey = button.dataset.rerunStep;
  rerunStep(agentKey);
}

function handleResultPanelClick(event) {
  const loadButton = event.target.closest("[data-load-previous-id]");
  if (loadButton) {
    loadSelectedPreviousResult(loadButton.dataset.loadPreviousId);
  }
}

function handlePreviousDropdownClick(event) {
  const loadButton = event.target.closest("[data-load-previous-id]");
  if (!loadButton) return;
  loadSelectedPreviousResult(loadButton.dataset.loadPreviousId);
}

function handleEventLogScroll() {
  state.eventAutoScroll = isNearBottom(els.eventLog);
}

async function rerunStep(agentKey) {
  if (!state.jobId || !agentKey) return;

  try {
    setSubmitting(true);
    const response = await fetch(`/api/jobs/${state.jobId}/rerun-step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_key: agentKey }),
    });
    const data = await parseResponse(response);
    state.chain = null;
    startPolling(data.job_id, `重跑步骤：${data.step_name || agentKey}`, {
      mode: data.mode || state.mode,
    });
  } catch (error) {
    renderClientError(error);
  } finally {
    setSubmitting(false);
  }
}

function renderPreviousResultChoices(candidates, payload) {
  state.previousLoadPayload = payload;
  state.chain = null;
  setPreviousDropdownOpen(true);

  if (!candidates.length) {
    const lookupLabel = payload.evaluation_name
      ? `评估名称「${payload.evaluation_name}」`
      : "当前 Patent ID 和 SMILES";
    renderPreviousDropdownMessage(
      `${lookupLabel} 没有匹配到 outputs/results 下的成功记录。`,
      true,
    );
    return;
  }

  els.jobStatus.textContent = "Choose Result";
  els.previousResultDropdown.innerHTML = `
    <article class="previous-results">
      <h3>选择要加载的成功结果</h3>
      <div class="previous-result-list">
        ${candidates.map(previousResultChoiceHtml).join("")}
      </div>
    </article>
  `;
}

function renderPreviousDropdownMessage(message, isError = false) {
  if (!els.previousResultDropdown) return;
  els.previousResultDropdown.innerHTML = `
    <article class="previous-results ${isError ? "danger" : ""}">
      <p>${escapeHtml(message)}</p>
    </article>
  `;
}

function setPreviousDropdownOpen(isOpen) {
  state.previousResults.isOpen = Boolean(isOpen);
  if (els.previousResultDropdown) {
    els.previousResultDropdown.classList.toggle("is-hidden", !state.previousResults.isOpen);
  }
}

function previousResultSignature(payload) {
  return [
    payload.include_patentability ? "with-patentability" : "infringement-only",
    String(payload.evaluation_name || "").trim().toLowerCase(),
    String(payload.patent_id || "").trim().toLowerCase(),
    String(payload.smiles || "").trim(),
  ].join("|");
}

function previousResultChoiceHtml(candidate) {
  const protection = previousProtectionState(candidate);
  const modelLabel = candidate.evaluation_name
    ? `${candidate.evaluation_name} / ${candidate.model || "-"}`
    : candidate.model || "-";
  return `
    <button
      class="previous-result-item"
      type="button"
      data-load-previous-id="${escapeHtml(candidate.id)}"
    >
      <span class="previous-result-time">${escapeHtml(formatDateTime(candidate.updated_at))}</span>
      <span class="previous-result-model">${escapeHtml(modelLabel)}</span>
      <span class="previous-result-protection ${protection.className}">
        ${escapeHtml(protection.label)}
      </span>
    </button>
  `;
}

async function loadSelectedPreviousResult(resultId) {
  if (!resultId || !state.previousLoadPayload) return;
  try {
    setSubmitting(true);
    const response = await fetch("/api/infringement/load-previous", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...state.previousLoadPayload,
        previous_result_id: resultId,
      }),
    });
    const data = await parseResponse(response);
    setPreviousDropdownOpen(false);
    if (data.mode === "infringement_patentability") {
      state.chain = null;
      startPolling(data.job_id, "已加载历史结果", { mode: "infringement_patentability" });
    } else if (state.includePatentability) {
      state.chain = {
        patentability: {
          llm: collectLlmSettings(),
        },
      };
      startPolling(data.job_id, "已加载历史结果", {
        mode: "infringement",
        onSucceeded: submitPatentabilityFollowup,
      });
    } else {
      state.chain = null;
      startPolling(data.job_id, "已加载历史结果", { mode: "infringement" });
    }
  } catch (error) {
    renderClientError(error);
  } finally {
    setSubmitting(false);
  }
}

function renderSnapshot(snapshot) {
  state.currentSnapshot = snapshot;
  state.mode = snapshot.mode || state.mode;
  els.jobMode.textContent = visibleWorkflowLabel(snapshot.mode);
  els.jobStatus.textContent = statusText(snapshot.status);
  els.jobId.textContent = snapshot.id || "---";
  els.jobEvents.textContent = String(snapshot.event_count || 0);
  setStopEnabled(Boolean(snapshot.id) && !isTerminalStatus(snapshot.status));
  renderCurrentWorkflowView();
  renderEventLog(snapshot.events || []);
  renderResult(snapshot);
}

function renderCurrentWorkflowView() {
  const snapshot = state.currentSnapshot;
  const view = workflowView(snapshot);
  renderWorkflow(view.agents, view.stepOutputs);
  els.jobMode.textContent = visibleWorkflowLabel(snapshot?.mode);
}

function workflowView(snapshot) {
  if (snapshot?.mode === "patentability" && state.chain?.infringementSnapshot) {
    const previous = state.chain.infringementSnapshot;
    const agents = baseWorkflowAgents(previous.agents || []);
    const stepOutputs = baseStepOutputs(previous.step_outputs || []);
    if (state.includePatentability) {
      agents.push(patentabilityViewNode(collapsedPatentabilityStatus(snapshot.agents || [], snapshot.status), agents.length + 1));
      const output = collapsedPatentabilityOutput(snapshot.step_outputs || [], snapshot);
      if (output) stepOutputs.push(output);
    }
    return { agents, stepOutputs };
  }

  const sourceAgents = snapshot?.agents || state.blueprints.infringement || [];
  const sourceOutputs = snapshot?.step_outputs || [];
  const agents = baseWorkflowAgents(sourceAgents);
  const stepOutputs = baseStepOutputs(sourceOutputs);
  if (state.includePatentability) {
    const patentabilityAgents = sourceAgents.filter((agent) => isPatentabilityKey(agent.key));
    agents.push(patentabilityViewNode(collapsedPatentabilityStatus(patentabilityAgents, snapshot?.status), agents.length + 1));
    const output = collapsedPatentabilityOutput(sourceOutputs, snapshot);
    if (output) stepOutputs.push(output);
  }
  return { agents, stepOutputs };
}

function baseWorkflowAgents(agents) {
  return (agents || [])
    .filter((agent) => !isPatentabilityKey(agent.key))
    .map((agent, index) => ({ ...agent, order: index + 1 }));
}

function baseStepOutputs(stepOutputs) {
  return (stepOutputs || []).filter((output) => !isPatentabilityKey(output.agent_key));
}

function patentabilityViewNode(status, order) {
  const blueprint =
    (state.blueprints.infringement_patentability || []).find((agent) => agent.key === "patentability") ||
    { key: "patentability", name: "可授权分析", detail: "基于侵权分析结果评估新颖性、创造性与授权风险。" };
  return { ...blueprint, key: "patentability", order, status: status || "pending" };
}

function collapsedPatentabilityStatus(agents, snapshotStatus) {
  if (snapshotStatus === "succeeded" && agents.length) return "done";
  if (snapshotStatus === "failed" || snapshotStatus === "cancelled") {
    return agents.some((agent) => agent.status === "done") ? "done" : "active";
  }
  if (agents.some((agent) => agent.status === "active")) return "active";
  if (agents.length && agents.every((agent) => agent.status === "done")) return "done";
  return "pending";
}

function collapsedPatentabilityOutput(stepOutputs, snapshot) {
  const outputs =
    snapshot?.mode === "patentability"
      ? stepOutputs || []
      : (stepOutputs || []).filter((output) => isPatentabilityKey(output.agent_key));
  const result = snapshot?.result?.patentability || (snapshot?.mode === "patentability" ? snapshot?.result : null);
  if (!outputs.length && !result) {
    return null;
  }
  const latest = outputs[outputs.length - 1] || {};
  return {
    ...latest,
    step: (state.blueprints.infringement || []).length + 1,
    agent_key: "patentability",
    title: "可授权分析",
    summary: latest.summary || (result ? "可授权分析结果已生成。" : "查看可授权分析输出"),
    data:
      latest.data ||
      result ||
      outputs.map((output) => output.data),
    timestamp: latest.timestamp || snapshot?.updated_at,
  };
}

function isPatentabilityKey(key) {
  const value = String(key || "");
  return value === "patentability" || value.startsWith("patentability_");
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
      const explicitOpen = state.stepOutputOpen.get(agent.key);
      const isOpen = explicitOpen ?? agent.status === "active";
      const canRerun =
        Boolean(state.jobId) &&
        state.mode !== "infringement_patentability" &&
        !isPatentabilityKey(agent.key);
      const scrollKey = `${agent.key}:data`;
      const details = hasOutput
        ? `
          <details class="step-output" data-agent-key="${escapeHtml(agent.key)}" ${isOpen ? "open" : ""}>
            <summary>${escapeHtml(output.summary || "查看步骤输出")}</summary>
            ${renderStepImages(output)}
            <pre class="step-output-scroll" data-scroll-key="${escapeHtml(scrollKey)}">${escapeHtml(formatData(output.data))}</pre>
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
              <div class="step-actions">
                <button
                  class="step-rerun"
                  type="button"
                  data-rerun-step="${escapeHtml(agent.key)}"
                  title="使用原输入重跑该步骤"
                  ${canRerun ? "" : "disabled"}
                >重跑</button>
                <span class="step-status">${statusText(status)}</span>
              </div>
            </div>
            ${details}
          </div>
        </article>
      `;
    })
    .join("");
  restoreStepOutputScroll();
}

function renderEventLog(events) {
  const shouldStickToBottom = state.eventAutoScroll || isNearBottom(els.eventLog);
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
  if (shouldStickToBottom) {
    els.eventLog.scrollTop = els.eventLog.scrollHeight;
  }
}

function restoreStepOutputScroll() {
  window.requestAnimationFrame(() => {
    els.workflowList.querySelectorAll(".step-output-scroll").forEach((element) => {
      const key = element.dataset.scrollKey;
      if (!key || !state.stepOutputScroll.has(key)) return;
      element.scrollTop = state.stepOutputScroll.get(key);
    });
  });
}

function renderResult(snapshot) {
  if (snapshot.mode === "infringement_patentability") {
    renderChainedResult(snapshot);
    return;
  }

  if (snapshot.status === "failed" || snapshot.status === "cancelled") {
    const previous = state.chain?.infringementSnapshot?.result;
    const title = snapshot.status === "cancelled" ? "任务已停止" : "任务失败";
    const failedResult =
      snapshot.mode === "infringement" && snapshot.result
        ? `${resultTitle("侵权分析")}${infringementResultHtml(snapshot.result, snapshot.id)}`
        : "";
    if (snapshot.mode === "patentability" && previous) {
      if (!state.includePatentability) {
        els.resultPanel.innerHTML = `
          ${resultTitle("侵权分析")}
          ${infringementResultHtml(previous, state.chain?.infringementSnapshot?.id)}
        `;
        return;
      }
      els.resultPanel.innerHTML = `
        ${resultTitle("侵权分析")}
        ${infringementResultHtml(previous, state.chain?.infringementSnapshot?.id)}
        ${resultTitle("可授权分析")}
        <article class="result-block danger">
          <h3>${title}</h3>
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
      ${failedResult}
      <article class="result-block danger">
        <h3>${title}</h3>
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
      if (!state.includePatentability) {
        els.resultPanel.innerHTML = `
          ${resultTitle("侵权分析")}
          ${infringementResultHtml(previous, state.chain?.infringementSnapshot?.id)}
        `;
        return;
      }
      els.resultPanel.innerHTML = `
        ${resultTitle("侵权分析")}
        ${infringementResultHtml(previous, state.chain?.infringementSnapshot?.id)}
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
  els.resultPanel.innerHTML = `
    ${infringementResultHtml(result, state.jobId)}
    ${
      state.includePatentability
        ? `${resultTitle("可授权分析")}<div class="empty-state">可授权分析未运行。</div>`
        : ""
    }
  `;
}

function renderPatentabilityResult(result) {
  els.resultPanel.innerHTML = `
    ${reportActions([{ jobId: state.jobId, type: "patentability", label: "可授权分析报告" }])}
    ${patentabilityResultHtml(result)}
  `;
}

function renderCombinedResult(infringementResult, patentabilityResult, jobId = state.jobId) {
  els.resultPanel.innerHTML = `
    ${reportActions([
      { jobId, type: "infringement", label: "侵权分析报告" },
      { jobId, type: "patentability", label: "可授权分析报告" },
    ])}
    ${resultTitle("侵权分析")}
    ${infringementResultHtml(infringementResult, jobId, { showReportActions: false })}
    ${resultTitle("可授权分析")}
    ${patentabilityResult ? patentabilityResultHtml(patentabilityResult) : `<div class="empty-state">可授权分析正在运行。</div>`}
  `;
}

function renderChainedResult(snapshot) {
  const infringementResult = snapshot.result?.infringement;
  const patentabilityResult = snapshot.result?.patentability;
  const errorBlock =
    snapshot.status === "failed" || snapshot.status === "cancelled"
      ? `
        <article class="result-block danger">
          <h3>${snapshot.status === "cancelled" ? "任务已停止" : "任务失败"}</h3>
          <pre>${escapeHtml(snapshot.error?.message || "Unknown error")}</pre>
        </article>
        ${
          snapshot.error?.traceback
            ? `<article class="result-block"><h3>Traceback</h3><pre>${escapeHtml(snapshot.error.traceback)}</pre></article>`
            : ""
        }
      `
      : "";

  if (!infringementResult) {
    els.resultPanel.innerHTML = `${errorBlock || `<div class="empty-state">Pipeline 正在运行。</div>`}`;
    return;
  }

  const reportItems = [
    { jobId: snapshot.id, type: "infringement", label: "侵权分析报告" },
  ];
  if (state.includePatentability && patentabilityResult) {
    reportItems.push({
      jobId: snapshot.id,
      type: "patentability",
      label: "可授权分析报告",
    });
  }

  els.resultPanel.innerHTML = `
    ${reportActions(reportItems)}
    ${resultTitle("侵权分析")}
    ${infringementResultHtml(infringementResult, snapshot.id, { showReportActions: false })}
    ${state.includePatentability ? resultTitle("可授权分析") : ""}
    ${state.includePatentability
      ? patentabilityResult
        ? patentabilityResultHtml(patentabilityResult)
        : `<div class="empty-state">${isTerminalStatus(snapshot.status) ? "可授权分析未运行。" : "可授权分析正在运行。"}</div>`
      : ""}
    ${errorBlock}
  `;
}

function resultTitle(title) {
  return `<div class="result-title">${escapeHtml(title)}</div>`;
}

function infringementResultHtml(result, jobId = state.jobId, options = {}) {
  const showReportActions = options.showReportActions !== false;
  const status = result.analysis_status || (result.is_protected ? "protected" : "not_protected");
  const conclusive = result.is_conclusive !== false;
  const protectionLabel = conclusive
    ? result.is_protected
      ? "落入"
      : "未落入"
    : "无法判断";
  return `
    <div class="result-metrics">
      ${metric("保护范围", protectionLabel)}
      ${metric("分析状态", analysisStatusText(status))}
      ${metric("置信度", result.confidence || "-")}
    </div>
    ${textBlock("目标专利", result.patent_id || "-")}
    ${textBlock("待评估分子", result.target_smiles || "-")}
    ${showReportActions ? infringementReportActions(jobId) : ""}
    ${renderImageGallery("报告图片", resultImagePaths(result))}
    ${listBlock("R-group 映射", objectToItems(result.fused_match?.r_group_matching))}
    ${result.failure_reason ? reportBlock("失败 / 无法判断原因", result.failure_reason) : ""}
    ${reportBlock("分析报告", result.report)}
  `;
}

function patentabilityResultHtml(result) {
  const success = result.success_analysis || {};
  const evidenceItems = [];
  const report = result.report || success.comprehensive_report;
  if (report) evidenceItems.push(`分析/证据1：${escapeHtml(report)}`);
  (result.prior_arts || []).forEach((item) => {
    evidenceItems.push(`分析/证据${evidenceItems.length + 1}：现有技术 ${escapeHtml(item.patent_id || item)}`);
  });
  (result.risk_points || []).forEach((item) => {
    evidenceItems.push(`分析/证据${evidenceItems.length + 1}：风险点 ${escapeHtml(item)}`);
  });
  (result.suggestions || success.improvement_suggestions || []).forEach((item) => {
    evidenceItems.push(`分析/证据${evidenceItems.length + 1}：改进建议 ${escapeHtml(item)}`);
  });
  return `
    <div class="result-metrics">
      ${metric("新颖性评分", formatScore(result.novelty_score))}
      ${metric("授权可能性", success.success_rate_estimation || "-")}
    </div>
    ${textBlock("一.最终结论", `新颖性评分：${formatScore(result.novelty_score)}；授权可能性：${success.success_rate_estimation || "-"}`)}
    ${listBlock("二.相关分析及证据", evidenceItems)}
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

function infringementReportActions(jobId) {
  if (!jobId) return "";
  return reportActions([
    { jobId, type: "infringement", label: "侵权分析报告" },
  ]);
}

function reportActions(items) {
  const links = (items || [])
    .filter((item) => item?.jobId && item?.type)
    .map(
      (item) => {
        const baseUrl = `/api/jobs/${encodeURIComponent(item.jobId)}/reports/${encodeURIComponent(item.type)}`;
        const label = item.label || "分析报告";
        return `
          <div class="download-group">
            <span>${escapeHtml(label)}</span>
            <a class="download-link" href="${baseUrl}.md" download>MD</a>
            <a class="download-link" href="${baseUrl}.pdf" download>PDF</a>
          </div>
        `;
      },
    )
    .join("");
  if (!links) return "";
  return `
    <article class="result-block report-actions">
      <h3>报告文件</h3>
      <div class="download-link-row">${links}</div>
    </article>
  `;
}

function renderImageGallery(title, imagePaths) {
  if (!imagePaths.length) return "";
  return `
    <article class="result-block">
      <h3>${escapeHtml(title)}</h3>
      <div class="step-image-grid">
        ${imagePaths
          .map(
            (path) => `
              <figure class="step-image">
                <img src="${publicFileUrl(path)}" alt="${escapeHtml(path)}" loading="lazy" />
                <figcaption>${escapeHtml(shortPath(path))}</figcaption>
              </figure>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function resultImagePaths(result) {
  const candidates = [
    result?.markush_structure?.source_image_path,
    result?.llm_outputs?.markush_image_selection?.selected?.image_path,
    result?.llm_outputs?.llm_markush_extraction?.image_path,
  ];
  const evaluations = result?.llm_outputs?.markush_image_selection?.evaluations || [];
  evaluations.slice(0, 3).forEach((item) => candidates.push(item?.image_path));
  return uniqueImagePaths(candidates);
}

function renderStepImages(output) {
  if (Number(output?.step) !== 2) return "";

  const imagePaths = stepOutputImagePaths(output);
  if (!imagePaths.length) return "";

  return `
    <div class="step-image-grid">
      ${imagePaths
        .map(
          (path) => `
            <figure class="step-image">
              <img src="${publicFileUrl(path)}" alt="${escapeHtml(path)}" loading="lazy" />
              <figcaption>${escapeHtml(shortPath(path))}</figcaption>
            </figure>
          `,
        )
        .join("")}
    </div>
  `;
}

function stepOutputImagePaths(output) {
  const data = output?.data || {};
  const candidates = [
    data.image_path,
    data.image?.path,
    data.image_selection?.selected?.image_path,
    data.markush_structure?.source_image_path,
    data.llm_response?.image_path,
    data.llm_response?.source_image_path,
  ];
  const evaluations = data.image_selection?.evaluations || [];
  evaluations.slice(0, 3).forEach((item) => candidates.push(item?.image_path));
  return uniqueImagePaths(candidates);
}

function uniqueImagePaths(candidates) {
  const seen = new Set();
  return candidates
    .filter((path) => typeof path === "string" && isImagePath(path))
    .filter((path) => {
      if (seen.has(path)) return false;
      seen.add(path);
      return true;
    });
}

function isImagePath(path) {
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(path.split("?")[0] || "");
}

function publicFileUrl(path) {
  return `/api/files?path=${encodeURIComponent(path)}`;
}

function shortPath(path) {
  return String(path || "").split(/[\\/]/).slice(-3).join("/");
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
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return String(isoString);
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function formatDateTime(isoString) {
  if (!isoString) return "-";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return String(isoString);
  return [
    date.getFullYear(),
    pad2(date.getMonth() + 1),
    pad2(date.getDate()),
  ].join("-") + ` ${formatTime(isoString)}`;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function isNearBottom(element) {
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight < 24;
}

function modeLabel(mode) {
  if (mode === "infringement") return "侵权分析";
  if (mode === "patentability") return "可授权分析";
  if (mode === "infringement_patentability") return "侵权分析 + 可授权分析";
  return "待命";
}

function visibleWorkflowLabel(mode = state.mode) {
  if (mode === "patentability" && state.chain?.infringementSnapshot) {
    return state.includePatentability ? "侵权分析 + 可授权分析" : "侵权分析";
  }
  if (mode === "infringement" || mode === "infringement_patentability") {
    return state.includePatentability ? "侵权分析 + 可授权分析" : "侵权分析";
  }
  return modeLabel(mode);
}

function statusText(status) {
  const map = {
    queued: "排队中",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已停止",
    pending: "等待",
    active: "运行中",
    done: "完成",
  };
  return map[status] || status || "等待";
}

function isTerminalStatus(status) {
  return ["succeeded", "failed", "cancelled"].includes(status);
}

function analysisStatusText(status) {
  const map = {
    protected: "已判定：落入",
    not_protected: "已判定：未落入",
    completed: "已完成",
    undetermined: "无法判断",
    failed: "任务失败",
  };
  return map[status] || status || "-";
}

function previousProtectionState(candidate) {
  const status = String(candidate?.analysis_status || "").toLowerCase();
  if (candidate?.is_protected === true || status === "protected") {
    return { label: "protected", className: "is-protected" };
  }
  if (candidate?.is_protected === false || status === "not_protected") {
    return { label: "not protected", className: "is-not-protected" };
  }
  return { label: "unknown", className: "is-unknown" };
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
