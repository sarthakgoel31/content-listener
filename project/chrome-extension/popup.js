/**
 * Popup script — handles UI interactions for the Chrome extension popup.
 */

// ── DOM refs ────────────────────────────────────────────────

const serverStatus = document.getElementById("server-status");
const tabs = document.querySelectorAll(".tab");
const tabContents = document.querySelectorAll(".tab-content");

// Capture tab
const pagePlatform = document.getElementById("page-platform");
const pageTitle = document.getElementById("page-title");
const captureObjective = document.getElementById("capture-objective");
const captureKindle = document.getElementById("capture-kindle");
const captureKindleSummary = document.getElementById("capture-kindle-summary");
const btnCapture = document.getElementById("btn-capture");
const captureResult = document.getElementById("capture-result");

// Batch tab
const batchMode = document.getElementById("batch-mode");
const fieldUrls = document.getElementById("field-urls");
const fieldChannel = document.getElementById("field-channel");
const batchUrls = document.getElementById("batch-urls");
const batchChannel = document.getElementById("batch-channel");
const batchCount = document.getElementById("batch-count");
const batchObjective = document.getElementById("batch-objective");
const batchQuestion = document.getElementById("batch-question");
const batchKindle = document.getElementById("batch-kindle");
const batchKindleSummary = document.getElementById("batch-kindle-summary");
const btnBatch = document.getElementById("btn-batch");
const batchResult = document.getElementById("batch-result");

// Status tab
const statusList = document.getElementById("status-list");
let statusInterval = null;

// History tab
const searchInput = document.getElementById("search-input");
const historyList = document.getElementById("history-list");

// Job bar
const jobBar = document.getElementById("job-bar");
const jobText = document.getElementById("job-text");
const jobEta = document.getElementById("job-eta");
const jobProgressBar = document.getElementById("job-progress-bar");
const jobProgressFill = document.getElementById("job-progress-fill");

// ── Tab switching ───────────────────────────────────────────

function switchToTab(tabName) {
  tabs.forEach((t) => t.classList.remove("active"));
  tabContents.forEach((tc) => tc.classList.remove("active"));
  const target = document.querySelector(`.tab[data-tab="${tabName}"]`);
  if (target) target.classList.add("active");
  const content = document.getElementById(`tab-${tabName}`);
  if (content) content.classList.add("active");

  if (tabName === "history") loadHistory();
  if (tabName === "status") {
    loadStatus();
    if (!statusInterval) statusInterval = setInterval(loadStatus, 3000);
  } else {
    if (statusInterval) { clearInterval(statusInterval); statusInterval = null; }
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    switchToTab(tab.dataset.tab);
  });
});

// ── Health check ────────────────────────────────────────────

function checkServer() {
  chrome.runtime.sendMessage({ action: "health" }, (res) => {
    if (res && res.ok) {
      serverStatus.classList.remove("offline");
      serverStatus.classList.add("online");
      serverStatus.title = "Server online";
    } else {
      serverStatus.classList.remove("online");
      serverStatus.classList.add("offline");
      serverStatus.title = "Server offline — start backend first";
    }
  });
}

checkServer();
setInterval(checkServer, 10000);

// ── Detect current page ─────────────────────────────────────

chrome.tabs.query({ active: true, currentWindow: true }, (tabList) => {
  const tab = tabList[0];
  if (!tab || !tab.url) return;

  const url = tab.url;
  let platform = "unknown";

  if (url.includes("youtube.com") || url.includes("youtu.be")) platform = "youtube";
  else if (url.includes("instagram.com")) platform = "instagram";
  else if (url.includes("spotify.com")) platform = "spotify";

  if (platform !== "unknown") {
    pagePlatform.textContent = platform;
    pageTitle.textContent = tab.title || url;
    btnCapture.disabled = false;
    btnCapture.dataset.url = url;
    btnCapture.dataset.title = tab.title || "";
  } else {
    pagePlatform.textContent = "-";
    pageTitle.textContent = "Navigate to YouTube, Instagram, or Spotify";
    btnCapture.disabled = true;
  }
});

// ── Capture button ──────────────────────────────────────────

