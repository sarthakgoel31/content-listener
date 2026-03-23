"""
Transcription skill — extracts text from YouTube videos, Instagram reels, Spotify podcasts.

Strategy:
1. YouTube: Try yt-dlp subtitles first (free, fast). Fall back to audio download + Whisper.
2. Instagram: Download via yt-dlp → Whisper.
3. Spotify: Download via spotdl → Whisper.
4. Generic URL: Download audio via yt-dlp → Whisper.
"""

import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import time

# Fix SSL cert issues on macOS Python
ssl._create_default_https_context = ssl._create_unverified_context
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from skill.transcript_formatter import format_transcript

WHISPER_MODEL_OVERRIDE = os.getenv("WHISPER_MODEL", "")  # set to force a specific model
WHISPER_DURATION_THRESHOLD = 600  # seconds — videos longer than this use "tiny"
WHISPER_MODEL_SHORT = "base"     # ≤ threshold
WHISPER_MODEL_LONG = "tiny"      # > threshold
# CPU speed factors: estimated seconds of processing per second of audio
WHISPER_SPEED_FACTOR = {"tiny": 1.0, "base": 3.0, "small": 8.0, "medium": 20.0, "large": 40.0}

# Resolve venv binaries so subprocess calls work even when server runs outside venv
VENV_BIN = Path(__file__).resolve().parent.parent / ".venv" / "bin"
WHISPER_CMD = str(VENV_BIN / "whisper") if (VENV_BIN / "whisper").exists() else "whisper"
YTDLP_CMD = str(VENV_BIN / "yt-dlp") if (VENV_BIN / "yt-dlp").exists() else "yt-dlp"


@dataclass
class TranscriptResult:
    url: str
    title: str
    transcript: str
    source: str  # "subtitles" | "whisper"
    duration_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "transcript": self.transcript,
            "source": self.source,
            "duration_seconds": self.duration_seconds,
        }


def pick_whisper_model(duration_seconds: float | None) -> str:
    """Choose Whisper model based on video duration. Short videos get better model."""
    if WHISPER_MODEL_OVERRIDE:
        return WHISPER_MODEL_OVERRIDE
    if duration_seconds and duration_seconds > WHISPER_DURATION_THRESHOLD:
        return WHISPER_MODEL_LONG
    return WHISPER_MODEL_SHORT


def estimate_transcription_time(duration_seconds: float | None, model: str) -> float | None:
    """Estimate transcription wall-clock time in seconds. Returns None if duration unknown."""
    if not duration_seconds:
        return None
    download_overhead = 15  # ~15s for audio download
    factor = WHISPER_SPEED_FACTOR.get(model, 3.0)
    return download_overhead + (duration_seconds * factor)


def format_eta(seconds: float | None) -> str:
    """Human-readable ETA string."""
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"~{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"~{minutes}m {secs}s"


def detect_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "instagram.com" in url:
        return "instagram"
    if "spotify.com" in url:
        return "spotify"
    return "generic"


