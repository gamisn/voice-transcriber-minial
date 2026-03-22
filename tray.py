#!/usr/bin/python3
"""
voice-transcriber tray daemon — shows a small floating status window and lets
you toggle recording via a global keyboard shortcut or by clicking the window.

Usage:
    python tray.py            # start the daemon (floating status window)
    python tray.py toggle     # toggle recording (bind this to a hotkey)
    python tray.py status     # print current state and exit

GNOME / Pop!_OS keyboard shortcut setup:
    Settings -> Keyboard -> Customize Shortcuts -> Custom Shortcuts -> Add Shortcut
    Name:    Voice Transcriber Toggle
    Command: voice-transcriber-toggle
    Shortcut: Super+Shift+R  (or any combo you prefer)

The window stays in the corner of your screen. Click it to toggle recording,
or use the keyboard shortcut from any application.
"""

from __future__ import annotations

import os
import pathlib
import signal
import socket
import subprocess
import sys
import threading
from enum import Enum, auto
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Runtime paths
# ---------------------------------------------------------------------------

_CACHE_DIR = pathlib.Path.home() / ".cache" / "voice-transcriber"
_SOCK_PATH = _CACHE_DIR / "tray.sock"
_PID_PATH = _CACHE_DIR / "tray.pid"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()


# State display config: (base_label, background colour, text colour)
_STATE_UI = {
    State.IDLE:         ("  Mic: ready  ", "#2d2d2d", "#aaaaaa"),
    State.RECORDING:    ("  Rec ", "#8b0000", "#ff6b6b"),
    State.TRANSCRIBING: ("  Transcribing...  ", "#5a4000", "#ffd060"),
}

# Number of bars in the level meter shown during recording
_METER_WIDTH = 12

# ---------------------------------------------------------------------------
# Desktop notifications
# ---------------------------------------------------------------------------