btnCapture.addEventListener("click", () => {
  const url = btnCapture.dataset.url;
  const title = btnCapture.dataset.title;
  const objective = captureObjective.value.trim();

  btnCapture.disabled = true;
  showJobBar("Transcribing...");

  const sendToKindle = captureKindle.checked;
  const kindleSummarised = captureKindleSummary.checked;

  chrome.runtime.sendMessage(
    { action: "quick_capture", url, title, objective, send_to_kindle: sendToKindle, kindle_summarised: kindleSummarised },
    (res) => {
      if (res && res.error) {
        hideJobBar();
        showResult(captureResult, `<p style="color:#fca5a5">Error: ${res.error}</p>`);
        btnCapture.disabled = false;
        return;
      }
      if (res && res.job_id) {
        switchToTab("status");
        pollJob(res.job_id, captureResult, btnCapture);
      }
    }
  );
});

// ── Batch mode toggle ───────────────────────────────────────

batchMode.addEventListener("change", () => {
  if (batchMode.value === "channel") {
    fieldUrls.style.display = "none";
    fieldChannel.style.display = "block";
  } else {
    fieldUrls.style.display = "block";
    fieldChannel.style.display = "none";
  }
});

// ── Batch button ────────────────────────────────────────────

btnBatch.addEventListener("click", () => {
  const mode = batchMode.value;
  const payload = {
    action: "process",
    objective: batchObjective.value.trim(),
    question: batchQuestion.value.trim(),
    send_to_kindle: batchKindle.checked,
    kindle_summarised: batchKindleSummary.checked,
  };

  if (mode === "urls") {
    const urls = batchUrls.value
      .split("\n")
      .map((u) => u.trim())
      .filter((u) => u.length > 0);
    if (urls.length === 0) return alert("Enter at least one URL");
    payload.urls = urls;
  } else {
    const channel = batchChannel.value.trim();
    if (!channel) return alert("Enter a channel URL");
    payload.channel = channel;
    payload.count = parseInt(batchCount.value) || 10;
  }

  btnBatch.disabled = true;
  showJobBar("Processing batch...");

  chrome.runtime.sendMessage(payload, (res) => {
    if (res && res.error) {
      hideJobBar();
      showResult(batchResult, `<p style="color:#fca5a5">Error: ${res.error}</p>`);
      btnBatch.disabled = false;
      return;
    }
    if (res && res.job_id) {
      switchToTab("status");
      pollJob(res.job_id, batchResult, btnBatch);
    }
  });
});

// ── Job polling ─────────────────────────────────────────────

function pollJob(jobId, resultEl, btn) {
  const startTime = Date.now();
  const interval = setInterval(() => {
    chrome.runtime.sendMessage({ action: "job_status", job_id: jobId }, (job) => {
      if (!job) return;

      if (job.status === "processing") {
        const p = job.progress;
        if (p && p.message) {
          const countText = p.total > 1 ? ` (${p.current}/${p.total})` : "";
          showJobBar(`${p.message}${countText}`);

          // Show ETA
          if (p.eta_seconds) {
            jobEta.textContent = formatEta(p.eta_seconds);
          } else {
            jobEta.textContent = "";
          }

          // Show progress bar
          if (p.pct != null) {
            // Single-video Whisper progress
            jobProgressBar.style.display = "block";
            jobProgressFill.style.width = `${p.pct}%`;
          } else if (p.total > 1) {
            // Multi-URL batch progress
            jobProgressBar.style.display = "block";
            const pct = Math.round(((p.current - 1) / p.total) * 100);
            jobProgressFill.style.width = `${pct}%`;
          }
        } else {
          showJobBar(`Processing job #${jobId}...`);
        }
      } else if (job.status === "completed") {
        clearInterval(interval);
        hideJobBar();
        btn.disabled = false;
        renderResult(resultEl, job.result_data);
        loadStatus();
        loadHistory();
      } else if (job.status === "failed") {
        clearInterval(interval);
        hideJobBar();
        btn.disabled = false;
        showResult(resultEl, `<p style="color:#fca5a5">Failed: ${job.error || "Unknown error"}</p>`);
        loadStatus();
      }
    });
  }, 2000);
}

