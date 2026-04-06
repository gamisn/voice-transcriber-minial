"""Shared pipeline code for the voice transcriber app."""

from .clipboard import copy_to_clipboard
from .config import AppConfig, load_config, save_config
from .models import DomainMatch, ProcessingOptions, TranscriptionResult
from .pipeline import process_transcript

__all__ = [
    "AppConfig",
    "DomainMatch",
    "ProcessingOptions",
    "TranscriptionResult",
    "copy_to_clipboard",
    "load_config",
    "process_transcript",
    "save_config",
]