def _notify(title: str, body: str) -> None:
    """Send a desktop notification via notify-send (best-effort)."""
    try:
        subprocess.run(
            ["notify-send", "--app-name=voice-transcriber", "--expire-time=8000",
             title, body],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass
    # end _notify


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard; returns True on success."""
    for cmd in (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],  # macOS
    ):
        try:
            subprocess.run(cmd, input=text.encode(), check=True, capture_output=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False
    # end _copy_to_clipboard


# ---------------------------------------------------------------------------
# Unix socket helpers
# ---------------------------------------------------------------------------


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _send_command(command: str) -> Optional[str]:
    """Send a command to the running daemon and return its response."""
    if not _SOCK_PATH.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect(str(_SOCK_PATH))
            sock.sendall((command + "\n").encode())
            return sock.recv(256).decode().strip()
    except (ConnectionRefusedError, OSError):
        return None
    # end _send_command


# ---------------------------------------------------------------------------
# GTK floating status window
# ---------------------------------------------------------------------------


class StatusWindow:
    """A small always-on-top floating pill that shows the current state."""

    def __init__(self, on_toggle_callback: Callable) -> None:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk, GLib

        self._Gtk = Gtk
        self._Gdk = Gdk
        self._GLib = GLib
        self._on_toggle = on_toggle_callback

        # Shared state — written from any thread, read by the GTK timer.
        self._desired_state = State.IDLE
        self._rendered_state = None  # force first paint
        self._level_text: Optional[str] = None  # live level bar during recording

        self._win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self._win.set_title("voice-transcriber")
        self._win.set_decorated(False)
        self._win.set_keep_above(True)
        self._win.set_skip_taskbar_hint(True)
        self._win.set_skip_pager_hint(True)
        self._win.stick()  # show on all workspaces

        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_geometry()
        self._screen_w = geometry.width
        self._screen_h = geometry.height

        self._css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._apply_css("#2d2d2d", "#aaaaaa")

        self._label = Gtk.Label(label="  Mic: ready  ")
        self._win.add(self._label)

        self._win.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._win.connect("button-press-event", self._on_click)
        self._win.connect("destroy", Gtk.main_quit)

        self._win.show_all()
        self._reposition()

        # Single fast timer drives ALL UI updates from the GTK main thread.
        # Worker threads never call GLib.idle_add — they just set attributes.
        GLib.timeout_add(150, self._poll_and_render)

    def _apply_css(self, bg_color: str, fg_color: str) -> None:
        self._css_provider.load_from_data(f"""
            window {{
                background-color: {bg_color};
                border-radius: 8px;
            }}
            label {{
                color: {fg_color};
                font-family: monospace;
                font-size: 13px;
                padding: 6px 14px;
            }}
        """.encode())

    def _reposition(self) -> None:
        self._win.resize(1, 1)
        self._win.queue_resize()
        self._GLib.idle_add(self._do_reposition)

    def _do_reposition(self) -> bool:
        w, h = self._win.get_size()
        margin = 16
        x = self._screen_w - w - margin
        y = self._screen_h - h - margin - 48
        self._win.move(x, y)
        return False

    def _on_click(self, widget, event) -> None:
        threading.Thread(target=self._on_toggle, daemon=True).start()

    def _poll_and_render(self) -> bool:
        """Called every 150ms on the GTK main thread. Reads shared state
        written by worker threads and applies it to the UI — no cross-thread
        GTK calls needed."""
        state = self._desired_state
        label_text, bg_color, fg_color = _STATE_UI[state]

        # Always repaint colours when state changed
        if state != self._rendered_state:
            self._apply_css(bg_color, fg_color)
            self._label.set_text(label_text)
            self._rendered_state = state

        # During recording, override the label with the live level bar
        if state == State.RECORDING:
            level_text = self._level_text
            if level_text is not None:
                self._label.set_text(level_text)

        return True  # keep repeating

    # -- Public API called from worker threads (thread-safe) -----------------

    def set_state(self, state: State) -> None:
        """Set the desired state. The GTK timer picks it up within 150ms."""
        self._desired_state = state
        self._level_text = None  # reset level bar on any state change

    def set_level(self, normalized: float) -> None:
        """Set the live level bar text. Only meaningful during RECORDING."""
        filled = min(int(normalized * _METER_WIDTH), _METER_WIDTH)
        bar = "|" * filled + "." * (_METER_WIDTH - filled)
        self._level_text = f"  Rec [{bar}]  "
    # end StatusWindow


# ---------------------------------------------------------------------------
# Tray daemon
# ---------------------------------------------------------------------------


class TrayDaemon:
    """Background daemon that owns the recording lifecycle and status window."""

    def __init__(self) -> None:
        self._model = "base"
        self._language = "en"
        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._stop_recording_event: Optional[threading.Event] = None
        self._work_thread: Optional[threading.Thread] = None
        self._server_thread: Optional[threading.Thread] = None
        self._window: Optional[StatusWindow] = None
        self._running = False
        self._sd = None  # cached sounddevice module
        self._whisper_model_cache: dict = {}  # {"model_name": loaded_model}

    # -- State management ----------------------------------------------------

    def _set_state(self, state: State) -> None:
        with self._state_lock:
            self._state = state
        if self._window is not None:
            self._window.set_state(state)

    def _get_state(self) -> State:
        with self._state_lock:
            return self._state

    # -- Toggle logic --------------------------------------------------------

    def toggle(self) -> None:
        state = self._get_state()
        if state == State.IDLE:
            self._start_recording()
        elif state == State.RECORDING:
            self._stop_recording()
        # TRANSCRIBING: ignore second press

    def _start_recording(self) -> None:
        if self._get_state() != State.IDLE:
            return
        self._set_state(State.RECORDING)
        self._stop_recording_event = threading.Event()
        self._work_thread = threading.Thread(
            target=self._recording_worker,
            args=(self._stop_recording_event,),
            daemon=True,
        )
        self._work_thread.start()

    def _stop_recording(self) -> None:
        if self._get_state() != State.RECORDING:
            return
        if self._stop_recording_event is not None:
            self._stop_recording_event.set()

    def _recording_worker(self, stop_event: threading.Event) -> None:
        """Background thread: record -> transcribe -> clipboard -> back to idle."""
        # Silence stderr for this thread — the spinner and level-meter in
        # transcriber.py write to sys.stderr, which can block when the
        # daemon is launched from a terminal whose buffer fills up.
        import io
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self._ensure_venv_imports()
            from transcriber import _import_sounddevice, transcribe, record_audio

            if self._sd is None:
                self._sd = _import_sounddevice()

            def _on_level(normalized: float) -> None:
                if self._window is not None and self._get_state() == State.RECORDING:
                    self._window.set_level(normalized)

            audio = record_audio(
                self._sd,
                stop_event=stop_event,
                interactive=False,
                on_level=_on_level,
            )

            if audio is None:
                self._set_state(State.IDLE)
                threading.Thread(target=_notify, args=("Voice Transcriber", "No audio captured."), daemon=True).start()
                return

            self._set_state(State.TRANSCRIBING)
            text = transcribe(
                audio,
                model_name=self._model,
                language=self._language,
                model_cache=self._whisper_model_cache,
            )

            if text:
                _copy_to_clipboard(text)
            self._set_state(State.IDLE)

            if text:
                threading.Thread(target=_notify, args=("Voice Transcriber", text), daemon=True).start()
            else:
                threading.Thread(target=_notify, args=("Voice Transcriber", "Transcription was empty."), daemon=True).start()

        except Exception as exc:  # noqa: BLE001
            self._set_state(State.IDLE)
            threading.Thread(target=_notify, args=("Voice Transcriber - Error", str(exc)), daemon=True).start()
        finally:
            sys.stderr = old_stderr
        # end _recording_worker

    def _ensure_venv_imports(self) -> None:
        """Add the venv's site-packages to sys.path once so sounddevice/
        numpy/whisper are importable under system python3."""
        if getattr(self, "_venv_injected", False):
            return
        _here = pathlib.Path(__file__).parent
        _venv_lib = _here / ".venv" / "lib"
        if _venv_lib.exists():
            for _pydir in _venv_lib.iterdir():
                _site = _pydir / "site-packages"
                if _site.exists() and str(_site) not in sys.path:
                    sys.path.insert(0, str(_site))
                    break
        if str(_here) not in sys.path:
            sys.path.insert(0, str(_here))
        self._venv_injected = True
        # end _ensure_venv_imports

    # -- Unix socket server --------------------------------------------------

    def _start_socket_server(self) -> None:
        _ensure_cache_dir()
        if _SOCK_PATH.exists():
            _SOCK_PATH.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(_SOCK_PATH))
        server.listen(5)
        server.settimeout(1.0)

        def _serve() -> None:
            while self._running:
                try:
                    conn, _ = server.accept()
                    threading.Thread(
                        target=self._handle_client,
                        args=(conn,),
                        daemon=True,
                    ).start()
                except socket.timeout:
                    continue
                except OSError:
                    break
            server.close()
            if _SOCK_PATH.exists():
                _SOCK_PATH.unlink()
        # end _serve

        self._server_thread = threading.Thread(target=_serve, daemon=True)
        self._server_thread.start()

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            data = conn.recv(64).decode().strip()
            if data == "toggle":
                self.toggle()
                conn.sendall(b"ok\n")
            elif data == "status":
                conn.sendall((self._get_state().name.lower() + "\n").encode())
            else:
                conn.sendall(b"unknown\n")
        except OSError:
            pass
        finally:
            conn.close()
        # end _handle_client

    # -- SIGUSR1 as an alternative toggle signal -----------------------------

    def _setup_signal_handler(self) -> None:
        def _handler(signum, frame):
            threading.Thread(target=self.toggle, daemon=True).start()

        try:
            signal.signal(signal.SIGUSR1, _handler)
        except (OSError, ValueError):
            pass

    # -- Lifecycle -----------------------------------------------------------

    def run(self, model: str = "base", language: str = "en") -> None:
        """Start the daemon. Blocks until the window is closed."""
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        self._model = model
        self._language = language
        self._running = True

        _ensure_cache_dir()
        _PID_PATH.write_text(str(os.getpid()))

        self._setup_signal_handler()
        self._start_socket_server()

        self._window = StatusWindow(on_toggle_callback=self.toggle)

        try:
            Gtk.main()
        finally:
            self._running = False
            if _PID_PATH.exists():
                _PID_PATH.unlink()
        # end run


# ---------------------------------------------------------------------------
# CLI subcommands: toggle / status
# ---------------------------------------------------------------------------


def cmd_toggle() -> None:
    """Send toggle to the running daemon."""
    response = _send_command("toggle")
    if response is None:
        print("ERROR: voice-transcriber daemon is not running.", file=sys.stderr)
        print("Start it with: voice-transcriber-tray", file=sys.stderr)
        sys.exit(1)
    # end cmd_toggle


def cmd_status() -> None:
    """Print the current daemon state."""
    response = _send_command("status")
    print("not running" if response is None else response)
    # end cmd_status


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="voice-transcriber-tray",
        description="Voice transcriber floating status window.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["toggle", "status"],
        help="toggle: flip recording state in the running daemon; "
             "status: print daemon state; "
             "(omit to start the daemon)",
    )
    parser.add_argument(
        "-m", "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base).",
    )
    parser.add_argument(
        "-l", "--language",
        default="en",
        help="Language code for transcription (default: en).",
    )

    args = parser.parse_args()

    if args.command == "toggle":
        cmd_toggle()
    elif args.command == "status":
        cmd_status()
    else:
        daemon = TrayDaemon()
        daemon.run(model=args.model, language=args.language)
    # end main


if __name__ == "__main__":
    main()
