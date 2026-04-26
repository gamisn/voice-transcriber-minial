"""Typed errors and traceback logging for the voice transcriber.

Both daemons funnel unexpected failures through ``log_recording_failure`` so the
full traceback ends up on disk while only a short, user-friendly message is
surfaced via notifications or overlays.
"""

from __future__ import annotations

import pathlib
import sys
import traceback
from datetime import datetime, timezone


_CACHE_DIR = pathlib.Path.home() / ".cache" / "voice-transcriber"
_ERROR_LOG = _CACHE_DIR / "error.log"


class RecordingError(RuntimeError):
    """Raised when the recording pipeline fails for a known reason."""
    # end RecordingError


class TranscriptionError(RuntimeError):
    """Raised when Whisper transcription fails."""
    # end TranscriptionError


def log_recording_failure(stage: str, exc: BaseException) -> str:
    """Write a traceback for a daemon failure to the error log.

    Args:
        stage: Short identifier of where the failure happened
            (e.g. "record", "transcribe", "process").
        exc: The exception instance that was caught.

    Returns:
        A short single-line summary safe to show in a notification/overlay.
        The full traceback is written to ``~/.cache/voice-transcriber/error.log``.
    """
    summary = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with _ERROR_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"\n[{timestamp}] stage={stage} {summary}\n{tb}\n")
    except OSError as log_exc:
        # Read-only home, full disk, or similar. Logging must never mask the
        # original error path, but staying entirely silent loses the
        # traceback. Fall back to stderr so a developer can still see what
        # happened.
        try:
            print(
                f"voice-transcriber: could not write error log "
                f"({type(log_exc).__name__}: {log_exc}); "
                f"stage={stage} {summary}\n{tb}",
                file=sys.stderr,
            )
        except OSError:
            pass

    return f"{stage}: {summary}"
    # end log_recording_failure


def error_log_path() -> pathlib.Path:
    """Return the on-disk path of the error log."""
    return _ERROR_LOG
    # end error_log_path