function formatEta(seconds) {
  if (seconds < 60) return `~${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `~${m}m ${s}s`;
}

// ── Result rendering ────────────────────────────────────────

function showResult(el, html) {
  el.innerHTML = html;
  el.style.display = "block";
}

function renderResult(el, data) {
  if (!data) {
    showResult(el, "<p>No data returned</p>");
    return;
  }

  let html = "";

  // Actionable result
  if (data.actionable) {
    const a = data.actionable;
    html += `<h3>Answer</h3><p>${escapeHtml(a.answer)}</p>`;
    html += `<span class="confidence confidence-${a.confidence}">${a.confidence} confidence</span>`;

    if (a.actionables && a.actionables.length > 0) {
      html += `<h3 style="margin-top:10px">Actionables</h3><ul>`;
      a.actionables.forEach((item) => {
        html += `<li>${escapeHtml(item)}</li>`;
      });
      html += `</ul>`;
    }
  }

  // Summaries
  if (data.summaries && data.summaries.length > 0) {
    html += `<h3 style="margin-top:10px">Summaries (${data.summaries.length})</h3>`;
    data.summaries.forEach((s) => {
      html += `<p><strong>${escapeHtml(s.title)}</strong></p>`;
      html += `<div class="md-summary">${markdownToHtml(s.summary)}</div>`;
    });
  }

  // Errors
  if (data.errors && data.errors.length > 0) {
    html += `<h3 style="margin-top:10px;color:#fca5a5">Errors</h3>`;
    data.errors.forEach((e) => {
      html += `<p style="color:#fca5a5">${escapeHtml(e)}</p>`;
    });
  }

  // Kindle status
  if (data.kindle_sent === true) {
    html += `<p style="margin-top:10px;color:#86efac">Transcript sent to Kindle!</p>`;
  }
  if (data.kindle_summary_sent === true) {
    html += `<p style="margin-top:4px;color:#86efac">Summary sent to Kindle!</p>`;
  }

  if (!html) html = "<p>Processing complete. No output to display.</p>";

  showResult(el, html);
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Lightweight markdown-to-HTML converter for summaries.
 * Handles: ## headings, ### subheadings, **bold**, - bullets, paragraphs.
 */
function markdownToHtml(md) {
  if (!md) return "";
  const lines = md.split("\n");
  const out = [];
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Close open list if this line isn't a bullet
    if (inList && !trimmed.startsWith("- ")) {
      out.push("</ul>");
      inList = false;
    }

    if (!trimmed) {
      continue; // blank line — paragraph break handled by block structure
    } else if (trimmed.startsWith("## ")) {
      out.push(`<h3 class="md-h2">${escapeHtml(trimmed.slice(3))}</h3>`);
    } else if (trimmed.startsWith("### ")) {
      out.push(`<h4 class="md-h3">${escapeHtml(trimmed.slice(4))}</h4>`);
    } else if (trimmed.startsWith("- ")) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inlineMd(trimmed.slice(2))}</li>`);
    } else {
      out.push(`<p>${inlineMd(trimmed)}</p>`);
    }
  }

  if (inList) out.push("</ul>");
  return out.join("\n");
}

/** Convert inline markdown (**bold**) to HTML, with escaping. */
function inlineMd(text) {
  // Escape HTML first, then apply bold
  let safe = escapeHtml(text);
  // **bold** → <strong>bold</strong>
  safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  return safe;
}

// ── History / Search ────────────────────────────────────────

function loadHistory() {
  chrome.runtime.sendMessage({ action: "list_transcripts", limit: 20 }, (res) => {
    if (res && res.results) {
      renderHistory(res.results);
    } else {
      historyList.innerHTML = '<p class="muted">Could not load history</p>';
    }
  });
}

let searchTimeout;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    const q = searchInput.value.trim();
    if (q.length < 2) {
      loadHistory();
      return;
    }
    chrome.runtime.sendMessage({ action: "search", query: q }, (res) => {
      if (res && res.results) {
        renderHistory(res.results);
      }
    });
  }, 400);
});

function renderHistory(items) {
  if (!items || items.length === 0) {
    historyList.innerHTML = '<p class="muted">No transcripts yet</p>';
    return;
  }

  historyList.innerHTML = items
    .map(
      (t) => `
    <div class="history-item" data-id="${t.id}">
      <div class="hi-title">${escapeHtml(t.title)}</div>
      <div class="hi-meta">${t.platform || "?"} &middot; ${t.source || ""} &middot; ${new Date(t.created_at).toLocaleDateString()}</div>
    </div>
  `
    )
    .join("");

  // Click handler for detail view
  historyList.querySelectorAll(".history-item").forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.dataset.id;
      el.classList.add("loading");
      chrome.runtime.sendMessage({ action: "transcript_detail", id: parseInt(id) }, (detail) => {
        el.classList.remove("loading");
        if (!detail || detail.error) {
          console.error("Detail fetch failed:", detail?.error);
          return;
        }
        renderHistoryDetail(detail);
      });
    });
  });
}

