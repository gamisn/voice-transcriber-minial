"""Style-aware formatter that adapts output to match the user's writing.

Runs after the basic ``normalize_transcript`` but before the result hits the
clipboard.  If no style profile exists, passes through unchanged.

Usage:
    from voice_transcriber.style import load_style_profile
    from voice_transcriber.style_formatter import apply_style

    profile = load_style_profile()
    styled = apply_style("hello i want to follow up", profile)
"""

from __future__ import annotations

import re

from voice_transcriber.style import StyleProfile


def apply_style(text: str, profile: StyleProfile | None) -> str:
    """Adapt ``text`` to match the user's writing style.

    Returns the text unchanged if ``profile`` is None.
    """
    if profile is None:
        return text

    result = text

    # 1. Capitalize I
    if profile.capitalizes_i:
        result = _capitalize_i(result)
    else:
        result = _decapitalize_i(result)

    # 2. Expand or contract based on preference
    result = _apply_contractions(result, profile.uses_contractions)

    # 3. Handle lowercase fragments
    if profile.lowercase_fragments:
        result = _lowercase_fragments(result)
    else:
        # Ensure every sentence starts capitalized
        result = _capitalize_sentences(result)

    # 4. Trailing period
    if profile.trailing_period:
        result = _ensure_trailing_period(result)
    else:
        result = _strip_trailing_period(result)

    return result
    # end apply_style


# ── Internal helpers ────────────────────────────────────────────────────


def _capitalize_i(text: str) -> str:
    """Capitalize standalone 'i' to 'I'."""
    return re.sub(r"\bi\b", "I", text)
    # end _capitalize_i


def _decapitalize_i(text: str) -> str:
    """Lowercase standalone 'I' to 'i'."""
    return re.sub(r"\bI\b", "i", text)
    # end _decapitalize_i


def _apply_contractions(text: str, use_contractions: bool) -> str:
    """Expand or contract based on the user's preference."""
    if use_contractions:
        # Expand common full forms → contractions
        replacements = {
            r"\bdo not\b": "don't",
            r"\bdid not\b": "didn't",
            r"\bcannot\b": "can't",
            r"\bwill not\b": "won't",
            r"\bis not\b": "isn't",
            r"\bare not\b": "aren't",
            r"\bhave not\b": "haven't",
            r"\bhas not\b": "hasn't",
            r"\bhad not\b": "hadn't",
            r"\bwould not\b": "wouldn't",
            r"\bcould not\b": "couldn't",
            r"\bshould not\b": "shouldn't",
            r"\bI am\b": "I'm",
            r"\bYou are\b": "You're",
            r"\bThey are\b": "They're",
            r"\bWe are\b": "We're",
            r"\bIt is\b": "It's",
            r"\bThat is\b": "That's",
        }
    else:
        # Expand contractions → full forms
        replacements = {
            r"\bdon't\b": "do not",
            r"\bdidn't\b": "did not",
            r"\bcan't\b": "cannot",
            r"\bwon't\b": "will not",
            r"\bisn't\b": "is not",
            r"\baren't\b": "are not",
            r"\bhaven't\b": "have not",
            r"\bhasn't\b": "has not",
            r"\bhadn't\b": "had not",
            r"\bwouldn't\b": "would not",
            r"\bcouldn't\b": "could not",
            r"\bshouldn't\b": "should not",
            r"\bI'm\b": "I am",
            r"\bYou're\b": "You are",
            r"\bThey're\b": "They are",
            r"\bWe're\b": "We are",
            r"\bIt's\b": "It is",
            r"\bThat's\b": "That is",
        }

    result = text
    for pattern, replacement in replacements.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result
    # end _apply_contractions


def _capitalize_sentences(text: str) -> str:
    """Capitalize the first letter of each sentence."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    capitalized = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            sentence = sentence[0].upper() + sentence[1:]
        capitalized.append(sentence)
    return " ".join(capitalized)
    # end _capitalize_sentences


def _lowercase_fragments(text: str) -> str:
    """Leave short sentences (≤3 words) lowercase, capitalize longer ones."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    processed = []
    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        if len(stripped.split()) <= 3:
            processed.append(stripped.lower())
        else:
            processed.append(stripped[0].upper() + stripped[1:])
    return " ".join(processed)
    # end _lowercase_fragments


def _ensure_trailing_period(text: str) -> str:
    """Add a trailing period if missing."""
    if not text or text[-1] in ".!?":
        return text
    return text + "."
    # end _ensure_trailing_period


def _strip_trailing_period(text: str) -> str:
    """Remove trailing period if present."""
    if text and text[-1] == ".":
        return text[:-1]
    return text
    # end _strip_trailing_period
