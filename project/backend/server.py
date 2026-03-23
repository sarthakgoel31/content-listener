"""
FastAPI server — backend for the Chrome extension and API consumers.

Run: uvicorn project.backend.server:app --reload --port 8420
"""

import sys
import os
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from project.backend.db import (
    create_job, get_job, get_active_jobs, get_all_transcripts, get_transcript,
    get_transcript_detail, search_transcripts,
)
from agent.content_agent import process_job_async
from skill.local_summarizer import local_summarize, format_kindle_summary
from skill.kindle_sender import send_html_to_kindle, format_for_kindle

app = FastAPI(title="VidText", version="1.1.0")

# Allow Chrome extension and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to extension ID
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ──────────────────────────────────────────

class ProcessRequest(BaseModel):
    urls: list[str] = []
    channel: str | None = None
    count: int = 10
    objective: str = ""
    question: str = ""
    send_to_kindle: bool = False
    kindle_summarised: bool = False


class QuickCaptureRequest(BaseModel):
    url: str
    title: str = ""
    objective: str = ""
    send_to_kindle: bool = False
    kindle_summarised: bool = False


class KindleSendRequest(BaseModel):
    transcript_id: int
    mode: str = "transcript"  # "transcript" | "summary" | "both"


# ── Endpoints ───────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "content-listener-agent"}


@app.post("/process")
def start_processing(req: ProcessRequest):
    """
    Start a processing job (async). Returns a job_id to poll.
    Use this for batch operations (multiple URLs, channel scraping).
    """
    if not req.urls and not req.channel:
        raise HTTPException(400, "Provide 'urls' or 'channel'")

    input_data = req.model_dump()
    job_id = create_job("process", input_data)

    # Run in background thread
    thread = threading.Thread(
        target=process_job_async,
        args=(job_id, input_data),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@app.get("/job/{job_id}")
def get_job_status(job_id: int):
    """Poll job status and get results when complete."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/quick-capture")
def quick_capture(req: QuickCaptureRequest):
    """
    Quick capture from Chrome extension — starts transcription of current page.
    Returns job_id for polling.
    """
    input_data = {
        "urls": [req.url],
        "objective": req.objective,
        "question": "",
        "send_to_kindle": req.send_to_kindle,
        "kindle_summarised": req.kindle_summarised,
    }
    job_id = create_job("quick_capture", input_data)

    thread = threading.Thread(
        target=process_job_async,
        args=(job_id, input_data),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending", "url": req.url}


@app.get("/jobs")
def list_jobs(limit: int = 20):
    """List recent jobs with progress info. Active jobs first."""
    return get_active_jobs(limit=limit)


@app.get("/transcripts")
def list_transcripts(limit: int = 50):
    """List stored transcripts."""
    return get_all_transcripts(limit=limit)


@app.get("/transcripts/{transcript_id}")
def read_transcript(transcript_id: int, detail: bool = False):
    """Get a specific transcript. Pass ?detail=true to include summaries and actionables."""
    if detail:
        t = get_transcript_detail(transcript_id)
    else:
        t = get_transcript(transcript_id)
    if not t:
        raise HTTPException(404, "Transcript not found")
    return t


@app.post("/kindle-send")
def kindle_send(req: KindleSendRequest):
    """
    Send a stored transcript to Kindle as transcript, summary, or both.
    Works with locally stored transcripts — no API needed.
    """
    t = get_transcript(req.transcript_id)
    if not t:
        raise HTTPException(404, "Transcript not found")

    title = t["title"] or "Untitled"
    transcript = t["transcript"] or ""
    results = {"transcript_sent": False, "summary_sent": False}

    if req.mode in ("transcript", "both"):
        html = format_for_kindle(title=title, transcript=transcript)
        results["transcript_sent"] = send_html_to_kindle(f"{title} — Transcript", html)

    if req.mode in ("summary", "both"):
        summary_text = local_summarize(transcript, title=title)
        html = format_kindle_summary(title, transcript, summary_text)
        results["summary_sent"] = send_html_to_kindle(f"{title} — Summary", html)

    return results


@app.get("/search")
def search(q: str, limit: int = 20):
    """Search transcripts by title or content."""
    return search_transcripts(q, limit=limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420)
