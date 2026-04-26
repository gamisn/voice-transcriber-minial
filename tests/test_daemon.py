"""Tests for the platform-agnostic daemon core.

These tests stub out audio recording and Whisper transcription so the full
``DaemonCore`` flow can be exercised without microphone or model dependencies.
"""

from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import numpy as np

from voice_transcriber import daemon as daemon_module
from voice_transcriber.daemon import (
    DaemonCore,
    RecordingHooks,
    SocketServer,
    State,
    send_command,
)


class _FakeHooks(RecordingHooks):
    def __init__(self) -> None:
        self.states: list[State] = []
        self.results: list[str] = []
        self.empties = 0
        self.errors: list[str] = []
        self.levels: list[float] = []
        # end __init__

    def on_state_change(self, state: State) -> None:
        self.states.append(state)
        # end on_state_change

    def on_level(self, normalized: float) -> None:
        self.levels.append(normalized)
        # end on_level

    def on_result(self, final_text: str) -> None:
        self.results.append(final_text)
        # end on_result

    def on_empty(self) -> None:
        self.empties += 1
        # end on_empty

    def on_error(self, summary: str) -> None:
        self.errors.append(summary)
        # end on_error


def _fake_record_audio(sd: object, stop_event: Optional[threading.Event],
                       interactive: bool, on_level: Optional[callable]) -> np.ndarray:
    """Return one second of int16 silence and respect the stop event."""
    if stop_event is not None and not stop_event.is_set():
        # Wait briefly so callers that set the event have time to do so.
        stop_event.wait(timeout=0.1)
    return np.zeros(16_000, dtype=np.int16)
    # end _fake_record_audio


def _fake_record_audio_none(*args: object, **kwargs: object) -> None:
    return None
    # end _fake_record_audio_none


def _fake_transcribe(audio: np.ndarray, model_name: str, language: str, quiet: bool) -> str:
    return "hello world"
    # end _fake_transcribe


def _fake_copy_to_clipboard(text: str) -> bool:
    return True
    # end _fake_copy_to_clipboard


class DaemonCoreStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = _FakeHooks()
        self.core = DaemonCore(
            model_name="base",
            language="en",
            domain_hint="auto",
            custom_terms=[],
            hooks=self.hooks,
        )
        # Pretend sounddevice is already loaded so we never call import_sounddevice.
        self.core._sd = object()
        # end setUp

    def test_initial_state_is_idle(self) -> None:
        self.assertEqual(self.core.get_state(), State.IDLE)
        # end test_initial_state_is_idle

    def test_full_recording_cycle_emits_expected_states(self) -> None:
        with patch("voice_transcriber.daemon.record_audio", _fake_record_audio), \
             patch("voice_transcriber.daemon.transcribe_audio", _fake_transcribe), \
             patch("voice_transcriber.daemon.copy_to_clipboard", _fake_copy_to_clipboard):
            self.core.toggle()
            # Stop recording immediately and wait for the worker.
            self.core.toggle()
            self._wait_for_idle(self.core, timeout_s=2.0)

        self.assertIn(State.RECORDING, self.hooks.states)
        self.assertIn(State.TRANSCRIBING, self.hooks.states)
        self.assertEqual(self.hooks.states[-1], State.IDLE)
        self.assertEqual(self.hooks.results, ["Hello world."])
        self.assertEqual(self.hooks.empties, 0)
        self.assertEqual(self.hooks.errors, [])
        # end test_full_recording_cycle_emits_expected_states

    def test_no_audio_emits_on_empty(self) -> None:
        with patch("voice_transcriber.daemon.record_audio", _fake_record_audio_none):
            self.core.toggle()
            self._wait_for_idle(self.core, timeout_s=1.0)

        self.assertEqual(self.hooks.empties, 1)
        self.assertEqual(self.hooks.results, [])
        self.assertEqual(self.hooks.states[-1], State.IDLE)
        # end test_no_audio_emits_on_empty

    def test_exception_inside_pipeline_routes_to_on_error(self) -> None:
        def _boom(*args: object, **kwargs: object) -> str:
            raise RuntimeError("transcription failed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch("voice_transcriber.daemon.record_audio", _fake_record_audio), \
                 patch("voice_transcriber.daemon.transcribe_audio", _boom), \
                 patch("voice_transcriber.errors._CACHE_DIR", tmp_path), \
                 patch("voice_transcriber.errors._ERROR_LOG", tmp_path / "error.log"):
                self.core.toggle()
                self.core.toggle()
                self._wait_for_idle(self.core, timeout_s=2.0)

        self.assertEqual(self.hooks.states[-1], State.IDLE)
        self.assertEqual(len(self.hooks.errors), 1)
        self.assertIn("RuntimeError", self.hooks.errors[0])
        # end test_exception_inside_pipeline_routes_to_on_error

    def test_toggle_when_already_recording_stops_session(self) -> None:
        with patch("voice_transcriber.daemon.record_audio", _fake_record_audio), \
             patch("voice_transcriber.daemon.transcribe_audio", _fake_transcribe), \
             patch("voice_transcriber.daemon.copy_to_clipboard", _fake_copy_to_clipboard):
            self.core.toggle()
            self.assertEqual(self.core.get_state(), State.RECORDING)
            self.core.toggle()
            self._wait_for_idle(self.core, timeout_s=2.0)

        self.assertEqual(self.core.get_state(), State.IDLE)
        # end test_toggle_when_already_recording_stops_session

    def _wait_for_idle(self, core: DaemonCore, timeout_s: float) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if core.get_state() == State.IDLE and core._work_thread is not None and not core._work_thread.is_alive():  # noqa: SLF001
                return
            time.sleep(0.02)
        raise AssertionError("Daemon did not return to IDLE within the deadline")
        # end _wait_for_idle


class SocketServerTests(unittest.TestCase):
    """Verify the toggle/status/unknown wire protocol over a temp socket."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmp.name)
        self._sock_path = tmp_path / "tray.sock"

        self._patches = [
            patch.object(daemon_module, "CACHE_DIR", tmp_path),
            patch.object(daemon_module, "SOCK_PATH", self._sock_path),
        ]
        for p in self._patches:
            p.start()

        self.toggle_count = 0
        self.state = State.IDLE

        def _on_toggle() -> None:
            self.toggle_count += 1

        def _on_status() -> State:
            return self.state

        self.server = SocketServer(on_toggle=_on_toggle, on_status=_on_status)
        self.server.start()
        time.sleep(0.05)
        # end setUp

    def tearDown(self) -> None:
        self.server.stop()
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()
        # end tearDown

    def test_toggle_command_invokes_callback(self) -> None:
        response = send_command("toggle")
        self.assertEqual(response, "ok")
        self.assertEqual(self.toggle_count, 1)
        # end test_toggle_command_invokes_callback

    def test_status_command_returns_current_state(self) -> None:
        self.state = State.RECORDING
        response = send_command("status")
        self.assertEqual(response, "recording")
        # end test_status_command_returns_current_state

    def test_unknown_command_returns_unknown(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect(str(self._sock_path))
            sock.sendall(b"nope\n")
            response = sock.recv(64).decode().strip()
        self.assertEqual(response, "unknown")
        # end test_unknown_command_returns_unknown


class SendCommandWhenNoDaemonTests(unittest.TestCase):
    def test_returns_none_when_socket_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "nope.sock"
            with patch.object(daemon_module, "SOCK_PATH", missing):
                self.assertIsNone(send_command("toggle"))
        # end test_returns_none_when_socket_missing


if __name__ == "__main__":
    unittest.main()
