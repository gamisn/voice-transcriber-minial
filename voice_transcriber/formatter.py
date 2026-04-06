from __future__ import annotations

import re


def normalize_transcript(text: str) -> str:
    """Polish a raw transcript into paste-ready text.

    Collapses whitespace, ensures sentence-start capitalization,
    and adds a trailing period if missing.
    """
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    if compact[-1] not in ".!?":
        compact += "."
    return compact[0].upper() + compact[1:]
    # end normalize_transcript
