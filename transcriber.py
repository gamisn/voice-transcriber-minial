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
import wave

import numpy as np

from voice_transcriber.clipboard import copy_to_clipboard
from voice_transcriber.config import load_config
from voice_transcriber.models import ProcessingOptions
from voice_transcriber.pipeline import process_transcript
from voice_transcriber.recorder import CHANNELS, SAMPLE_RATE, import_sounddevice, record_audio
from voice_transcriber.transcription import transcribe_audio


# ---------------------------------------------------------------------------
# WAV export (optional)
# ---------------------------------------------------------------------------

def _save_wav(audio: np.ndarray, path: str) -> None:
    """Persist a recording to disk as WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    with open(path, "wb") as f:
        f.write(buf.getvalue())
    sys.stderr.write(f"Audio saved to {path}\n")
    # end _save_wav


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice-transcriber",
        description="Record your voice and transcribe it locally with Whisper.",
    )
    p.add_argument(
        "-m", "--model",
        default=None,
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size. Overrides config default.",
    )
    p.add_argument(
        "-l", "--language",
        default=None,
        help="Language code for transcription. Overrides config default.",
    )
    p.add_argument(
        "--domain",
        default=None,
        help="Force a domain hint (e.g. 'technical', 'general'). Overrides config.",
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
        help="Copy transcription to clipboard.",
    )
    return p
    # end _build_parser


def main() -> None:
    args = _build_parser().parse_args()
    config = load_config()

    model = args.model if args.model is not None else config.default_model
    language = args.language if args.language is not None else config.default_language
    domain_hint = args.domain if args.domain is not None else config.domain_hint

    sd = import_sounddevice()

    if args.list_devices:
        print(sd.query_devices())
        return

    if args.device is not None:
        sd.default.device = (args.device, None)

    audio = record_audio(sd, stop_event=None, interactive=True, on_level=None)
    if audio is None:
        sys.exit(1)

    if args.save:
        _save_wav(audio, args.save)

    raw_text = transcribe_audio(audio, model_name=model, language=language, quiet=False)

    result = process_transcript(
        raw_transcript=raw_text,
        options=ProcessingOptions(
            language=language,
            domain_hint=domain_hint,
            custom_terms=config.custom_terms,
        ),
    )

    sys.stderr.write("\n--- Transcription ---\n\n")
    print(result.final_output)
    sys.stderr.write("\n---------------------\n")

    if result.applied_terms:
        sys.stderr.write(
            f"Domain: {result.detected_domain} | "
            f"Corrections: {', '.join(result.applied_terms)}\n"
        )

    if args.clipboard:
        if copy_to_clipboard(result.final_output):
            sys.stderr.write("Copied to clipboard.\n")
        else:
            sys.stderr.write(
                "Could not copy to clipboard. "
                "Install xclip, xsel, wl-copy, or pbcopy.\n"
            )
    # end main


if __name__ == "__main__":
    main()