function renderHistoryDetail(t) {
  const tl = t.timeline || {};
  let html = `<div class="history-detail">`;
  html += `<button class="btn-back" id="btn-history-back">&larr; Back</button>`;
  html += `<h3>${escapeHtml(t.title)}</h3>`;
  html += `<div class="hi-meta">${t.platform || ""} &middot; ${t.source || ""} &middot; ${t.duration_seconds ? Math.round(t.duration_seconds / 60) + " min" : ""}</div>`;

  // Timeline
  html += `<div class="detail-section"><h4>Timeline</h4>`;
  html += `<div class="timeline">`;
  html += timelineRow("Requested", tl.requested_at, tl.requested_at);
  html += timelineRow("Transcribed", tl.transcribed_at, tl.requested_at);
  html += timelineRow("Summarized", tl.summarized_at, tl.transcribed_at);
  html += timelineRow("Kindle", tl.kindle_sent ? tl.transcribed_at : null, null, tl.kindle_sent);
  html += timelineRow("Kindle Summary", tl.kindle_summary_sent ? tl.summarized_at : null, null, tl.kindle_summary_sent);
  html += `</div></div>`;

  // Summary preview
  if (t.summaries && t.summaries.length > 0) {
    html += `<div class="detail-section"><h4>Summary</h4>`;
    html += `<div class="md-summary">${markdownToHtml(t.summaries[0].summary)}</div>`;
    html += `</div>`;
  }

  // Transcript preview
  if (t.transcript) {
    html += `<div class="detail-section"><h4>Transcript Preview</h4>`;
    html += `<p class="transcript-preview">${escapeHtml(t.transcript).substring(0, 300)}...</p>`;
    html += `</div>`;
  }

  html += `</div>`;
  historyList.innerHTML = html;

  document.getElementById("btn-history-back").addEventListener("click", () => {
    loadHistory();
  });
}

function timelineRow(label, timestamp, refTimestamp, explicitStatus) {
  const happened = explicitStatus !== undefined ? explicitStatus : !!timestamp;
  const icon = happened ? '<span class="tl-check">&#10003;</span>' : '<span class="tl-cross">&#10007;</span>';
  let timeStr = "";
  let takenStr = "";

  if (happened && timestamp) {
    const d = new Date(timestamp);
    timeStr = d.toLocaleTimeString();
    if (refTimestamp) {
      const ref = new Date(refTimestamp);
      const diffSec = Math.round((d - ref) / 1000);
      if (diffSec >= 0 && diffSec < 3600) {
        takenStr = diffSec < 60 ? `${diffSec}s` : `${Math.floor(diffSec / 60)}m ${diffSec % 60}s`;
      }
    }
  }

  return `
    <div class="tl-row ${happened ? "tl-done" : "tl-skip"}">
      ${icon}
      <span class="tl-label">${label}</span>
      <span class="tl-time">${timeStr}</span>
      ${takenStr ? `<span class="tl-taken">(${takenStr})</span>` : ""}
    </div>
  `;
}

// ── Status tab ──────────────────────────────────────────────

function loadStatus() {
  chrome.runtime.sendMessage({ action: "list_jobs", limit: 20 }, (res) => {
    // Server returns array directly, background.js wraps it as {results: [...]}
    const jobs = res?.results || (Array.isArray(res) ? res : null);
    if (jobs) {
      renderStatus(jobs);
    } else {
      statusList.innerHTML = '<p class="muted">Could not load jobs</p>';
    }
  });
}

