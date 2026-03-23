"""
Summarization skill — skips if no ANTHROPIC_API_KEY is set.
Transcripts are always stored in DB. Summarization is done by Claude Code in-session
when the user asks (free, no API cost).
"""

import os
from dataclasses import dataclass


@dataclass
class SummaryResult:
    title: str
    summary: str
    key_points: list[str]
    raw_response: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "key_points": self.key_points,
        }


def summarize(transcript: str, title: str = "", context: str = "") -> SummaryResult:
    """
    Summarize a transcript. If ANTHROPIC_API_KEY is set, uses Claude API.
    Otherwise raises to signal the caller to skip (transcript still saved).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY — transcript saved. Ask Claude Code to summarize it for free."
        )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("SUMMARIZER_MODEL", "claude-sonnet-4-20250514")

    context_block = ""
    if context:
        context_block = f"\n\nUser's context/goal: {context}"

    prompt = f"""You are a content summarizer. Given the transcript below, produce a well-structured summary using markdown formatting.

Title: {title}
{context_block}

Transcript:
{transcript[:80000]}

Respond in this exact format:

SUMMARY:
## Overview
A 2-3 sentence high-level overview of the content.

## Key Themes
Organize the main ideas into 2-4 themed subsections. For each:

### <Theme Name>
A brief paragraph explaining this theme, with **bold** for key terms or important phrases.
- Bullet points for specific details, facts, or examples
- Use sub-bullets where needed for clarity

## Takeaways
- 3-5 bullet points summarizing the most important conclusions or action items, with **bold highlights** on the key phrase in each

KEY POINTS:
- <point 1>
- <point 2>
..."""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    summary = ""
    key_points = []
    if "SUMMARY:" in raw and "KEY POINTS:" in raw:
        parts = raw.split("KEY POINTS:")
        summary = parts[0].replace("SUMMARY:", "").strip()
        points_text = parts[1].strip()
        key_points = [
            line.strip().lstrip("- ").strip()
            for line in points_text.split("\n")
            if line.strip().startswith("-")
        ]
    else:
        summary = raw

    return SummaryResult(
        title=title,
        summary=summary,
        key_points=key_points,
        raw_response=raw,
    )
