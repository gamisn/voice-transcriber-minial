"""Shared pipeline code for the voice transcriber app."""

from .clipboard import copy_to_clipboard
from .config import AppConfig, load_config, save_config
from .errors import (
    RecordingError,
    TranscriptionError,
    error_log_path,
    log_recording_failure,
)
from .models import DomainMatch, ProcessingOptions, TranscriptionResult
from .pipeline import process_transcript
from .recorder import import_sounddevice, record_audio
from .transcription import import_whisper, transcribe_audio

__all__ = [
    "AppConfig",
    "DomainMatch",
    "ProcessingOptions",
    "RecordingError",
    "TranscriptionError",
    "TranscriptionResult",
    "copy_to_clipboard",
    "error_log_path",
    "import_sounddevice",
    "import_whisper",
    "load_config",
    "log_recording_failure",
    "process_transcript",
    "record_audio",
    "save_config",
    "transcribe_audio",
]