function renderStatus(jobs) {
  if (!jobs || jobs.length === 0) {
    statusList.innerHTML = '<p class="muted">No jobs yet</p>';
    return;
  }

  statusList.innerHTML = jobs.map((job) => {
    const title = getJobTitle(job);
    const badge = statusBadge(job.status);
    const time = new Date(job.updated_at).toLocaleTimeString();
    let detail = "";

    if (job.status === "processing" && job.progress) {
      const p = job.progress;
      const msg = p.message || "Processing...";
      const pct = p.pct != null ? p.pct : 0;
      const eta = p.eta_seconds ? formatEta(p.eta_seconds) : "";
      const countText = p.total > 1 ? ` (${p.current}/${p.total})` : "";

      // Pipeline step indicator
      const stages = ["downloading", "transcribing", "summarizing", "done"];
      const stageLabels = { downloading: "Download", subtitles: "Subtitles", transcribing: "Transcribe", whisper_start: "Transcribe", summarizing: "Summarize", done: "Done" };
      const currentStage = p.stage || "downloading";
      detail += `<div class="pipeline-steps">`;
      stages.forEach((s) => {
        const stageIdx = stages.indexOf(s);
        const currentIdx = stages.indexOf(currentStage in stageLabels ? currentStage : "downloading");
        let cls = "step-pending";
        if (stageIdx < currentIdx || currentStage === "done") cls = "step-done";
        else if (stageIdx === currentIdx) cls = "step-active";
        // Map subtitles/whisper_start to transcribing for display
        const label = stageLabels[s] || s;
        detail += `<span class="pipeline-step ${cls}">${label}</span>`;
      });
      detail += `</div>`;

      detail += `<div class="status-detail">${escapeHtml(msg)}${countText}</div>`;
      detail += `
        <div class="status-progress">
          <div class="status-progress-fill" style="width:${pct}%"></div>
        </div>`;
      if (eta) {
        detail += `<div class="status-eta">${eta} remaining</div>`;
      }
    } else if (job.status === "completed" && job.result_data) {
      const r = job.result_data;
      const tCount = (r.transcripts || []).length;
      const sCount = (r.summaries || []).length;
      const errors = (r.errors || []).length;
      const kindleSent = r.kindle_sent || r.kindle_summary_sent;
      const source = tCount > 0 ? r.transcripts[0].source : "";
      let parts = [];
      if (tCount) parts.push(`${tCount} transcribed (${source})`);
      if (sCount) parts.push(`${sCount} summarized`);
      if (kindleSent) parts.push("sent to Kindle");
      if (errors) parts.push(`${errors} error(s)`);
      detail = `<div class="status-detail">${parts.join(" · ")}</div>`;
    } else if (job.status === "failed") {
      detail = `<div class="status-detail status-error">${escapeHtml(job.error || "Unknown error")}</div>`;
    }

    return `
      <div class="status-card status-${job.status}" data-job-id="${job.id}">
        <div class="status-header">
          <span class="status-title">${escapeHtml(title)}</span>
          ${badge}
        </div>
        ${detail}
        <div class="status-time">${time}</div>
      </div>
    `;
  }).join("");

  // Make completed/failed cards clickable to show detail
  statusList.querySelectorAll(".status-card").forEach((card) => {
    const jobId = card.dataset.jobId;
    if (!jobId) return;
    card.style.cursor = "pointer";
    card.addEventListener("click", () => {
      card.classList.add("loading");
      chrome.runtime.sendMessage({ action: "job_status", job_id: parseInt(jobId) }, (job) => {
        card.classList.remove("loading");
        if (!job) return;
        renderStatusDetail(job);
      });
    });
  });
}

