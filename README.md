# VidText

**Transcribe, summarize, and extract actionables from any video or podcast -- for free.**

Paste a URL. Get a transcript, summary, and action items. Send it to your Kindle.

---

## Why

You watch a 45-minute YouTube video and forget everything by the next day. You listen to a podcast while driving and can't take notes. You want to batch-process a channel's content but there's no free tool that does it.

VidText solves this: give it any YouTube video, Instagram Reel, or Spotify podcast URL, and it returns a full transcript, an objective-focused summary, and concrete actionable items. Runs as a CLI, API server, or Chrome extension. Transcription is zero-cost (local Whisper). Summarization uses Claude API or a built-in local extractive summarizer for a completely free pipeline.

---

## Features

| Feature | Description |
|---------|-------------|
| Multi-Platform | YouTube videos, Instagram Reels, Spotify podcasts |
| Smart Transcription | Auto-selects Whisper model based on audio length and quality |
| Objective-Focused Summary | Summarizes relative to your specific question or goal |
| Actionable Extraction | Pulls concrete next steps and takeaways |
| Chrome Extension | One-click transcription while browsing (Manifest V3) |
| Kindle Sender | Send formatted transcripts directly to your Kindle |
| Channel Mode | Batch-process N videos from a channel (`--channel URL --count N`) |
| FastAPI Server | REST API backend for browser extension and programmatic access |
| Local Summarizer | Free extractive summarizer as alternative to Claude API |
| Transcript Formatter | Cleans raw Whisper output into readable paragraphs |
| Job Tracking | SQLite persistence for all transcripts, summaries, and job progress |

---

## How It Works

```
URL --> yt-dlp (download audio)
    --> Whisper (local STT, model auto-selected)
    --> SQLite (store transcript)
    --> LLM Summarizer (Claude API or local extractive mode)
    --> LLM Actionable Extractor
    --> Output: CLI / REST API / Chrome Extension / Kindle
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI + Uvicorn |
| Transcription | OpenAI Whisper (local, free) |
| Summarization | Anthropic Claude API or local extractive mode |
| Video Download | yt-dlp |
| Validation | Pydantic v2 |
| Chrome Extension | Vanilla JS + Manifest V3 |
| Database | SQLite |

---

## Architecture

```
agent/
└── content_agent.py           -- Orchestrator (calls skills in sequence)

skill/
├── transcriber.py             -- yt-dlp + Whisper pipeline
├── summarizer.py              -- LLM-powered summarization
├── local_summarizer.py        -- Free extractive summarizer (no API)
├── transcript_formatter.py    -- Raw Whisper → readable paragraphs
├── actionable_extractor.py    -- Concrete takeaway extraction
└── kindle_sender.py           -- Format + email to Kindle

project/
├── backend/
│   └── server.py              -- FastAPI server (port 8420)
└── chrome-extension/          -- Manifest V3 browser extension

output/
└── content_listener.db        -- SQLite job + transcript storage
```

---

## Getting Started

```bash
git clone https://github.com/sarthakgoel31/content-listener.git
cd content-listener
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Prerequisites:** Python 3.11+, ffmpeg (`brew install ffmpeg`)

### CLI

```bash
# Single video
python -m agent.content_agent \
  --urls "https://youtube.com/watch?v=..." \
  --objective "Learn about X" \
  --question "What are the key takeaways?"

# Batch channel processing
python -m agent.content_agent \
  --channel "https://youtube.com/@channel" \
  --count 10 \
  --objective "..."
```

### Server

```bash
python -m project.backend.server
# Runs at http://localhost:8420
```

### Chrome Extension

1. Open `chrome://extensions/`
2. Enable Developer Mode
3. Load unpacked → select `project/chrome-extension/`

---

## Status

| Component | Status |
|-----------|--------|
| YouTube transcription | Done |
| Instagram Reel support | Done |
| Spotify podcast support | Done |
| Whisper model auto-selection | Done |
| Objective-focused summarization | Done |
| Local extractive summarizer | Done |
| Actionable extraction | Done |
| Transcript formatter | Done |
| Chrome extension | Done |
| Kindle sender | Done |
| Channel batch mode | Done |
| FastAPI server | Done |
| SQLite persistence | Done |

---

<p align="center">
  <sub>Built with <a href="https://claude.ai/claude-code">Claude Code</a></sub>
</p>
