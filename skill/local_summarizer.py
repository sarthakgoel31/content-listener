"""
Local extractive summarizer — no API needed.
Extracts the most important sentences from a transcript for Kindle delivery.
Uses sentence scoring based on position, length, and keyword frequency.
"""

import re
from collections import Counter


def local_summarize(transcript: str, title: str = "", max_sentences: int = 20) -> str:
    """
    Extract key sentences from a transcript. Returns a readable summary string.
    No API calls — pure Python text extraction.
    """
    if not transcript or len(transcript.strip()) < 100:
        return transcript

    sentences = _split_sentences(transcript)
    if len(sentences) <= max_sentences:
        return transcript

    # Score each sentence
    word_freq = _get_word_frequencies(transcript)
    scored = []
    for i, sent in enumerate(sentences):
        score = _score_sentence(sent, i, len(sentences), word_freq)
        scored.append((score, i, sent))

    # Pick top sentences, preserve original order
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_sentences]
    top.sort(key=lambda x: x[1])  # restore order

    summary_sentences = [s[2] for s in top]

    # Extract top keywords for section headings
    top_keywords = [w for w, _ in word_freq.most_common(30)
                    if w not in {'the', 'and', 'that', 'this', 'with', 'for', 'are',
                                 'but', 'not', 'you', 'all', 'can', 'had', 'her',
                                 'was', 'one', 'our', 'out', 'has', 'have', 'from',
                                 'they', 'been', 'were', 'will', 'would', 'could',
                                 'should', 'about', 'which', 'their', 'there', 'what',
                                 'when', 'make', 'like', 'just', 'know', 'take', 'come',
                                 'into', 'your', 'some', 'them', 'than', 'then', 'also',
                                 'back', 'after', 'going', 'these', 'thing', 'things',
                                 'really', 'right', 'because', 'actually', 'pretty'}]

    # Build structured output with sections
    output_parts = []

    # Overview from first few sentences
    overview_count = min(3, len(summary_sentences))
    overview = ' '.join(summary_sentences[:overview_count])
    output_parts.append(f"## Overview\n{overview}")

    remaining = summary_sentences[overview_count:]

    if remaining:
        # Split remaining into sections of ~4 sentences
        section_size = max(3, len(remaining) // 3)
        sections = []
        for j in range(0, len(remaining), section_size):
            sections.append(remaining[j:j + section_size])

        section_labels = ["Key Details", "Core Discussion", "Additional Insights"]
        # Use top keywords for more descriptive headings if available
        for idx, section in enumerate(sections):
            label = section_labels[idx] if idx < len(section_labels) else f"Part {idx + 1}"
            bullets = '\n'.join(f"- {s}" for s in section)
            output_parts.append(f"### {label}\n{bullets}")

    # Takeaways from highest-scored sentences
    takeaway_count = min(5, len(scored))
    takeaway_sents = [s[2] for s in scored[:takeaway_count]]
    takeaways = '\n'.join(f"- {s}" for s in takeaway_sents)
    output_parts.append(f"## Takeaways\n{takeaways}")

    return '\n\n'.join(output_parts)


def format_kindle_summary(title: str, transcript: str, summary: str) -> str:
    """Build a clean Kindle-optimized HTML document from a local summary."""
    import html as html_mod

    safe_title = html_mod.escape(title)

    # Build summary HTML from markdown-structured text
    summary_html = _markdown_to_html(summary, html_mod)

    # Extract key topics
    words = re.findall(r'\b[a-z]{4,}\b', transcript.lower())
    freq = Counter(words)
    # Remove common words
    stopwords = {'that', 'this', 'with', 'have', 'from', 'they', 'been', 'were',
                 'will', 'would', 'could', 'should', 'about', 'which', 'their',
                 'there', 'what', 'when', 'make', 'like', 'just', 'know', 'take',
                 'come', 'into', 'your', 'some', 'them', 'than', 'then', 'also',
                 'back', 'after', 'going', 'these', 'thing', 'things', 'really',
                 'right', 'because', 'basically', 'actually', 'pretty', 'those',
                 'very', 'much', 'here', 'want', 'said', 'says', 'doing', 'being',
                 'does', 'done', 'gonna', 'gotta', 'kind'}
    topics = [w for w, c in freq.most_common(50) if w not in stopwords][:10]
    topics_html = ", ".join(html_mod.escape(t) for t in topics)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{safe_title} — Summary</title>
<style>
body {{ font-family: Georgia, "Times New Roman", serif; font-size: 1em; line-height: 1.7; margin: 2em; color: #1a1a1a; }}
h1 {{ font-family: Helvetica, Arial, sans-serif; font-size: 1.5em; margin-bottom: 0.3em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }}
h2 {{ font-family: Helvetica, Arial, sans-serif; font-size: 1.2em; margin-top: 1.5em; margin-bottom: 0.5em; color: #333; }}
h3 {{ font-family: Helvetica, Arial, sans-serif; font-size: 1.05em; margin-top: 1.2em; margin-bottom: 0.4em; color: #444; }}
p {{ margin-bottom: 0.8em; text-align: justify; }}
ul {{ margin: 0.5em 0 1em 1.5em; }}
li {{ margin-bottom: 0.4em; }}
strong {{ font-weight: bold; }}
.meta {{ font-size: 0.85em; color: #666; margin-bottom: 1.5em; }}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<p class="meta">Key topics: {topics_html}</p>

{summary_html}

<hr>
<p style="font-size:0.8em;color:#888;">Summarised by Content Listener Agent</p>
</body>
</html>"""


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Remove speaker labels for scoring purposes
    clean = re.sub(r'^[A-Z][a-zA-Z\s]{0,30}:\s*', '', text, flags=re.MULTILINE)
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', clean)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 15]


def _get_word_frequencies(text: str) -> Counter:
    """Get word frequencies, excluding stopwords."""
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    stopwords = {'the', 'and', 'that', 'this', 'with', 'for', 'are', 'but',
                 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one',
                 'our', 'out', 'has', 'have', 'from', 'they', 'been'}
    return Counter(w for w in words if w not in stopwords)


def _score_sentence(sentence: str, position: int, total: int,
                    word_freq: Counter) -> float:
    """Score a sentence for importance."""
    score = 0.0

    # Position bonus: first and last 15% of content score higher
    rel_pos = position / max(total, 1)
    if rel_pos < 0.15:
        score += 2.0
    elif rel_pos > 0.85:
        score += 1.5

    # Length: prefer medium-length sentences (20-40 words)
    words = sentence.split()
    word_count = len(words)
    if 20 <= word_count <= 40:
        score += 1.0
    elif word_count < 8:
        score -= 1.0

    # Keyword density: sum of word frequencies
    for word in words:
        score += word_freq.get(word.lower().strip('.,!?'), 0) * 0.01

    # Bonus for sentences with key phrases
    key_patterns = [
        r'\b(important|key|main|critical|essential|significant)\b',
        r'\b(first|second|third|finally|conclusion)\b',
        r'\b(recommend|suggest|advise|should|must)\b',
        r'\b(because|therefore|result|means|shows)\b',
    ]
    for pattern in key_patterns:
        if re.search(pattern, sentence, re.IGNORECASE):
            score += 1.0

    return score


def _markdown_to_html(md: str, html_mod) -> str:
    """Convert markdown-structured summary text to HTML for Kindle."""
    lines = md.split('\n')
    out = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Close open list if not a bullet
        if in_list and not stripped.startswith('- '):
            out.append('</ul>')
            in_list = False

        if not stripped:
            continue
        elif stripped.startswith('## '):
            out.append(f'<h2>{html_mod.escape(stripped[3:])}</h2>')
        elif stripped.startswith('### '):
            out.append(f'<h3>{html_mod.escape(stripped[4:])}</h3>')
        elif stripped.startswith('- '):
            if not in_list:
                out.append('<ul>')
                in_list = True
            text = stripped[2:]
            # Handle **bold** inline
            text = html_mod.escape(text)
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            out.append(f'<li>{text}</li>')
        else:
            text = html_mod.escape(stripped)
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            out.append(f'<p>{text}</p>')

    if in_list:
        out.append('</ul>')

    return '\n'.join(out)
