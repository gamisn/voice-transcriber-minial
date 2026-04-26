from __future__ import annotations

import re

# Sentence terminators that should be followed by a capital letter.
_SENTENCE_TERMINATORS: frozenset[str] = frozenset({".", "!", "?"})


def normalize_transcript(text: str) -> str:
    """Polish a raw transcript into paste-ready text.

    Collapses whitespace, capitalizes every sentence start (after . ! ?),
    and adds a trailing period if missing.
    """
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    if compact[-1] not in _SENTENCE_TERMINATORS:
        compact += "."

    return _capitalize_sentences(compact)
    # end normalize_transcript


def _capitalize_sentences(text: str) -> str:
    """Uppercase the first alphabetic character of every sentence.

    A sentence boundary is a terminator (. ! ?) followed by whitespace,
    plus the very first character of the string.
    """
    chars: list[str] = list(text)
    capitalize_next = True

    for index, char in enumerate(chars):
        if capitalize_next and char.isalpha():
            chars[index] = char.upper()
            capitalize_next = False
            continue

        if char in _SENTENCE_TERMINATORS:
            capitalize_next = True
            continue

        if capitalize_next and not char.isspace():
            # Stop searching once we hit a non-space, non-letter char
            # (e.g. quotes, parens) — keep flag set so we still capitalize
            # the next letter we find.
            continue

    return "".join(chars)
    # end _capitalize_sentences
