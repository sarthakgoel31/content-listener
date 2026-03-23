/**
 * Content script — detects current platform, extracts page metadata,
 * and injects a floating capture button on supported sites.
 */

(function () {
  if (document.getElementById("cl-agent-fab")) return;

  function detectPlatform() {
    const host = window.location.hostname;
    if (host.includes("youtube.com")) return "youtube";
    if (host.includes("instagram.com")) return "instagram";
    if (host.includes("spotify.com")) return "spotify";
    return "unknown";
  }

  function getPageInfo() {
    const platform = detectPlatform();
    const url = window.location.href;
    let title = document.title;

    if (platform === "youtube") {
      const ytTitle = document.querySelector(
        "h1.ytd-video-primary-info-renderer, h1.ytd-watch-metadata yt-formatted-string"
      );
      if (ytTitle) title = ytTitle.textContent.trim();
    }

    return { platform, url, title };
  }

  function isContentPage() {
    const platform = detectPlatform();
    const path = window.location.pathname;

    if (platform === "youtube") return path.startsWith("/watch") || path.startsWith("/shorts");
    if (platform === "instagram") return path.startsWith("/reel") || path.startsWith("/p/");
    if (platform === "spotify") return path.includes("/episode/") || path.includes("/show/");
    return false;
  }

  // ── Floating action button ──────────────────────────────

  function createFAB() {
    const fab = document.createElement("div");
    fab.id = "cl-agent-fab";
    fab.innerHTML = `
      <div class="cl-fab-btn" id="cl-fab-main">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      </div>
      <div class="cl-fab-menu" id="cl-fab-menu" style="display:none;">
        <button class="cl-fab-action" id="cl-capture-btn">Capture & Transcribe</button>
        <button class="cl-fab-action" id="cl-summarize-btn">Capture & Summarize</button>
      </div>
      <div class="cl-fab-status" id="cl-fab-status" style="display:none;"></div>
    `;
    document.body.appendChild(fab);

    const mainBtn = document.getElementById("cl-fab-main");
    const menu = document.getElementById("cl-fab-menu");

    mainBtn.addEventListener("click", () => {
      menu.style.display = menu.style.display === "none" ? "flex" : "none";
    });

    document.getElementById("cl-capture-btn").addEventListener("click", () => {
      triggerCapture("");
      menu.style.display = "none";
    });

    document.getElementById("cl-summarize-btn").addEventListener("click", () => {
      const objective = prompt("What's your objective? (optional)") || "";
      triggerCapture(objective);
      menu.style.display = "none";
    });
  }

  function showStatus(text, type = "info") {
    const el = document.getElementById("cl-fab-status");
    if (!el) return;
    el.textContent = text;
    el.className = `cl-fab-status cl-status-${type}`;
    el.style.display = "block";

    if (type === "success" || type === "error") {
      setTimeout(() => {
        el.style.display = "none";
      }, 5000);
    }
  }

  function triggerCapture(objective) {
    const info = getPageInfo();
    showStatus("Sending to agent...", "info");

    chrome.runtime.sendMessage(
      {
        action: "quick_capture",
        url: info.url,
        title: info.title,
        objective: objective,
      },
      (response) => {
        if (response && response.error) {
          showStatus("Error: " + response.error, "error");
          return;
        }
        if (response && response.job_id) {
          showStatus("Processing... (job #" + response.job_id + ")", "info");
          pollForResult(response.job_id);
        }
      }
    );
  }

  function pollForResult(jobId) {
    const interval = setInterval(() => {
      chrome.runtime.sendMessage(
        { action: "job_status", job_id: jobId },
        (job) => {
          if (!job) return;
          if (job.status === "completed") {
            clearInterval(interval);
            showStatus("Done! Check extension popup for results.", "success");
          } else if (job.status === "failed") {
            clearInterval(interval);
            showStatus("Failed: " + (job.error || "unknown error"), "error");
          }
        }
      );
    }, 3000);
  }

  // ── Init ────────────────────────────────────────────────

  if (isContentPage()) {
    createFAB();
  }

  // Handle SPA navigation (YouTube)
  let lastUrl = window.location.href;
  const observer = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      const existing = document.getElementById("cl-agent-fab");
      if (existing) existing.remove();
      if (isContentPage()) createFAB();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
