from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from voice_transcriber.context import UserContext


@dataclass(slots=True)
class DomainMatch:
    """Result of domain auto-detection on a transcript."""

    domain_id: str = "general"
    confidence: float = 0.0
    keywords: list[str] = field(default_factory=list)
    # end DomainMatch


@dataclass(slots=True)
class ProcessingOptions:
    """Options controlling how a raw transcript is post-processed."""

    language: str
    domain_hint: str = "auto"
    custom_terms: list[str] = field(default_factory=list)
    context: "UserContext | None" = None

    # Phase 2: Dynamic Glossaries
    auto_glossary: bool = True

    # Phase 4: Style Learning
    style_enabled: bool = True
    # end ProcessingOptions


@dataclass(slots=True)
class TranscriptionResult:
    """Final result of the processing pipeline."""

    raw_transcript: str
    corrected_transcript: str
    final_output: str
    detected_domain: str
    domain_confidence: float
    applied_terms: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # end TranscriptionResult