def _get_video_info(url: str) -> dict:
    """Get video metadata via yt-dlp without downloading."""
    result = subprocess.run(
        [YTDLP_CMD, "--dump-json", "--no-download", url],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp info failed: {result.stderr[:500]}")
    return json.loads(result.stdout)


def _try_subtitles(url: str) -> Optional[TranscriptResult]:
    """Try extracting existing subtitles/captions (YouTube auto-captions, etc.)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_path = os.path.join(tmpdir, "subs")
        result = subprocess.run(
            [
                YTDLP_CMD,
                "--write-auto-sub", "--write-sub",
                "--sub-lang", "en,hi",
                "--sub-format", "vtt",
                "--skip-download",
                "-o", sub_path,
                url,
            ],
            capture_output=True, text=True, timeout=60,
        )
        # Find any .vtt file
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return None

        raw = vtt_files[0].read_text(encoding="utf-8", errors="replace")
        transcript = _clean_vtt(raw)
        if len(transcript.strip()) < 20:
            return None

        info = _get_video_info(url)
        return TranscriptResult(
            url=url,
            title=info.get("title", "Unknown"),
            transcript=transcript,
            source="subtitles",
            duration_seconds=info.get("duration"),
        )


def _clean_vtt(raw: str) -> str:
    """Strip VTT timestamps and metadata, return plain text."""
    lines = raw.split("\n")
    text_lines = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d{2}:\d{2}", line) or re.match(r"^<\d{2}:\d{2}", line):
            continue
        if "-->" in line:
            continue
        # Remove inline VTT tags
        clean = re.sub(r"<[^>]+>", "", line)
        if clean and clean not in seen:
            seen.add(clean)
            text_lines.append(clean)
    return " ".join(text_lines)


def _run_whisper_with_progress(audio_path: str, output_dir: str, model: str,
                               eta: float | None = None, on_progress=None) -> str:
    """Run Whisper on an audio file with live progress bar. Returns transcript text."""
    whisper_proc = subprocess.Popen(
        [
            WHISPER_CMD, audio_path,
            "--model", model,
            "--output_format", "txt",
            "--output_dir", output_dir,
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    # Parse Whisper's stderr for tqdm progress (e.g. " 42%|████ |")
    whisper_pct = [0]  # mutable for thread access
    stderr_lines = []

    def _read_whisper_stderr():
        for line in whisper_proc.stderr:
            stderr_lines.append(line)
            match = re.search(r"(\d+)%\|", line)
            if match:
                whisper_pct[0] = int(match.group(1))

    stderr_thread = threading.Thread(target=_read_whisper_stderr, daemon=True)
    stderr_thread.start()

    # Time-based progress bar (falls back if Whisper doesn't emit %)
    start_time = time.time()
    is_tty = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    while whisper_proc.poll() is None:
        elapsed = time.time() - start_time
        if whisper_pct[0] > 0:
            pct = whisper_pct[0]
        elif eta and eta > 0:
            pct = min(95, int((elapsed / eta) * 100))
        else:
            pct = min(95, int(elapsed / 60))  # rough fallback

        remaining = max(0, (eta or 300) - elapsed) if eta else None
        remaining_str = format_eta(remaining) if remaining else ""

        filled = pct // 5
        bar = "█" * filled + "░" * (20 - filled)
        progress_line = f"\r  [{bar}] {pct}% — {remaining_str} remaining"

        if is_tty:
            sys.stderr.write(progress_line)
            sys.stderr.flush()

        if on_progress:
            on_progress("progress", pct=pct, remaining=remaining,
                        message=f"{pct}% — {remaining_str} remaining")

        time.sleep(2)

    stderr_thread.join(timeout=5)

    if is_tty:
        sys.stderr.write("\r  [████████████████████] 100% — done!              \n")
        sys.stderr.flush()

    if whisper_proc.returncode != 0:
        raise RuntimeError(f"Whisper failed: {''.join(stderr_lines)[:500]}")

    txt_files = list(Path(output_dir).glob("*.txt"))
    if not txt_files:
        raise RuntimeError("Whisper produced no output")

    return txt_files[0].read_text(encoding="utf-8", errors="replace").strip()


def _transcribe_with_whisper(url: str, on_progress=None) -> TranscriptResult:
    """Download audio and transcribe with Whisper."""
    info = _get_video_info(url)
    title = info.get("title", "Unknown")
    duration = info.get("duration")

    model = pick_whisper_model(duration)
    eta = estimate_transcription_time(duration, model)

    if on_progress:
        dur_str = f"{int(duration//60)}m {int(duration%60)}s" if duration else "unknown"
        on_progress("whisper_start", title=title, model=model, eta=eta, duration=duration,
                     message=f"Whisper ({model}) — video: {dur_str}, ETA: {format_eta(eta)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")

        if on_progress:
            on_progress("downloading", title=title, message="Downloading audio...")

        dl_result = subprocess.run(
            [
                YTDLP_CMD,
                "-x", "--audio-format", "mp3",
                "--audio-quality", "5",
                "-o", audio_path,
                url,
            ],
            capture_output=True, text=True, timeout=300,
        )
        if dl_result.returncode != 0:
            raise RuntimeError(f"Audio download failed: {dl_result.stderr[:500]}")

        # Find the actual output file (yt-dlp may append extension)
        audio_files = list(Path(tmpdir).glob("audio*"))
        if not audio_files:
            raise RuntimeError("No audio file produced by yt-dlp")
        actual_audio = str(audio_files[0])

        if on_progress:
            on_progress("transcribing", title=title, model=model, eta=eta,
                         message=f"Transcribing with Whisper ({model})...")

        transcript = _run_whisper_with_progress(actual_audio, tmpdir, model, eta, on_progress)

    return TranscriptResult(
        url=url,
        title=title,
        transcript=transcript,
        source="whisper",
        duration_seconds=duration,
    )


def _transcribe_spotify(url: str, on_progress=None) -> TranscriptResult:
    """Download Spotify podcast episode via spotdl, then Whisper."""
    with tempfile.TemporaryDirectory() as tmpdir:
        if on_progress:
            on_progress("downloading", message="Downloading from Spotify...")

        dl_result = subprocess.run(
            ["spotdl", url, "--output", tmpdir],
            capture_output=True, text=True, timeout=300,
        )
        if dl_result.returncode != 0:
            raise RuntimeError(f"spotdl failed: {dl_result.stderr[:500]}")

        audio_files = list(Path(tmpdir).glob("*.*"))
        if not audio_files:
            raise RuntimeError("spotdl produced no files")
        actual_audio = str(audio_files[0])
        title = audio_files[0].stem

        model = pick_whisper_model(None)  # no duration info for Spotify
        eta = None  # unknown duration

        if on_progress:
            on_progress("transcribing", title=title, model=model, eta=eta,
                         message=f"Transcribing with Whisper ({model})...")

        transcript = _run_whisper_with_progress(actual_audio, tmpdir, model, eta, on_progress)

    return TranscriptResult(
        url=url,
        title=title,
        transcript=transcript,
        source="whisper",
    )


def transcribe(url: str, on_progress=None) -> TranscriptResult:
    """Main entry point — transcribe any supported URL.

    on_progress(stage, **kwargs) is called with progress updates:
        stage: "info" | "subtitles" | "whisper_start" | "downloading" | "transcribing" | "done"
        kwargs: title, model, eta, duration, message
    """
    platform = detect_platform(url)

    # Get duration early for ETA estimation
    if on_progress:
        try:
            info = _get_video_info(url)
            duration = info.get("duration")
            title = info.get("title", "Unknown")
            dur_str = f"{int(duration//60)}m {int(duration%60)}s" if duration else "unknown"
            on_progress("info", title=title, duration=duration,
                        message=f"Video: {title} ({dur_str})")
        except Exception:
            pass

    if platform == "spotify":
        result = _transcribe_spotify(url, on_progress=on_progress)
    elif platform in ("youtube", "generic"):
        result = None
        try:
            if on_progress:
                on_progress("subtitles", message="Trying subtitles (fast path)...")
            result = _try_subtitles(url)
            if result and on_progress:
                on_progress("done", title=result.title, source="subtitles",
                            message="Got subtitles — no Whisper needed!")
        except Exception:
            pass
        if not result:
            result = _transcribe_with_whisper(url, on_progress=on_progress)
    else:
        result = _transcribe_with_whisper(url, on_progress=on_progress)

    # Format transcript for readability
    result.transcript = format_transcript(result.transcript)
    return result


def get_channel_videos(channel_url: str, count: int = 10) -> list[str]:
    """Get latest N video URLs from a YouTube channel."""
    result = subprocess.run(
        [
            YTDLP_CMD,
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(count),
            channel_url,
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Channel fetch failed: {result.stderr[:500]}")

    urls = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        data = json.loads(line)
        video_id = data.get("id", "")
        video_url = data.get("url") or data.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
        urls.append(video_url)
    return urls
