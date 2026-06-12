from __future__ import annotations

from voice_transcriber.context import load_user_context
from voice_transcriber.domain import apply_glossary, detect_domain
from voice_transcriber.formatter import normalize_transcript
from voice_transcriber.models import ProcessingOptions, TranscriptionResult


def process_transcript(
    raw_transcript: str,
    options: ProcessingOptions,
) -> TranscriptionResult:
    """Post-process a raw Whisper transcript through the shared pipeline.

    Pipeline: domain detection -> glossary correction -> normalization.
    """
    warnings: list[str] = []
    if not raw_transcript.strip():
        warnings.append("Transcription was empty.")

    ctx = options.context or load_user_context()
    domain = detect_domain(raw_transcript, domain_hint=options.domain_hint, context=ctx)
    corrected, applied_terms = apply_glossary(
        raw_transcript, domain, options.custom_terms,
    )
    final_output = normalize_transcript(corrected)

    return TranscriptionResult(
        raw_transcript=raw_transcript,
        corrected_transcript=corrected,
        final_output=final_output,
        detected_domain=domain.domain_id,
        domain_confidence=domain.confidence,
        applied_terms=applied_terms,
        warnings=warnings,
    )
    # end process_transcript
