"""
Content Listener Agent — orchestrates transcription, summarization, and actionable extraction.

Usage modes:
1. CLI: python -m agent.content_agent --urls URL1 URL2 --objective "..." --question "..."
2. CLI channel mode: python -m agent.content_agent --channel CHANNEL_URL --count 10 --objective "..."
3. API: called by the FastAPI server for Chrome extension requests
"""

import argparse
import json
import sys
import os

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time as _time
from skill.transcriber import transcribe, get_channel_videos, detect_platform, format_eta
from skill.summarizer import summarize
from skill.actionable_extractor import extract_actionables
from skill.kindle_sender import send_to_kindle as kindle_send, send_html_to_kindle
from skill.local_summarizer import local_summarize, format_kindle_summary  # free, no API
from project.backend.db import (
    save_transcript, save_summary, save_actionable,
    create_job, update_job, update_job_progress,
)


def process_urls(
    urls: list[str],
    objective: str = "",
    question: str = "",
    do_summarize: bool = True,
    do_actionables: bool = True,
    save_to_db: bool = True,
    do_kindle: bool = False,
    job_id: int | None = None,
) -> dict:
    """
    Full pipeline: transcribe → summarize → extract actionables.

    Returns dict with all results.
    """
    results = {
        "transcripts": [],
        "summaries": [],
        "actionable": None,
        "kindle_sent": False,
        "errors": [],
    }

    transcript_ids = []

    def _cli_progress(stage, **kwargs):
        msg = kwargs.get("message", "")
        if stage == "info":
            print(f"  [info] {msg}", flush=True)
        elif stage == "subtitles":
            print(f"  [try] {msg}", flush=True)
        elif stage == "whisper_start":
            print(f"  [whisper] {msg}", flush=True)
        elif stage == "downloading":
            print(f"  [download] {msg}", flush=True)
        elif stage == "transcribing":
            eta = kwargs.get("eta")
            print(f"  [transcribing] {msg} — ETA: {format_eta(eta)}", flush=True)
        elif stage == "progress":
            pass  # progress bar is printed directly to stderr by transcriber
        elif stage == "done":
            print(f"  [done] {msg}", flush=True)

    for i, url in enumerate(urls):
        print(f"\n[{i+1}/{len(urls)}] {url}")
        t_start = _time.time()

        # Build combined progress callback (CLI + job DB)
        job_cb = _make_job_progress_callback(job_id, i, len(urls)) if job_id else None
        def _combined_progress(stage, _job_cb=job_cb, **kwargs):
            _cli_progress(stage, **kwargs)
            if _job_cb:
                _job_cb(stage, **kwargs)

        try:
            t_result = transcribe(url, on_progress=_combined_progress)
            elapsed = _time.time() - t_start
            print(f"  [complete] Transcribed in {format_eta(elapsed)} via {t_result.source}", flush=True)
            t_dict = t_result.to_dict()
            results["transcripts"].append(t_dict)

            if save_to_db:
                t_id = save_transcript(
                    url=t_result.url,
                    platform=detect_platform(url),
                    title=t_result.title,
                    transcript=t_result.transcript,
                    source=t_result.source,
                    duration_seconds=t_result.duration_seconds,
                )
                t_dict["db_id"] = t_id
                transcript_ids.append(t_id)

            if do_summarize:
                print(f"  [summarizing] {t_result.title}", flush=True)
                summary_text = ""
                key_points = []
                try:
                    s_result = summarize(
                        transcript=t_result.transcript,
                        title=t_result.title,
                        context=objective,
                    )
                    summary_text = s_result.summary
                    key_points = s_result.key_points
                except RuntimeError:
                    # No API key — fall back to free local summarizer
                    summary_text = local_summarize(t_result.transcript, title=t_result.title)
                    print(f"  [summarizing] Using free local summarizer", flush=True)

                s_dict = {"title": t_result.title, "summary": summary_text, "key_points": key_points}
                results["summaries"].append(s_dict)

                if save_to_db and "db_id" in t_dict:
                    save_summary(
                        transcript_id=t_dict["db_id"],
                        summary=summary_text,
                        key_points=key_points,
                        context=objective,
                    )

        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}"
            print(f"[error] {error_msg}")
            results["errors"].append(error_msg)

    # Extract actionables across all transcripts
    if do_actionables and objective and results["transcripts"]:
        print(f"\n[extracting actionables] objective: {objective}", flush=True)
        try:
            a_result = extract_actionables(
                transcripts=[
                    {"title": t["title"], "transcript": t["transcript"]}
                    for t in results["transcripts"]
                ],
                objective=objective,
                question=question,
            )
            results["actionable"] = a_result.to_dict()

            if save_to_db:
                save_actionable(
                    objective=objective,
                    question=question,
                    answer=a_result.answer,
                    actionables=a_result.actionables,
                    confidence=a_result.confidence,
                    transcript_ids=transcript_ids,
                )

        except RuntimeError:
            # No API key — skip actionable extraction, transcripts are saved
            print("  [info] No API key — transcripts saved to DB. Ask Claude Code to analyze them for free.", flush=True)
        except Exception as e:
            error_msg = f"Error extracting actionables: {str(e)}"
            print(f"  [error] {error_msg}", flush=True)
            results["errors"].append(error_msg)

    # Optional: send to Kindle
    if do_kindle and (results["transcripts"] or results["summaries"]):
        try:
            title = results["transcripts"][0]["title"] if results["transcripts"] else "Content Listener"
            if len(results["transcripts"]) > 1:
                title = f"{title} (+{len(results['transcripts']) - 1} more)"

            a = results.get("actionable") or {}
            s = results["summaries"][0] if results["summaries"] else {}

            sent = kindle_send(
                title=title,
                transcript=results["transcripts"][0]["transcript"] if results["transcripts"] else "",
                summary=s.get("summary", ""),
                key_points=s.get("key_points"),
                actionables=a.get("actionables"),
                answer=a.get("answer", ""),
                confidence=a.get("confidence", ""),
            )
            results["kindle_sent"] = sent
        except Exception as e:
            results["errors"].append(f"Kindle send failed: {str(e)}")

    return results


