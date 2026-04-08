"""Audio recording via sounddevice.

Provides a single record_audio() function used by both the CLI
and tray entry points.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Optional

import numpy as np


SAMPLE_RATE: int = 16_000
CHANNELS: int = 1
DTYPE: str = "int16"
BLOCK_DURATION_MS: int = 100
BLOCK_SIZE: int = int(SAMPLE_RATE * BLOCK_DURATION_MS / 1000)

_RMS_SCALE: float = 600.0


def import_sounddevice():
    """Lazily import sounddevice with friendly error messages."""
    try:
        import sounddevice as sd
        return sd
    except ImportError:
        raise ImportError(
            "'sounddevice' is not installed. Run:  pip install sounddevice"
        )
    except OSError as exc:
        raise OSError(
            f"PortAudio not found — {exc}. "
            "Install it with your package manager: "
            "Ubuntu/Pop!_OS: sudo apt install libportaudio2 portaudio19-dev  |  "
            "macOS: brew install portaudio  |  "
            "Windows: included with sounddevice"
        )
    # end import_sounddevice


def record_audio(
    sd: object,
    stop_event: Optional[threading.Event],
    interactive: bool,
    on_level: Optional[Callable[[float], None]],
) -> Optional[np.ndarray]:
    """Record audio from the default microphone until stopped.

    Args:
        sd: The sounddevice module (from import_sounddevice()).
        stop_event: Event that, when set, stops recording.
            If None and interactive is True, a new event is created
            and controlled by keyboard input.
        interactive: When True, prints prompts and listens for keystrokes.
        on_level: Optional callback with a normalised RMS float [0.0, 1.0]
            every ~100ms. When provided the stderr level bar is suppressed.

    Returns:
        int16 numpy array of recorded audio, or None on cancel / no audio.
    """
    chunks: list[np.ndarray] = []

    if stop_event is None:
        stop_event = threading.Event()

    def _callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        if status:
            sys.stderr.write(f"\naudio warning: {status}\n")
        chunks.append(indata.copy())

    if interactive:
        sys.stderr.write("\nRecording... (press ENTER, SPACE, or 'q' to stop)\n\n")

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=BLOCK_SIZE,
        callback=_callback,
    )

    meter_stop = threading.Event()

    def _level_meter() -> None:
        while not meter_stop.is_set():
            if chunks:
                latest = chunks[-1].astype(np.float32)
                rms = float(np.sqrt(np.mean(latest ** 2)))
                normalised = min(rms / _RMS_SCALE, 1.0)

                if on_level is not None:
                    on_level(normalised)
                else:
                    level = min(int(rms / 800 * 30), 30)
                    bar = "█" * level + "░" * (30 - level)
                    sys.stderr.write(f"\r  Level: [{bar}] ")
                    sys.stderr.flush()
            time.sleep(0.1)
        # end _level_meter

    meter_thread = threading.Thread(target=_level_meter, daemon=True)

    try:
        with stream:
            meter_thread.start()
            if interactive:
                _wait_for_stop_key(stop_event)
            else:
                stop_event.wait()
    except KeyboardInterrupt:
        sys.stderr.write("\n\nRecording cancelled.\n")
        return None
    finally:
        meter_stop.set()
        if interactive:
            sys.stderr.write("\r\033[K")

    if not chunks:
        sys.stderr.write("No audio captured.\n")
        return None

    audio: np.ndarray = np.concatenate(chunks, axis=0).flatten()
    duration = len(audio) / SAMPLE_RATE
    sys.stderr.write(f"Captured {duration:.1f}s of audio\n\n")
    return audio
    # end record_audio


def _wait_for_stop_key(stop_event: threading.Event) -> None:
    """Block until the user presses ENTER, SPACE, or 'q'.

    Uses msvcrt on Windows, termios on Unix.
    """
    if sys.platform == "win32":
        _wait_for_stop_key_windows(stop_event)
    else:
        _wait_for_stop_key_unix(stop_event)
    # end _wait_for_stop_key


def _wait_for_stop_key_unix(stop_event: threading.Event) -> None:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not stop_event.is_set():
            ch = sys.stdin.read(1)
            if ch in ("\n", "\r", " ", "q", "Q"):
                stop_event.set()
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    # end _wait_for_stop_key_unix


def _wait_for_stop_key_windows(stop_event: threading.Event) -> None:
    import msvcrt

    while not stop_event.is_set():
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\n", "\r", " ", "q", "Q"):
                stop_event.set()
                return
        time.sleep(0.05)
    # end _wait_for_stop_key_windows
