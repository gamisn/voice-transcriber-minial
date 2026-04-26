"""Platform-agnostic core for the voice transcriber daemons.

Both the Linux GTK tray and the macOS menubar build their UI on top of this
module. It owns:

- The recording state machine (``State``).
- The unix-socket toggle/status protocol shared by both platforms.
- The recording -> transcription -> pipeline -> clipboard flow
  (``RecordingSession``), with hooks for UI callbacks.
- A small ``preload_model`` helper so the daemon can warm up Whisper at
  startup instead of paying the load cost on the first hotkey press.

Trust model: the unix socket is restricted to the same Unix user, local
session only. There is no authentication on the wire — the file-mode 0600
on the socket is the only access control.
"""

from __future__ import annotations

import os
import pathlib
import socket
import threading
from enum import Enum, auto
from typing import Callable, Optional, Protocol

import numpy as np

from .clipboard import copy_to_clipboard
from .errors import log_recording_failure
from .models import ProcessingOptions
from .pipeline import process_transcript
from .recorder import import_sounddevice, record_audio
from .transcription import transcribe_audio


CACHE_DIR: pathlib.Path = pathlib.Path.home() / ".cache" / "voice-transcriber"
SOCK_PATH: pathlib.Path = CACHE_DIR / "tray.sock"
PID_PATH: pathlib.Path = CACHE_DIR / "tray.pid"


class State(Enum):
    """High-level daemon state visible in the tray/menubar UI."""

    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    # end State


def ensure_cache_dir() -> None:
    """Create the cache directory if it does not yet exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # end ensure_cache_dir


def send_command(command: str) -> Optional[str]:
    """Send a command to the running daemon and return its response.

    Returns ``None`` when no daemon is listening.
    """
    if not SOCK_PATH.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect(str(SOCK_PATH))
            sock.sendall((command + "\n").encode())
            return sock.recv(256).decode().strip()
    except (ConnectionRefusedError, OSError):
        return None
    # end send_command


class SocketServer:
    """Listens on the daemon's unix socket and dispatches toggle/status."""

    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_status: Callable[[], State],
    ) -> None:
        self._on_toggle = on_toggle
        self._on_status = on_status
        self._server_thread: Optional[threading.Thread] = None
        self._server: Optional[socket.socket] = None
        self._running = False
        # end __init__

    def start(self) -> None:
        ensure_cache_dir()
        if SOCK_PATH.exists():
            SOCK_PATH.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(SOCK_PATH))
        # Restrict to owner-only RW so other local users cannot send
        # toggle/status even on hosts where ~/.cache is world-traversable.
        os.chmod(SOCK_PATH, 0o600)
        server.listen(5)
        server.settimeout(1.0)
        self._server = server
        self._running = True

        self._server_thread = threading.Thread(target=self._serve, daemon=True)
        self._server_thread.start()
        # end start

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        if SOCK_PATH.exists():
            SOCK_PATH.unlink()
        # end stop

    def _serve(self) -> None:
        assert self._server is not None
        while self._running:
            try:
                conn, _ = self._server.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break
        # end _serve

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            data = conn.recv(64).decode().strip()
            if data == "toggle":
                self._on_toggle()
                conn.sendall(b"ok\n")
            elif data == "status":
                conn.sendall((self._on_status().name.lower() + "\n").encode())
            else:
                conn.sendall(b"unknown\n")
        except OSError:
            pass
        finally:
            conn.close()
        # end _handle_client


class RecordingHooks(Protocol):
    """UI callbacks invoked by ``RecordingSession`` at each pipeline stage.

    Implementations must define every method — using a ``Protocol`` instead
    of a concrete base class means a forgotten method fails at type-check
    time rather than silently no-op'ing in production.

    Hooks run on the recording worker thread, so implementations must be
    thread-safe (typically by scheduling work onto the GTK / AppKit main
    loop).
    """

    def on_state_change(self, state: State) -> None: ...
    def on_level(self, normalized: float) -> None: ...
    def on_result(self, final_text: str) -> None: ...
    def on_empty(self) -> None: ...
    def on_error(self, summary: str) -> None: ...
    # end RecordingHooks


class RecordingSession:
    """Owns a single record -> transcribe -> process -> clipboard cycle.

    The daemon creates a new ``RecordingSession`` for every toggle. State
    transitions and errors are reported through the supplied ``RecordingHooks``.
    """

    def __init__(
        self,
        sd: object,
        model_name: str,
        language: str,
        domain_hint: str,
        custom_terms: list[str],
        hooks: RecordingHooks,
    ) -> None:
        self._sd = sd
        self._model_name = model_name
        self._language = language
        self._domain_hint = domain_hint
        self._custom_terms = custom_terms
        self._hooks = hooks
        # end __init__

    def run(self, stop_event: threading.Event) -> None:
        """Run the full pipeline. Blocks until done or aborted."""
        try:
            audio = record_audio(
                self._sd,
                stop_event=stop_event,
                interactive=False,
                on_level=self._hooks.on_level,
            )
            if audio is None:
                self._hooks.on_state_change(State.IDLE)
                self._hooks.on_empty()
                return

            self._hooks.on_state_change(State.TRANSCRIBING)

            raw_text = transcribe_audio(
                audio,
                model_name=self._model_name,
                language=self._language,
                quiet=True,
            )

            result = process_transcript(
                raw_transcript=raw_text,
                options=ProcessingOptions(
                    language=self._language,
                    domain_hint=self._domain_hint,
                    custom_terms=self._custom_terms,
                ),
            )

            output = result.final_output or ""
            if output:
                copy_to_clipboard(output)

            self._hooks.on_state_change(State.IDLE)
            if output:
                self._hooks.on_result(output)
            else:
                self._hooks.on_empty()

        except Exception as exc:
            summary = log_recording_failure("recording_session", exc)
            self._hooks.on_state_change(State.IDLE)
            self._hooks.on_error(summary)
        # end run