def process_channel(
    channel_url: str,
    count: int = 10,
    objective: str = "",
    question: str = "",
    do_kindle: bool = False,
    job_id: int | None = None,
) -> dict:
    """Fetch latest videos from a channel, then process them."""
    print(f"[fetching] latest {count} videos from {channel_url}")
    urls = get_channel_videos(channel_url, count=count)
    print(f"[found] {len(urls)} videos")
    return process_urls(urls, objective=objective, question=question, do_kindle=do_kindle, job_id=job_id)


def _make_job_progress_callback(job_id: int, url_index: int, total_urls: int):
    """Create a progress callback that writes to the jobs DB for Chrome extension polling."""
    def _cb(stage, **kwargs):
        progress = {
            "stage": stage,
            "current": url_index + 1,
            "total": total_urls,
            "message": kwargs.get("message", ""),
            "eta_seconds": kwargs.get("eta") or kwargs.get("remaining"),
            "pct": kwargs.get("pct"),
            "model": kwargs.get("model"),
            "duration": kwargs.get("duration"),
        }
        try:
            update_job_progress(job_id, progress)
        except Exception:
            pass
    return _cb


def process_job_async(job_id: int, input_data: dict):
    """Process a job (called from the server in a background thread)."""
    try:
        update_job(job_id, "processing")

        urls = input_data.get("urls", [])
        channel = input_data.get("channel")
        count = input_data.get("count", 10)
        objective = input_data.get("objective", "")
        question = input_data.get("question", "")
        do_kindle = input_data.get("send_to_kindle", False)
        kindle_summarised = input_data.get("kindle_summarised", False)

        if channel:
            result = process_channel(channel, count, objective, question, do_kindle=do_kindle, job_id=job_id)
        else:
            result = process_urls(urls, objective=objective, question=question, do_kindle=do_kindle, job_id=job_id)

        # Send summarised version to Kindle if requested
        if kindle_summarised and result.get("transcripts"):
            try:
                t = result["transcripts"][0]
                title = t["title"]
                summary_text = local_summarize(t["transcript"], title=title)
                html = format_kindle_summary(title, t["transcript"], summary_text)
                sent = send_html_to_kindle(f"{title} — Summary", html)
                result["kindle_summary_sent"] = sent
            except Exception as e:
                result["errors"].append(f"Kindle summary send failed: {str(e)}")

        update_job(job_id, "completed", result_data=result)
    except Exception as e:
        update_job(job_id, "failed", error=str(e))


def main():
    parser = argparse.ArgumentParser(description="Content Listener Agent")
    parser.add_argument("--urls", nargs="+", help="URLs to process")
    parser.add_argument("--channel", help="YouTube channel URL")
    parser.add_argument("--count", type=int, default=10, help="Number of videos from channel")
    parser.add_argument("--objective", default="", help="Your end objective/goal")
    parser.add_argument("--question", default="", help="Specific question to answer")
    parser.add_argument("--no-summary", action="store_true", help="Skip summarization")
    parser.add_argument("--no-actionables", action="store_true", help="Skip actionable extraction")
    parser.add_argument("--no-save", action="store_true", help="Don't save to DB")
    parser.add_argument("--kindle", action="store_true", help="Send results to Kindle (optional)")
    parser.add_argument("--output", help="Save JSON result to file")
    args = parser.parse_args()

    if not args.urls and not args.channel:
        parser.error("Provide --urls or --channel")

    if args.channel:
        result = process_channel(
            args.channel, args.count, args.objective, args.question,
            do_kindle=args.kindle,
        )
    else:
        result = process_urls(
            args.urls,
            objective=args.objective,
            question=args.question,
            do_summarize=not args.no_summary,
            do_actionables=not args.no_actionables,
            save_to_db=not args.no_save,
            do_kindle=args.kindle,
        )

    output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"\n[saved] Results written to {args.output}")
    else:
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        if result.get("actionable"):
            a = result["actionable"]
            print(f"\nObjective: {a['objective']}")
            print(f"Confidence: {a['confidence']}")
            print(f"\nAnswer:\n{a['answer']}")
            print("\nActionables:")
            for item in a["actionables"]:
                print(f"  - {item}")

        for s in result.get("summaries", []):
            print(f"\n--- {s['title']} ---")
            print(s["summary"][:500])

        if result.get("errors"):
            print("\nErrors:")
            for e in result["errors"]:
                print(f"  ! {e}")


if __name__ == "__main__":
    main()
