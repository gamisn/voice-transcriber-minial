"""Shared pipeline code for the voice transcriber app."""

from .clipboard import copy_to_clipboard
from .config import AppConfig, load_config, save_config
from .models import DomainMatch, ProcessingOptions, TranscriptionResult
from .pipeline import process_transcript
from .recorder import import_sounddevice, record_audio
from .transcription import import_whisper, transcribe_audio

__all__ = [
    "AppConfig",
    "DomainMatch",
    "ProcessingOptions",
    "TranscriptionResult",
    "copy_to_clipboard",
    "import_sounddevice",
    "import_whisper",
    "load_config",
    "process_transcript",
    "record_audio",
    "save_config",
    "transcribe_audio",
]