function renderStatusDetail(job) {
  const title = getJobTitle(job);
  let html = `<div class="history-detail">`;
  html += `<button class="btn-back" id="btn-status-back">&larr; Back</button>`;
  html += `<h3>${escapeHtml(title)}</h3>`;
  html += statusBadge(job.status);

  // Timing
  const created = new Date(job.created_at);
  const updated = new Date(job.updated_at);
  const durationSec = Math.round((updated - created) / 1000);
  const durationStr = durationSec < 60 ? `${durationSec}s` : `${Math.floor(durationSec / 60)}m ${durationSec % 60}s`;
  html += `<div class="hi-meta" style="margin-top:6px">Started ${created.toLocaleTimeString()} · Took ${durationStr}</div>`;

  // Pipeline steps (completed)
  if (job.progress) {
    const p = job.progress;
    html += `<div class="detail-section"><h4>Pipeline</h4>`;
    const stages = ["downloading", "transcribing", "summarizing", "done"];
    const stageLabels = { downloading: "Download", transcribing: "Transcribe", summarizing: "Summarize", done: "Complete" };
    const currentStage = p.stage || "done";
    html += `<div class="pipeline-steps pipeline-steps-detail">`;
    stages.forEach((s) => {
      const stageIdx = stages.indexOf(s);
      const currentIdx = stages.indexOf(currentStage);
      let cls = "step-pending";
      if (job.status === "completed" || stageIdx <= currentIdx) cls = "step-done";
      else if (stageIdx === currentIdx) cls = "step-active";
      html += `<span class="pipeline-step ${cls}">${stageLabels[s] || s}</span>`;
    });
    html += `</div></div>`;
  }

  // Result data
  if (job.status === "completed" && job.result_data) {
    const r = job.result_data;

    if (r.transcripts && r.transcripts.length > 0) {
      html += `<div class="detail-section"><h4>Transcripts (${r.transcripts.length})</h4>`;
      r.transcripts.forEach((t) => {
        const dur = t.duration_seconds ? `${Math.round(t.duration_seconds / 60)} min` : "";
        html += `<div class="status-result-item">`;
        html += `<strong>${escapeHtml(t.title)}</strong>`;
        html += `<span class="hi-meta">${t.source || ""} ${dur ? "· " + dur : ""}</span>`;
        html += `</div>`;
      });
      html += `</div>`;
    }

    if (r.summaries && r.summaries.length > 0) {
      html += `<div class="detail-section"><h4>Summary</h4>`;
      html += `<div class="md-summary">${markdownToHtml(r.summaries[0].summary)}</div>`;
      html += `</div>`;
    }

    if (r.actionable) {
      html += `<div class="detail-section"><h4>Answer</h4>`;
      html += `<p>${escapeHtml(r.actionable.answer)}</p>`;
      if (r.actionable.actionables && r.actionable.actionables.length > 0) {
        html += `<ul>`;
        r.actionable.actionables.forEach((a) => { html += `<li>${escapeHtml(a)}</li>`; });
        html += `</ul>`;
      }
      html += `</div>`;
    }

    if (r.kindle_sent) html += `<p style="color:#86efac;margin-top:6px">Transcript sent to Kindle</p>`;
    if (r.kindle_summary_sent) html += `<p style="color:#86efac;margin-top:4px">Summary sent to Kindle</p>`;

    if (r.errors && r.errors.length > 0) {
      html += `<div class="detail-section"><h4 style="color:#fca5a5">Errors</h4>`;
      r.errors.forEach((e) => { html += `<p style="color:#fca5a5">${escapeHtml(e)}</p>`; });
      html += `</div>`;
    }
  }

  if (job.status === "failed") {
    html += `<div class="detail-section"><h4 style="color:#fca5a5">Error</h4>`;
    html += `<p style="color:#fca5a5">${escapeHtml(job.error || "Unknown error")}</p>`;
    html += `</div>`;
  }

  html += `</div>`;
  statusList.innerHTML = html;

  document.getElementById("btn-status-back").addEventListener("click", () => {
    loadStatus();
  });
}

function getJobTitle(job) {
  // Try to get actual video title from result data first
  if (job.result_data && job.result_data.transcripts && job.result_data.transcripts.length > 0) {
    const t = job.result_data.transcripts[0];
    if (t.title) {
      if (job.result_data.transcripts.length > 1) {
        return `${t.title} (+${job.result_data.transcripts.length - 1} more)`;
      }
      return t.title;
    }
  }
  // Try progress title
  if (job.progress && job.progress.message) {
    const m = job.progress.message;
    if (m.startsWith("Video: ")) return m.replace("Video: ", "").split(" (")[0];
  }
  // Fallback to input data
  if (!job.input_data) return `Job #${job.id}`;
  const d = job.input_data;
  if (d.channel) return d.channel.replace(/https?:\/\/(www\.)?youtube\.com\//g, "");
  if (d.urls && d.urls.length > 0) {
    if (d.urls.length === 1) return d.urls[0].replace(/https?:\/\/(www\.)?youtube\.com\/watch\?v=/g, "");
    return `${d.urls.length} URLs`;
  }
  return `Job #${job.id}`;
}

function statusBadge(status) {
  return `<span class="status-badge status-badge-${status}">${status}</span>`;
}

// ── Job bar helpers ─────────────────────────────────────────

function showJobBar(text) {
  jobText.textContent = text;
  jobBar.style.display = "flex";
}

function hideJobBar() {
  jobBar.style.display = "none";
  jobEta.textContent = "";
  jobProgressBar.style.display = "none";
  jobProgressFill.style.width = "0%";
}

// ── Listen for background job completions ───────────────────

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "job_complete") {
    hideJobBar();
    // Auto-refresh both tabs so data is fresh
    loadStatus();
    loadHistory();
  }
});
