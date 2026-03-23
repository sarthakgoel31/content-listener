"""
Actionable extraction skill — skips if no ANTHROPIC_API_KEY is set.
Transcripts are stored in DB. Actionable extraction is done by Claude Code in-session
when the user asks (free, no API cost).
"""

import os
from dataclasses import dataclass


@dataclass
class ActionableResult:
    objective: str
    actionables: list[str]
    answer: str
    confidence: str
    raw_response: str

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "actionables": self.actionables,
            "answer": self.answer,
            "confidence": self.confidence,
        }


def extract_actionables(
    transcripts: list[dict],
    objective: str,
    question: str = "",
) -> ActionableResult:
    """
    Extract actionables from transcripts. If ANTHROPIC_API_KEY is set, uses Claude API.
    Otherwise raises to signal the caller to skip.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY — transcript saved. Ask Claude Code to extract actionables for free."
        )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("SUMMARIZER_MODEL", "claude-sonnet-4-20250514")

    max_per = 60000 // max(len(transcripts), 1)
    transcript_block = ""
    for i, t in enumerate(transcripts, 1):
        transcript_block += f"\n\n--- Source {i}: {t.get('title', 'Unknown')} ---\n"
        transcript_block += t["transcript"][:max_per]

    question_block = ""
    if question:
        question_block = f"\nSpecific question to answer: {question}"

    prompt = f"""You are an expert analyst. The user has a specific objective and wants actionable insights from the content below.

User's objective: {objective}
{question_block}

Content from {len(transcripts)} source(s):
{transcript_block}

Provide your response in this exact format:

ANSWER:
<Direct answer to the user's question/objective. Be specific and practical.>

ACTIONABLES:
- <Specific action item 1>
- <Specific action item 2>
...

CONFIDENCE: <high|medium|low>
<Brief explanation of confidence level>"""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    answer = ""
    actionables = []
    confidence = "medium"

    if "ANSWER:" in raw:
        parts = raw.split("ACTIONABLES:")
        answer = parts[0].replace("ANSWER:", "").strip()
        if len(parts) > 1:
            remainder = parts[1]
            conf_parts = remainder.split("CONFIDENCE:")
            actions_text = conf_parts[0].strip()
            actionables = [
                line.strip().lstrip("- ").strip()
                for line in actions_text.split("\n")
                if line.strip().startswith("-")
            ]
            if len(conf_parts) > 1:
                conf_line = conf_parts[1].strip().split("\n")[0].strip().lower()
                if "high" in conf_line:
                    confidence = "high"
                elif "low" in conf_line:
                    confidence = "low"
    else:
        answer = raw

    return ActionableResult(
        objective=objective,
        actionables=actionables,
        answer=answer,
        confidence=confidence,
        raw_response=raw,
    )
