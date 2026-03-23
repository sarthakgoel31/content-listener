#!/bin/bash
# Content Listener Agent — Setup Script
set -e

cd "$(dirname "$0")"

echo "=== Content Listener Agent Setup ==="

# 1. Create venv
if [ ! -d ".venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv .venv
else
    echo "[1/4] Virtual environment exists."
fi

source .venv/bin/activate

# 2. Install Python dependencies
echo "[2/4] Installing Python packages..."
pip install -r requirements.txt --quiet

# 3. Check for yt-dlp
if ! command -v yt-dlp &> /dev/null; then
    echo "[!] yt-dlp not found. Installing via pip..."
    pip install yt-dlp
fi

# 4. Check for ffmpeg (needed by whisper and yt-dlp)
if ! command -v ffmpeg &> /dev/null; then
    echo "[!] ffmpeg not found. Install it:"
    echo "    brew install ffmpeg"
    echo "    (or) sudo apt install ffmpeg"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start the backend server:"
echo "  cd $(pwd)"
echo "  source .venv/bin/activate"
echo "  python -m project.backend.server"
echo ""
echo "To use the CLI agent:"
echo "  python -m agent.content_agent --urls URL1 URL2 --objective 'your goal'"
echo "  python -m agent.content_agent --channel 'https://youtube.com/@channel' --count 10 --objective 'your goal'"
echo ""
echo "To install the Chrome extension:"
echo "  1. Go to chrome://extensions/"
echo "  2. Enable Developer Mode"
echo "  3. Click 'Load unpacked'"
echo "  4. Select: $(pwd)/project/chrome-extension/"
echo ""
echo "Make sure ANTHROPIC_API_KEY is set in your environment."
