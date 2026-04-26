"""Whisper model loading and transcription.

Centralises the model cache so both CLI and tray use the same
load-once-reuse-many pattern.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

import numpy as np


_model_cache: dict[str, object] = {}
# _cache_lock guards _model_cache and _load_locks. _load_locks holds one
# threading.Lock per model_name so concurrent callers (preload_model_async
# vs the first user toggle) collapse into a single load instead of racing
# and loading the same Whisper model twice.
_cache_lock = threading.Lock()
_load_locks: dict[str, threading.Lock] = {}


def import_whisper():
    """Lazily import openai-whisper with a friendly error message."""
    try:
        import whisper
        return whisper
    except ImportError:
        raise ImportError(
            "'openai-whisper' is not installed. Run:  pip install openai-whisper"
        )
    # end import_whisper


def transcribe_audio(
    audio: np.ndarray,
    model_name: str,
    language: str,
    quiet: bool,
) -> str:
    """Load (or reuse) a Whisper model and transcribe int16 audio.

    Args:
        audio: int16 numpy array at 16 kHz mono.
        model_name: Whisper model size (tiny/base/small/medium/large).
        language: BCP-47 language code.
        quiet: When True, suppress all stderr output (for GUI callers).

    Returns:
        The raw transcript text from Whisper.
    """
    whisper = import_whisper()

    with _cache_lock:
        cached = _model_cache.get(model_name)
        load_lock = _load_locks.setdefault(model_name, threading.Lock())

    if cached is not None:
        model = cached
        if not quiet:
            sys.stderr.write(f"Model '{model_name}' (cached)\n")
    else:
        # Single-flight: only one thread loads a given model_name at a time;
        # the second waiter sees the cached result on the recheck below.
        with load_lock:
            with _cache_lock:
                cached = _model_cache.get(model_name)
            if cached is not None:
                model = cached
                if not quiet:
                    sys.stderr.write(f"Model '{model_name}' (cached)\n")
            else:
                if quiet:
                    model = whisper.load_model(model_name)
                else:
                    spinner = _Spinner(f"Loading Whisper model '{model_name}'")
                    spinner.start()
                    model = whisper.load_model(model_name)
                    spinner.stop(f"Model '{model_name}' loaded")

                with _cache_lock:
                    _model_cache[model_name] = model

    audio_f32: np.ndarray = audio.astype(np.float32) / 32768.0

    if quiet:
        result = model.transcribe(
            audio_f32,
            language=language,
            fp16=False,
            task="transcribe",
        )
    else:
        spinner = _Spinner("Transcribing audio")
        spinner.start()
        result = model.transcribe(
            audio_f32,
            language=language,
            fp16=False,
            task="transcribe",
        )
        spinner.stop("Transcription complete")

    return result["text"].strip()
    # end transcribe_audio


class _Spinner:
    """Minimal terminal spinner for long-running tasks."""

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, message: str) -> None:
        self._message = message
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, final: str) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        sys.stderr.write("\r\033[K")
        sys.stderr.write(final + "\n")
        sys.stderr.flush()

    def _spin(self) -> None:
        idx = 0
        while not self._stop.is_set():
            frame = self._FRAMES[idx % len(self._FRAMES)]
            sys.stderr.write(f"\r\033[K{frame} {self._message}")
            sys.stderr.flush()
            idx += 1
            time.sleep(0.08)
    # end _Spinner
