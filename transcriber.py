#!/usr/bin/env python3
"""
voice-transcriber — Record your voice and transcribe it locally using OpenAI Whisper.

Usage:
    python transcriber.py [OPTIONS]

Controls:
    Press ENTER or SPACE to stop recording.
    Press Ctrl+C to cancel without transcribing.
"""

from __future__ import annotations

import argparse
import io
import sys
import threading
import time
import wave
from contextlib import contextmanager
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Lazy imports so startup stays fast and errors are friendly
# ---------------------------------------------------------------------------

def _import_sounddevice():
    try:
        import sounddevice as sd
        return sd
    except ImportError:
        print("ERROR: 'sounddevice' is not installed. Run:")
        print("  pip install sounddevice")
        sys.exit(1)
    except OSError as exc:
        print(f"ERROR: PortAudio not found — {exc}")
        print("Install it with your package manager:")
        print("  Fedora/Nobara : sudo dnf install portaudio-devel")
        print("  Ubuntu/Pop!_OS: sudo apt install libportaudio2 portaudio19-dev")
        print("  Arch          : sudo pacman -S portaudio")
        sys.exit(1)


def _import_whisper():
    try:
        import whisper  # openai-whisper
        return whisper
    except ImportError:
        print("ERROR: 'openai-whisper' is not installed. Run:")
        print("  pip install openai-whisper")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16_000  # Whisper expects 16 kHz mono
CHANNELS = 1
DTYPE = "int16"
BLOCK_DURATION_MS = 100  # callback block size in ms
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION_MS / 1000)

# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

@contextmanager
def _raw_terminal():
    """Put stdin into raw/cbreak mode so we can detect single key presses."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _wait_for_stop_key(stop_event: threading.Event) -> None:
    """Block until the user presses ENTER, SPACE, or 'q'."""
    with _raw_terminal():
        while not stop_event.is_set():
            ch = sys.stdin.read(1)
            if ch in ("\n", "\r", " ", "q", "Q"):
                stop_event.set()
                return


# ---------------------------------------------------------------------------
# Spinner / progress indicator
# ---------------------------------------------------------------------------

class Spinner:
    """Minimal terminal spinner for long-running tasks."""

    FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, message: str = "Processing"):
        self._message = message
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, final: str = ""):
        self._stop.set()
        if self._thread:
            self._thread.join()
        # clear spinner line
        sys.stderr.write("\r\033[K")
        if final:
            sys.stderr.write(final + "\n")
        sys.stderr.flush()

    def _spin(self):
        idx = 0
        while not self._stop.is_set():
            frame = self.FRAMES[idx % len(self.FRAMES)]
            sys.stderr.write(f"\r\033[K{frame} {self._message}")
            sys.stderr.flush()
            idx += 1
            time.sleep(0.08)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_audio(
    sd,
    stop_event: Optional[threading.Event] = None,
    interactive: bool = True,
    on_level: Optional[callable] = None,
) -> Optional[np.ndarray]:
    """Record audio from the default microphone until the user stops.

    Args:
        sd: The sounddevice module.
        stop_event: An external Event that, when set, stops recording.
            If None and interactive is True, a new event is created and
            controlled by keyboard input.
        interactive: When True, prints prompts and listens for keystrokes
            to stop recording. Set to False when stop_event is managed
            externally (e.g. from the tray daemon).
        on_level: Optional callback called with a normalized RMS float
            [0.0, 1.0] every ~100ms during recording. When provided, the
            stderr level bar is suppressed so the caller handles display.
    """
    chunks: list[np.ndarray] = []

    if stop_event is None:
        stop_event = threading.Event()

    def _callback(indata, frames, time_info, status):
        if status:
            sys.stderr.write(f"\n⚠ audio warning: {status}\n")
        chunks.append(indata.copy())

    if interactive:
        sys.stderr.write("\n🎙  Recording… (press ENTER, SPACE, or 'q' to stop)\n\n")

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=BLOCK_SIZE,
        callback=_callback,
    )

    meter_stop = threading.Event()

    def _level_meter():
        # Normalisation constant: int16 peak is 32768; target "loud speech"
        # at ~0.5 normalised around RMS ~400-600.
        _rms_scale = 600.0
        while not meter_stop.is_set():
            if chunks:
                latest = chunks[-1].astype(np.float32)
                rms = np.sqrt(np.mean(latest ** 2))
                normalized = min(rms / _rms_scale, 1.0)

                if on_level is not None:
                    on_level(normalized)
                else:
                    # Terminal bar: 0-30 blocks
                    level = min(int(rms / 800 * 30), 30)
                    bar = "█" * level + "░" * (30 - level)
                    sys.stderr.write(f"\r  Level: [{bar}] ")
                    sys.stderr.flush()
            time.sleep(0.1)

    meter_thread = threading.Thread(target=_level_meter, daemon=True)

    try:
        with stream:
            meter_thread.start()
            if interactive:
                _wait_for_stop_key(stop_event)
            else:
                # Block until the external stop_event is set
                stop_event.wait()
    except KeyboardInterrupt:
        sys.stderr.write("\n\n✗ Recording cancelled.\n")
        return None
    finally:
        meter_stop.set()
        if interactive:
            sys.stderr.write("\r\033[K")  # clear meter line

    if not chunks:
        sys.stderr.write("⚠ No audio captured.\n")
        return None

    audio = np.concatenate(chunks, axis=0).flatten()
    duration = len(audio) / SAMPLE_RATE
    sys.stderr.write(f"✓ Captured {duration:.1f}s of audio\n\n")
    return audio
    # end record_audio


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe(
    audio: np.ndarray,
    model_name: str,
    language: str,
    model_cache: Optional[dict] = None,
    quiet: bool = False,
) -> str:
    """Load Whisper model and transcribe the in-memory audio.

    Args:
        model_cache: Optional dict used to persist loaded models across calls.
            When provided, the model is loaded once and reused on subsequent
            calls with the same model_name, making the 2nd+ transcription
            significantly faster.
        quiet: When True, skip all Spinner output and stderr writes. Use this
            when calling from a GUI daemon where stderr writes cause GIL
            contention that blocks the UI event loop.
    """
    whisper = _import_whisper()

    if model_cache is not None and model_name in model_cache:
        model = model_cache[model_name]
        if not quiet:
            sys.stderr.write(f"✓ Model '{model_name}' (cached)\n")
    else:
        if quiet:
            model = whisper.load_model(model_name)
        else:
            spinner = Spinner(f"Loading Whisper model '{model_name}'")
            spinner.start()
            model = whisper.load_model(model_name)
            spinner.stop(f"✓ Model '{model_name}' loaded")
        if model_cache is not None:
            model_cache[model_name] = model

    audio_f32 = audio.astype(np.float32) / 32768.0

    if quiet:
        result = model.transcribe(
            audio_f32,
            language=language,
            fp16=False,
            task="transcribe",
        )
    else:
        spinner = Spinner("Transcribing audio")
        spinner.start()
        result = model.transcribe(
            audio_f32,
            language=language,
            fp16=False,
            task="transcribe",
        )
        spinner.stop("✓ Transcription complete")

    return result["text"].strip()


# ---------------------------------------------------------------------------
# WAV export (optional)
# ---------------------------------------------------------------------------

def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    """Convert int16 numpy array to in-memory WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def save_wav(audio: np.ndarray, path: str) -> None:
    """Persist a recording to disk as WAV."""
    wav_bytes = _audio_to_wav_bytes(audio)
    with open(path, "wb") as f:
        f.write(wav_bytes)
    sys.stderr.write(f"💾 Audio saved to {path}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice-transcriber",
        description="Record your voice and transcribe it locally with Whisper.",
    )
    p.add_argument(
        "-m", "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base). Larger = more accurate but slower.",
    )
    p.add_argument(
        "-l", "--language",
        default="en",
        help="Language code for transcription (default: en).",
    )
    p.add_argument(
        "--save",
        metavar="PATH",
        default=None,
        help="Optionally save the recording as a WAV file at PATH.",
    )
    p.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit.",
    )
    p.add_argument(
        "-d", "--device",
        type=int,
        default=None,
        help="Input device index (see --list-devices). Uses system default if omitted.",
    )
    p.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy transcription to clipboard (requires xclip or xsel).",
    )
    return p


