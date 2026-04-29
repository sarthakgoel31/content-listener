# VidText (Content Listener)

**Transcribe, summarize, and extract actionables from any video or podcast.**

---

## What It Does

VidText takes a YouTube video, Instagram Reel, or Spotify podcast URL and produces a full transcript, an objective-focused summary, and a list of actionable items. It runs as a CLI tool, a FastAPI server, or through a Chrome extension -- with optional Kindle delivery for long-form content.

**Cost model:** Transcription is zero-cost (local Whisper). Summarization uses the Anthropic Claude API (requires a paid API key), or you can use the built-in local extractive summarizer (`local_summarizer.py`) for a completely free pipeline.

---

## Key Features

- **Multi-Platform Support** -- YouTube videos, Instagram Reels, and Spotify podcasts
- **Smart Transcription** -- Automatic Whisper model selection based on audio length and quality (free, local)
- **Objective-Focused Summaries** -- Summarizes content relative to your specific objective or question
- **Actionable Extraction** -- Pulls out concrete next steps and takeaways from any content
- **Chrome Extension** -- Browser extension with overlay UI for one-click transcription while browsing
- **Kindle Sender** -- Send formatted transcripts and summaries directly to your Kindle device
- **Channel Mode** -- Process multiple videos from a channel in batch (`--channel URL --count N`)
- **FastAPI Server** -- REST API backend for the Chrome extension and programmatic access
- **Agent Architecture** -- Modular skill-based design (transcriber, summarizer, actionable extractor, kindle sender)
- **Job Tracking** -- Persistent database for transcript/summary/actionable storage with job progress tracking
- **Local Summarizer** -- Free extractive summarizer (`local_summarizer.py`) as an alternative to the Claude API
- **Transcript Formatter** -- Cleans and structures raw Whisper output into readable paragraphs (`transcript_formatter.py`)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI + Uvicorn |
| Transcription | OpenAI Whisper (local, free) |
| Summarization | Anthropic Claude API or local extractive mode |
| Video Download | yt-dlp |
| Image Processing | Pillow |
| Validation | Pydantic v2 |
| Chrome Extension | Vanilla JS + Manifest V3 |
| Database | SQLite (via backend) |

---

## Getting Started

### Prerequisites

- Python 3.11+
- ffmpeg installed (`brew install ffmpeg` on macOS)

### Installation

```bash
git clone https://github.com/sarthakgoel31/content-listener.git
cd content-listener
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### CLI Usage

```bash
# Transcribe and summarize a single video
python -m agent.content_agent --urls "https://youtube.com/watch?v=..." --objective "Learn about X" --question "What are the key takeaways?"

# Process multiple videos from a channel
python -m agent.content_agent --channel "https://youtube.com/@channel" --count 10 --objective "..."
```

### Server

```bash
python -m project.backend.server
```

Server runs at [http://localhost:8420](http://localhost:8420).

### Chrome Extension

1. Open `chrome://extensions/` in Chrome
2. Enable Developer Mode
3. Click "Load unpacked" and select `project/chrome-extension/`

---

## Architecture

The system uses an agent-skill architecture: the `content_agent` orchestrates the pipeline by calling independent skills (transcriber, summarizer, actionable extractor, kindle sender) in sequence. Each skill is a standalone module with no cross-dependencies. The FastAPI server wraps the same agent for browser-based access, while the Chrome extension communicates with the server via REST. Job state and results are persisted in SQLite for retrieval.

```
URL --> Transcriber (yt-dlp + Whisper) --> Summarizer (LLM)
    --> Actionable Extractor (LLM) --> Output (CLI / API / Kindle)
```

---

<p align="center">
  <sub>Built with <a href="https://claude.ai/claude-code">Claude Code</a></sub>
</p>