class DaemonCore:
    """Thread-safe state machine plus session coordinator.

    The platform-specific UI delegates ``toggle()`` to this class and
    receives state/level/result notifications via the ``RecordingHooks``
    it provides.
    """

    def __init__(
        self,
        model_name: str,
        language: str,
        domain_hint: str,
        custom_terms: list[str],
        hooks: RecordingHooks,
    ) -> None:
        self._model_name = model_name
        self._language = language
        self._domain_hint = domain_hint
        self._custom_terms = custom_terms
        self._hooks = hooks

        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._stop_recording_event: Optional[threading.Event] = None
        self._work_thread: Optional[threading.Thread] = None
        self._sd: Optional[object] = None
        # end __init__

    def get_state(self) -> State:
        with self._state_lock:
            return self._state
        # end get_state

    def _set_state(self, state: State) -> None:
        with self._state_lock:
            self._state = state
        self._hooks.on_state_change(state)
        # end _set_state

    def toggle(self) -> None:
        """Flip the state machine: idle -> recording, recording -> stop."""
        state = self.get_state()
        if state == State.IDLE:
            self._start_recording()
        elif state == State.RECORDING:
            self._stop_recording()
        # end toggle

    def _start_recording(self) -> None:
        if self.get_state() != State.IDLE:
            return
        if self._sd is None:
            try:
                self._sd = import_sounddevice()
            except (ImportError, OSError) as exc:
                summary = log_recording_failure("sounddevice_import", exc)
                self._hooks.on_error(summary)
                return

        self._set_state(State.RECORDING)
        self._stop_recording_event = threading.Event()

        # Wrap the hooks so the inner session also reports state changes
        # through the daemon's locked _set_state path.
        session_hooks = _DaemonSessionHooks(self)

        session = RecordingSession(
            sd=self._sd,
            model_name=self._model_name,
            language=self._language,
            domain_hint=self._domain_hint,
            custom_terms=self._custom_terms,
            hooks=session_hooks,
        )

        self._work_thread = threading.Thread(
            target=session.run,
            args=(self._stop_recording_event,),
            daemon=True,
        )
        self._work_thread.start()
        # end _start_recording

    def _stop_recording(self) -> None:
        if self.get_state() != State.RECORDING:
            return
        if self._stop_recording_event is not None:
            self._stop_recording_event.set()
        # end _stop_recording

    def update_options(
        self,
        model_name: str,
        language: str,
        domain_hint: str,
        custom_terms: list[str],
    ) -> None:
        """Update the options used by the next recording. Useful for tests."""
        self._model_name = model_name
        self._language = language
        self._domain_hint = domain_hint
        self._custom_terms = custom_terms
        # end update_options


class _DaemonSessionHooks(RecordingHooks):
    """Bridge that routes session state changes through the daemon lock."""

    def __init__(self, daemon: DaemonCore) -> None:
        self._daemon = daemon
        # end __init__

    def on_state_change(self, state: State) -> None:
        self._daemon._set_state(state)  # noqa: SLF001 — internal bridge
        # end on_state_change

    def on_level(self, normalized: float) -> None:
        self._daemon._hooks.on_level(normalized)  # noqa: SLF001
        # end on_level

    def on_result(self, final_text: str) -> None:
        self._daemon._hooks.on_result(final_text)  # noqa: SLF001
        # end on_result

    def on_empty(self) -> None:
        self._daemon._hooks.on_empty()  # noqa: SLF001
        # end on_empty

    def on_error(self, summary: str) -> None:
        self._daemon._hooks.on_error(summary)  # noqa: SLF001
        # end on_error


def preload_model_async(model_name: str) -> threading.Thread:
    """Warm up the Whisper model in a background daemon thread.

    Returns the thread so callers can join it in tests. The thread swallows
    failures (and logs them) because preloading is an optimisation, not a
    correctness requirement: the first real transcription will surface any
    real load error.
    """
    def _worker() -> None:
        try:
            silent = np.zeros(16_000, dtype=np.int16)
            transcribe_audio(silent, model_name=model_name, language="en", quiet=True)
        except Exception as exc:
            log_recording_failure("preload_model", exc)
        # end _worker

    thread = threading.Thread(target=_worker, name="vt-preload-model", daemon=True)
    thread.start()
    return thread
    # end preload_model_async
