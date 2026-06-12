from __future__ import annotations

from voice_transcriber.context import load_user_context
from voice_transcriber.domain import apply_glossary, detect_domain
from voice_transcriber.formatter import normalize_transcript
from voice_transcriber.models import ProcessingOptions, TranscriptionResult
from voice_transcriber import observer as observer_module
from voice_transcriber.style import load_style_profile
from voice_transcriber.style_formatter import apply_style



def process_transcript(
    raw_transcript: str,
    options: ProcessingOptions,
) -> TranscriptionResult:
    """Post-process a raw Whisper transcript through the shared pipeline.

    Pipeline: domain detection -> glossary correction -> normalization.
    After completion, the observer logs the result and optionally proposes
    new glossary entries.
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

    # Phase 4: Style Learning — adapt to user's writing style
    if options.style_enabled:
        style_profile = load_style_profile()
        if style_profile is not None:
            final_output = apply_style(final_output, style_profile)


    result = TranscriptionResult(
        raw_transcript=raw_transcript,
        corrected_transcript=corrected,
        final_output=final_output,
        detected_domain=domain.domain_id,
        domain_confidence=domain.confidence,
        applied_terms=applied_terms,
        warnings=warnings,
    )

    # Phase 2: log to history and propose new glossary entries
    observer_module.observe(
        raw=raw_transcript,
        corrected=corrected,
        domain=domain.domain_id if domain.confidence > 0 else None,
        confidence=domain.confidence,
        applied_terms=applied_terms,
        auto_glossary=options.auto_glossary,
    )

    return result
    # end process_transcript
