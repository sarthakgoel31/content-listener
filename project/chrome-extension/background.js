/**
 * Background service worker — handles API communication with the backend server.
 */

const API_BASE = "http://localhost:8420";

// Poll interval for job status (ms)
const POLL_INTERVAL = 3000;

// ── API helpers ─────────────────────────────────────────────

async function apiCall(endpoint, method = "GET", body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${endpoint}`, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

async function checkHealth() {
  try {
    const data = await apiCall("/health");
    return data.status === "ok";
  } catch {
    return false;
  }
}

async function startProcess(payload) {
  return apiCall("/process", "POST", payload);
}

async function quickCapture(url, title, objective, sendToKindle = false, kindleSummarised = false) {
  return apiCall("/quick-capture", "POST", { url, title, objective, send_to_kindle: sendToKindle, kindle_summarised: kindleSummarised });
}

async function getJobStatus(jobId) {
  return apiCall(`/job/${jobId}`);
}

async function searchTranscripts(query) {
  return apiCall(`/search?q=${encodeURIComponent(query)}`);
}

async function listJobs(limit = 20) {
  return apiCall(`/jobs?limit=${limit}`);
}

async function getTranscriptDetail(id) {
  return apiCall(`/transcripts/${id}?detail=true`);
}

async function listTranscripts(limit = 20) {
  return apiCall(`/transcripts?limit=${limit}`);
}

// ── Job polling ─────────────────────────────────────────────

function pollJob(jobId, callback) {
  const interval = setInterval(async () => {
    try {
      const job = await getJobStatus(jobId);
      if (job.status === "completed" || job.status === "failed") {
        clearInterval(interval);
        callback(job);
      }
    } catch (err) {
      clearInterval(interval);
      callback({ status: "failed", error: err.message });
    }
  }, POLL_INTERVAL);

  return interval;
}

// ── Message handler (popup & content script communication) ──

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.action) {
        case "health": {
          const ok = await checkHealth();
          sendResponse({ ok });
          break;
        }

        case "quick_capture": {
          const result = await quickCapture(msg.url, msg.title, msg.objective || "", msg.send_to_kindle || false, msg.kindle_summarised || false);
          // Start polling
          pollJob(result.job_id, (job) => {
            chrome.runtime.sendMessage({
              action: "job_complete",
              job_id: result.job_id,
              result: job,
            });
          });
          sendResponse({ job_id: result.job_id, status: "started" });
          break;
        }

        case "process": {
          const result = await startProcess({
            urls: msg.urls || [],
            channel: msg.channel || null,
            count: msg.count || 10,
            objective: msg.objective || "",
            question: msg.question || "",
            send_to_kindle: msg.send_to_kindle || false,
            kindle_summarised: msg.kindle_summarised || false,
          });
          pollJob(result.job_id, (job) => {
            chrome.runtime.sendMessage({
              action: "job_complete",
              job_id: result.job_id,
              result: job,
            });
          });
          sendResponse({ job_id: result.job_id, status: "started" });
          break;
        }

        case "job_status": {
          const job = await getJobStatus(msg.job_id);
          sendResponse(job);
          break;
        }

        case "search": {
          const results = await searchTranscripts(msg.query);
          sendResponse({ results });
          break;
        }

        case "list_jobs": {
          const results = await listJobs(msg.limit || 20);
          sendResponse({ results });
          break;
        }

        case "transcript_detail": {
          const detail = await getTranscriptDetail(msg.id);
          sendResponse(detail);
          break;
        }

        case "list_transcripts": {
          const results = await listTranscripts(msg.limit || 20);
          sendResponse({ results });
          break;
        }

        default:
          sendResponse({ error: "Unknown action" });
      }
    } catch (err) {
      sendResponse({ error: err.message });
    }
  })();

  return true; // keep channel open for async response
});
