const state = {
  mode: "infringement",
  jobId: null,
  pollTimer: null,
  blueprints: {},
};

const els = {
  modeButtons: Array.from(document.querySelectorAll(".mode-button")),
  infringementForm: document.getElementById("infringement-form"),
  patentabilityForm: document.getElementById("patentability-form"),
  agentGrid: document.getElementById("agent-grid"),
  eventLog: document.getElementById("event-log"),
  resultPanel: document.getElementById("result-panel"),
  jobMode: document.getElementById("job-mode"),
  jobStatus: document.getElementById("job-status"),
  jobId: document.getElementById("job-id"),
  jobEvents: document.getElementById("job-events"),
};

async function init() {
  const response = await fetch("/api/blueprints");
  state.blueprints = await response.json();
  bindEvents();
  renderAgentGrid(state.blueprints[state.mode] || []);
}

function bindEvents() {
  els.modeButtons.forEach((button) => {
    button.addEventListener("click", () => switchMode(button.dataset.mode));
  });

  els.infringementForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const form = new FormData(event.currentTarget);
      const payload = {
        patent_id: form.get("patent_id"),
        smiles: form.get("smiles"),
        caption: form.get("caption"),
      };
      const response = await fetch("/api/infringement", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await parseResponse(response);
      startPolling(data.job_id, "侵权分析");
    } catch (error) {
      renderClientError(error);
    }
  });

  els.patentabilityForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const form = new FormData(event.currentTarget);
      const response = await fetch("/api/patentability", {
        method: "POST",
        body: form,
      });
      const data = await parseResponse(response);
      startPolling(data.job_id, "可专利性评估");
    } catch (error) {
      renderClientError(error);
    }
  });
}

function switchMode(mode) {
  state.mode = mode;
  els.modeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mode === mode);
  });
  els.infringementForm.classList.toggle("is-hidden", mode !== "infringement");
  els.patentabilityForm.classList.toggle("is-hidden", mode !== "patentability");
  renderAgentGrid(state.blueprints[mode] || []);
}

function startPolling(jobId, label) {
  state.jobId = jobId;
  els.jobMode.textContent = label;
  els.jobStatus.textContent = "Queued";
  els.jobId.textContent = jobId;
  els.jobEvents.textContent = "0";
  els.eventLog.innerHTML = `<div class="log-empty">任务 ${jobId} 已提交，正在等待后端响应。</div>`;
  els.resultPanel.innerHTML = `<div class="result-empty">任务运行中，结果完成后展示。</div>`;

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
  els.jobStatus.textContent = snapshot.status;
  els.jobEvents.textContent = String(snapshot.event_count);
  renderAgentGrid(snapshot.agents || []);
  renderEventLog(snapshot.events || []);
  renderResult(snapshot);
}

function renderAgentGrid(agents) {
  if (!agents.length) {
    els.agentGrid.innerHTML = "";
    return;
  }
  els.agentGrid.innerHTML = agents
    .map((agent) => {
      const cls =
        agent.status === "active"
          ? "agent-card is-active"
          : agent.status === "done"
            ? "agent-card is-done"
            : "agent-card";
      return `
        <article class="${cls}">
          <div class="agent-meta">
            <span class="agent-order">${agent.order}</span>
            <span class="agent-status">${statusText(agent.status)}</span>
          </div>
          <h3>${escapeHtml(agent.name)}</h3>
          <p>${escapeHtml(agent.detail)}</p>
        </article>
      `;
    })
    .join("");
}

function renderEventLog(events) {
  if (!events.length) {
    els.eventLog.innerHTML = `<div class="log-empty">任务开始后，这里会显示 pipeline 事件流。</div>`;
    return;
  }
  els.eventLog.innerHTML = events
    .map(
      (event) => `
        <article class="event-item">
          <div class="event-topline">
            <span class="event-level ${event.level}">${escapeHtml(event.level)}</span>
            <span>${formatTime(event.timestamp)}</span>
          </div>
          <div class="event-message">${escapeHtml(event.message)}</div>
          <div class="event-meta">${escapeHtml(event.agent || "Pipeline")} ${
            event.step ? `· Step ${event.step}/${event.total_steps || "?"}` : ""
          }</div>
        </article>
      `,
    )
    .join("");
}

function renderResult(snapshot) {
  if (snapshot.status === "failed") {
    els.resultPanel.innerHTML = `
      <article class="result-card">
        <h3>任务失败</h3>
        <pre>${escapeHtml(snapshot.error?.message || "Unknown error")}</pre>
      </article>
      ${
        snapshot.error?.traceback
          ? `<article class="result-card"><h3>Traceback</h3><pre>${escapeHtml(snapshot.error.traceback)}</pre></article>`
          : ""
      }
    `;
    return;
  }

  if (snapshot.status !== "succeeded" || !snapshot.result) {
    els.resultPanel.innerHTML = `<div class="result-empty">任务运行中，结果完成后展示。</div>`;
    return;
  }

  const result = snapshot.result;
  if (snapshot.mode === "infringement") {
    els.resultPanel.innerHTML = `
      ${metricCard("保护范围判断", result.is_protected ? "Protected" : "Not Protected")}
      ${metricCard("置信度", result.confidence || "-")}
      ${textCard("Patent ID", result.patent_id || "-")}
      ${textCard("Target SMILES", result.target_smiles || "-")}
      ${listCard("R 基团映射", objectToItems(result.fused_match?.r_group_matching))}
      ${reportCard("分析报告", result.report)}
    `;
    return;
  }

  els.resultPanel.innerHTML = `
    ${metricCard("新颖性评分", formatScore(result.novelty_score))}
    ${metricCard("先有技术数量", String((result.prior_arts || []).length))}
    ${listCard(
      "风险点",
      (result.risk_points || []).map((item) => escapeHtml(item))
    )}
    ${listCard(
      "建议",
      (result.suggestions || []).map((item) => escapeHtml(item))
    )}
    ${listCard(
      "相关专利",
      (result.prior_arts || []).map((item) => escapeHtml(item.patent_id))
    )}
    ${reportCard("分析报告", result.report)}
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
    <article class="result-card">
      <h3>请求失败</h3>
      <pre>${escapeHtml(error.message || String(error))}</pre>
    </article>
  `;
}

function metricCard(title, value) {
  return `<article class="result-card"><h3>${escapeHtml(title)}</h3><pre>${escapeHtml(value)}</pre></article>`;
}

function textCard(title, value) {
  return `<article class="result-card"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(value)}</p></article>`;
}

function listCard(title, items) {
  if (!items || !items.length) {
    return `<article class="result-card"><h3>${escapeHtml(title)}</h3><p>无</p></article>`;
  }
  return `<article class="result-card"><h3>${escapeHtml(title)}</h3><ul>${items
    .map((item) => `<li>${item}</li>`)
    .join("")}</ul></article>`;
}

function reportCard(title, content) {
  return `<article class="result-card"><h3>${escapeHtml(title)}</h3><pre>${escapeHtml(
    content || "无报告内容",
  )}</pre></article>`;
}

function objectToItems(obj) {
  if (!obj || typeof obj !== "object") return [];
  return Object.entries(obj).map(([key, value]) => `${escapeHtml(key)}: ${escapeHtml(String(value))}`);
}

function formatScore(value) {
  if (typeof value !== "number") return "-";
  return value.toFixed(2);
}

function formatTime(isoString) {
  if (!isoString) return "-";
  return new Date(isoString).toLocaleTimeString();
}

function statusText(status) {
  if (status === "active") return "Running";
  if (status === "done") return "Done";
  return "Pending";
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
