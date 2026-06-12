"""Style profile builder and formatter for personalized output.

Phase 4: the transcriber learns how *you* write — not how a textbook
says people should write — and adapts every transcript to match.

The style profile is a lightweight JSON file at
``~/.config/voice-transcriber/style.json``.  It is generated once from
a handful of writing samples, then read on every transcription.

Metrics tracked (all 0–1 or numeric):
- formality: 0 = casual/slang, 1 = formal/business
- capitalizes_i: True/False — whether "i" is capitalized consistently
- uses_contractions: True/False — "I'm" vs "I am", "don't" vs "do not"
- avg_sentence_length: average words per sentence
- trailing_period: True/False — whether sentences always end with punctuation
- greeting_style: "none" | "casual" | "formal" — detected from openers
- lowercase_fragments: True/False — whether incomplete sentences are left lowercase
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any


_CONFIG_DIR: pathlib.Path = pathlib.Path.home() / ".config" / "voice-transcriber"
_STYLE_PATH: pathlib.Path = _CONFIG_DIR / "style.json"


@dataclass(slots=True)
class StyleProfile:
    """A snapshot of the user's writing style."""

    # How formal the writing is (0 = casual chat, 1 = business email)
    formality: float = 0.5

    # Whether standalone "i" should be capitalized
    capitalizes_i: bool = True

    # Whether contractions are preferred ("I'm" vs "I am")
    uses_contractions: bool = True

    # Average words per sentence in the corpus
    avg_sentence_length: float = 12.0

    # Whether sentences always end with . ! ?
    trailing_period: bool = True

    # Greeting style detected from openers
    greeting_style: str = "none"

    # Whether short fragments ("ok", "yeah") are left lowercase
    lowercase_fragments: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "formality": self.formality,
            "capitalizes_i": self.capitalizes_i,
            "uses_contractions": self.uses_contractions,
            "avg_sentence_length": self.avg_sentence_length,
            "trailing_period": self.trailing_period,
            "greeting_style": self.greeting_style,
            "lowercase_fragments": self.lowercase_fragments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleProfile":
        return cls(
            formality=float(data.get("formality", 0.5)),
            capitalizes_i=bool(data.get("capitalizes_i", True)),
            uses_contractions=bool(data.get("uses_contractions", True)),
            avg_sentence_length=float(data.get("avg_sentence_length", 12.0)),
            trailing_period=bool(data.get("trailing_period", True)),
            greeting_style=str(data.get("greeting_style", "none")),
            lowercase_fragments=bool(data.get("lowercase_fragments", False)),
        )
    # end StyleProfile


# ── Public API ──────────────────────────────────────────────────────────


def load_style_profile() -> StyleProfile | None:
    """Load the user's style profile from disk, or None if not yet created."""
    if not _STYLE_PATH.exists():
        return None
    try:
        data = json.loads(_STYLE_PATH.read_text(encoding="utf-8"))
        return StyleProfile.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return None
    # end load_style_profile


def save_style_profile(profile: StyleProfile) -> None:
    """Persist a style profile to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _STYLE_PATH.write_text(
        json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # end save_style_profile


def build_profile_from_samples(samples: list[str]) -> StyleProfile:
    """Analyze a list of writing samples and produce a StyleProfile.

    Each sample should be a paragraph or two of the user's actual writing
    (email draft, chat message, document).  The more samples, the more
    accurate the profile.
    """
    if not samples:
        return StyleProfile()

    combined = "\n\n".join(samples)
    sentences = _split_sentences(combined)
    if not sentences:
        return StyleProfile()

    # Formality: ratio of formal markers vs casual markers
    formal_markers = len(re.findall(r"\b(dear|regards|sincerely|furthermore|however|therefore|pursuant|accordingly)\b", combined, re.I))
    casual_markers = len(re.findall(r"\b(hey|hi|lol|yeah|ok|btw|tbh|gonna|wanna| kinda | sorta )\b", combined, re.I))
    formality = formal_markers / max(formal_markers + casual_markers, 1)
    # Smooth toward center if little data
    if formal_markers + casual_markers < 3:
        formality = 0.5

    # Capitalizes I
    i_words = re.findall(r"\b(i|I)\b", combined)
    capitalized_i = sum(1 for w in i_words if w == "I")
    capitalizes_i = (capitalized_i / max(len(i_words), 1)) > 0.8 if i_words else True

    # Contractions
    contractions = len(re.findall(r"\b\w+'\w+\b", combined))
    full_forms = len(re.findall(r"\b(do not|did not|cannot|will not|is not|are not|have not|has not|had not|would not|could not|should not)\b", combined, re.I))
    uses_contractions = contractions >= full_forms if (contractions + full_forms) > 0 else False

    # Average sentence length
    word_counts = [len(s.split()) for s in sentences if s.strip()]
    avg_len = sum(word_counts) / max(len(word_counts), 1)

    # Trailing period
    sentences_with_period = sum(1 for s in sentences if s.strip() and s.strip()[-1] in ".!?")
    trailing_period = (sentences_with_period / max(len(sentences), 1)) > 0.8

    # Greeting style
    greeting_style = _detect_greeting_style(combined)

    # Lowercase fragments (sentences under 3 words that start lowercase)
    fragments = [s for s in sentences if len(s.split()) <= 3]
    lowercase_fragments = False
    if fragments:
        lower_count = sum(1 for f in fragments if f and f[0].islower())
        lowercase_fragments = (lower_count / len(fragments)) > 0.5

    return StyleProfile(
        formality=round(formality, 2),
        capitalizes_i=capitalizes_i,
        uses_contractions=uses_contractions,
        avg_sentence_length=round(avg_len, 1),
        trailing_period=trailing_period,
        greeting_style=greeting_style,
        lowercase_fragments=lowercase_fragments,
    )
    # end build_profile_from_samples


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling abbreviations roughly."""
    # Simple split on . ! ? followed by space and capital letter
    text = text.replace("\n", " ")
    # Protect common abbreviations
    text = re.sub(r"\b(e\.g\.|i\.e\.|etc\.|vs\.|Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.|Inc\.|Ltd\.)\b", lambda m: m.group(0).replace(".", "\x00"), text)
    text = re.sub(r"\b([A-Z]\.[A-Z]\.)\b", lambda m: m.group(0).replace(".", "\x00"), text)

    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]
    # end _split_sentences


def _detect_greeting_style(text: str) -> str:
    """Detect whether the user opens with casual/formal greetings."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return "none"

    first_line = lines[0].lower()
    if re.search(r"^(dear\s+\w+|to\s+whom|attention:|subject:)", first_line):
        return "formal"
    if re.search(r"^(hi\s+|hello\s+|hey\s+|what's up|yo\s+|morning|evening)", first_line):
        return "casual"

    # Check first 3 lines for any greeting
    for line in lines[:3]:
        lowered = line.lower()
        if re.search(r"^(dear|to\s+whom|attention|subject:)", lowered):
            return "formal"
        if re.search(r"^(hi\s+|hello\s+|hey\s+)", lowered):
            return "casual"

    return "none"
    # end _detect_greeting_style