def copy_to_clipboard(text: str) -> bool:
    """Try to copy text to the system clipboard (Linux/macOS).

    Uses Popen with DEVNULL to avoid blocking on wl-copy's forked background
    child process (which would keep a captured pipe open indefinitely).
    """
    import subprocess
    data = text.encode()
    for cmd in (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],  # macOS
    ):
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.stdin.write(data)
            proc.stdin.close()
            proc.wait(timeout=2)
            return True
        except FileNotFoundError:
            continue
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
            except OSError:
                pass
            continue
    return False


def main() -> None:
    args = build_parser().parse_args()
    sd = _import_sounddevice()

    # --list-devices
    if args.list_devices:
        print(sd.query_devices())
        return

    # Set device if specified
    if args.device is not None:
        sd.default.device = (args.device, None)

    # Record
    audio = record_audio(sd, interactive=True)
    if audio is None:
        sys.exit(1)

    # Optionally save
    if args.save:
        save_wav(audio, args.save)

    # Transcribe
    text = transcribe(audio, model_name=args.model, language=args.language)

    # Output
    sys.stderr.write("\n─── Transcription ───────────────────────────────────\n\n")
    print(text)
    sys.stderr.write("\n─────────────────────────────────────────────────────\n")

    # Clipboard
    if args.clipboard:
        if copy_to_clipboard(text):
            sys.stderr.write("📋 Copied to clipboard.\n")
        else:
            sys.stderr.write("⚠ Could not copy to clipboard. Install xclip, xsel, or wl-copy.\n")


if __name__ == "__main__":
    main()
