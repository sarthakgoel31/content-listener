"""
Transcript formatter — makes raw transcripts readable.

Handles:
- Speaker detection and labeling
- Paragraph breaks at natural pauses
- Punctuation cleanup
- Proper spacing and indentation
"""

import re


def format_transcript(raw: str) -> str:
    """
    Take a raw transcript string and return a clean, readable version.
    Detects speakers, adds paragraph breaks, fixes punctuation.
    """
    if not raw or not raw.strip():
        return raw

    # Step 1: Normalize whitespace
    text = re.sub(r'\r\n', '\n', raw)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()

    # Step 2: Detect if transcript already has speaker labels
    has_speakers = _detect_speakers(text)

    if has_speakers:
        text = _format_with_speakers(text)
    else:
        text = _format_monologue(text)

    return text


def _detect_speakers(text: str) -> bool:
    """Check if transcript has speaker labels like 'Speaker 1:', 'John:', '[Speaker]', etc."""
    patterns = [
        r'^[A-Z][a-zA-Z\s]{0,30}:',           # "John:", "Speaker 1:"
        r'^\[[A-Z][a-zA-Z\s]{0,30}\]',          # "[Speaker]"
        r'^SPEAKER\s*\d+\s*:',                   # "SPEAKER 1:"
        r'^Speaker\s*\d+\s*:',                   # "Speaker 1:"
        r'^S\d+\s*:',                             # "S1:"
    ]
    lines = text.split('\n')
    speaker_lines = 0
    for line in lines[:50]:  # check first 50 lines
        line = line.strip()
        for pattern in patterns:
            if re.match(pattern, line):
                speaker_lines += 1
                break
    return speaker_lines >= 2


def _format_with_speakers(text: str) -> str:
    """Format a transcript that already has speaker labels."""
    lines = text.split('\n')
    formatted = []
    current_speaker = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect speaker label
        speaker_match = re.match(
            r'^(\[?[A-Z][a-zA-Z\s\d]{0,30}\]?\s*:|SPEAKER\s*\d+\s*:|Speaker\s*\d+\s*:|S\d+\s*:)\s*(.*)',
            line
        )

        if speaker_match:
            speaker = speaker_match.group(1).strip().rstrip(':').strip('[]').strip()
            speech = speaker_match.group(2).strip()
            speech = _fix_punctuation(speech)

            if speaker != current_speaker:
                if formatted:
                    formatted.append('')  # blank line between speakers
                current_speaker = speaker
                formatted.append(f'{speaker}: {speech}')
            else:
                # Same speaker continues
                formatted.append(f'{speaker}: {speech}')
        else:
            # No speaker label — continuation of previous speaker
            line = _fix_punctuation(line)
            if current_speaker and formatted:
                formatted[-1] += ' ' + line
            else:
                formatted.append(line)

    return '\n'.join(formatted)


def _format_monologue(text: str) -> str:
    """Format a single-speaker transcript into readable paragraphs."""
    # Try to detect speaker changes from context clues
    text = _try_detect_speaker_changes(text)

    # Split into sentences
    sentences = _split_sentences(text)

    if not sentences:
        return text

    # Group sentences into paragraphs (roughly 3-5 sentences each)
    paragraphs = []
    current_para = []
    sentence_count = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence = _fix_punctuation(sentence)
        current_para.append(sentence)
        sentence_count += 1

        # Break paragraph at natural points
        should_break = False
        if sentence_count >= 4:
            should_break = True
        elif sentence_count >= 2 and _is_topic_shift(sentence):
            should_break = True

        if should_break:
            paragraphs.append(' '.join(current_para))
            current_para = []
            sentence_count = 0

    if current_para:
        paragraphs.append(' '.join(current_para))

    return '\n\n'.join(paragraphs)


def _try_detect_speaker_changes(text: str) -> str:
    """
    Heuristic: detect speaker changes in unstructured transcripts.
    Looks for patterns like quotes, "he said", "she said", turn-taking cues.
    """
    # If we find patterns like "Person said" or dialogue markers, label them
    # For now, look for common YouTube patterns where the host addresses someone
    patterns_suggest_multi = [
        r'\b(interviewer|host|guest|caller)\b',
        r'"[^"]{10,}"',  # quoted speech
    ]
    is_multi = any(re.search(p, text, re.IGNORECASE) for p in patterns_suggest_multi)

    if not is_multi:
        return text

    # Basic dialogue detection: split on quoted speech
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return ' '.join(parts)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling abbreviations."""
    # Handle common abbreviations that shouldn't be split points
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|i\.e|e\.g)\.\s', r'\1<DOT> ', text)

    # Split on sentence-ending punctuation followed by space and capital letter
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text)

    # Restore abbreviation dots
    sentences = [s.replace('<DOT>', '.') for s in sentences]

    return [s.strip() for s in sentences if s.strip()]


def _fix_punctuation(text: str) -> str:
    """Fix common punctuation issues in transcripts."""
    if not text:
        return text

    # Capitalize first letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Ensure ends with punctuation
    if text and text[-1] not in '.!?':
        text += '.'

    # Fix double spaces
    text = re.sub(r'  +', ' ', text)

    # Fix spacing around punctuation
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    text = re.sub(r'([.,!?;:])([A-Za-z])', r'\1 \2', text)

    # Fix "i" → "I"
    text = re.sub(r'\bi\b', 'I', text)

    # Fix quotes spacing
    text = re.sub(r'"\s+', '"', text)
    text = re.sub(r'\s+"', ' "', text)

    return text.strip()


def _is_topic_shift(sentence: str) -> bool:
    """Heuristic: detect if a sentence signals a topic change."""
    shift_markers = [
        r'^(so|now|okay|alright|anyway|moving on|next|also|but|however|let\'s)',
        r'^(the (first|second|third|next|last|final) thing)',
        r'^(another|one more|in addition)',
        r'^(let me|I want to|I\'m going to|we\'re going to)',
    ]
    for pattern in shift_markers:
        if re.match(pattern, sentence, re.IGNORECASE):
            return True
    return False
