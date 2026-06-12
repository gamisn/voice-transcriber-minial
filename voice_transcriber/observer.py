"""Observer hook that runs after each transcription.

Records the transcript to history and, when ``auto_glossary`` is enabled,
proposes new glossary entries from raw/corrected differences.

This module is intentionally thin. All heavy logic lives in
``history.py`` and ``term_classifier.py``.
"""

from __future__ import annotations

from voice_transcriber import history as history_module
from voice_transcriber import term_classifier as classifier


def observe(
    raw: str,
    corrected: str,
    domain: str | None,
    confidence: float,
    applied_terms: list[str],
    auto_glossary: bool = True,
) -> None:
    """Called by the pipeline after every transcription.

    Args:
        raw: what Whisper originally produced.
        corrected: after glossary + formatter.
        domain: detected or manually chosen domain id.
        confidence: domain detection confidence (0.0–1.0).
        applied_terms: canonical terms that were corrected in this transcript.
        auto_glossary: whether to propose new glossary entries automatically.
    """
    # 1. Always record to history
    history_module.record_transcript(
        raw=raw,
        corrected=corrected,
        domain=domain,
        confidence=confidence,
        applied_terms=applied_terms,
    )

    # 2. If enabled, generate glossary candidates from this transcript
    if auto_glossary and domain:
        candidates = classifier.classify_correction(
            raw=raw,
            corrected=corrected,
            applied_terms=applied_terms,
            domain=domain,
        )
        for candidate in candidates:
            history_module.record_pending_term(
                domain=candidate["domain"],
                canonical=candidate["canonical"],
                alias=candidate["alias"],
                raw=candidate["raw"],
                corrected=candidate["corrected"],
            )
