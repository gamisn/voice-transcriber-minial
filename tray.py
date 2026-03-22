#!/usr/bin/python3
"""
voice-transcriber tray daemon — puts a microphone icon in the COSMIC / GNOME
panel and lets you toggle recording via a keyboard shortcut or clicking
the icon.

Usage:
    tray.py            # start the daemon (icon in panel)
    tray.py toggle     # toggle recording (bind this to a hotkey)
    tray.py status     # print current state and exit

Keyboard shortcut setup (COSMIC / Pop!_OS):
    Settings -> Keyboard -> Shortcuts -> Custom Shortcuts -> Add
    Name:    Voice Transcriber Toggle
    Command: voice-transcriber-toggle
    Shortcut: Super+Shift+R  (or any combo you prefer)
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
_ICON_DIR = _CACHE_DIR / "icons"
_SOCK_PATH = _CACHE_DIR / "tray.sock"
_PID_PATH = _CACHE_DIR / "tray.pid"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()


# State display: (menu_label, icon_filename_stem)
_STATE_UI = {
    State.IDLE:         ("Mic: ready — click to record", "vt-idle"),
    State.RECORDING:    ("Recording...",                 "vt-recording"),
    State.TRANSCRIBING: ("Transcribing...",              "vt-transcribing"),
}

_METER_WIDTH = 12

# ---------------------------------------------------------------------------
# SVG icons — generated once at startup into ~/.cache/voice-transcriber/icons/
# ---------------------------------------------------------------------------

_ICONS_SVG = {
    "vt-idle": """<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">
  <circle cx="11" cy="11" r="10" fill="#555555"/>
  <rect x="8" y="3" width="6" height="10" rx="3" fill="#cccccc"/>
  <path d="M5 11 Q5 16 11 16 Q17 16 17 11" stroke="#cccccc" stroke-width="1.5" fill="none"/>
  <line x1="11" y1="16" x2="11" y2="19" stroke="#cccccc" stroke-width="1.5"/>
  <line x1="8" y1="19" x2="14" y2="19" stroke="#cccccc" stroke-width="1.5"/>
</svg>""",

    "vt-recording": """<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">
  <circle cx="11" cy="11" r="10" fill="#8b0000"/>
  <circle cx="11" cy="11" r="5" fill="#ff4444"/>
</svg>""",

    "vt-transcribing": """<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">
  <circle cx="11" cy="11" r="10" fill="#5a4000"/>
  <text x="11" y="15" text-anchor="middle" font-size="10" fill="#ffd060" font-family="monospace">...</text>
</svg>""",
}


def _write_icons() -> None:
    """Write SVG icon files to the cache directory."""
    _ICON_DIR.mkdir(parents=True, exist_ok=True)
    for stem, svg in _ICONS_SVG.items():
        path = _ICON_DIR / f"{stem}.svg"
        if not path.exists():
            path.write_text(svg)
    # end _write_icons


def _icon_path(stem: str) -> str:
    return str(_ICON_DIR / f"{stem}.svg")


# ---------------------------------------------------------------------------
# Desktop notifications
# ---------------------------------------------------------------------------


def _notify(title: str, body: str) -> None:
    """Send a desktop notification via notify-send (best-effort)."""
    try:
        subprocess.run(
            ["notify-send", "--app-name=voice-transcriber",
             "--expire-time=8000", title, body],
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
    """Copy text to the system clipboard; returns True on success.

    wl-copy forks a background child to serve paste requests, so we must
    NOT use capture_output=True -- that keeps the pipe open until the child
    exits (i.e. until the next clipboard write), which would block the worker
    thread indefinitely and leave the tray stuck on 'Transcribing...'.
    We use Popen with DEVNULL for output and wait only for the parent to exit.
    """
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
# Recording overlay — small always-on-top pill shown during recording
# ---------------------------------------------------------------------------

_OVERLAY_CSS = b"""
#vt-overlay {
    background-color: rgba(30, 30, 30, 0.88);
    border-radius: 18px;
    padding: 6px 18px;
}
#vt-overlay label {
    color: #ffffff;
    font-family: monospace;
    font-size: 13px;
}
"""


class RecordingOverlay:
    """A small floating pill at the top-center of the screen that shows
    recording state and the live audio level bar."""

    def __init__(self, Gtk, Gdk, GLib) -> None:
        self._Gtk = Gtk
        self._Gdk = Gdk

        provider = Gtk.CssProvider()
        provider.load_from_data(_OVERLAY_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._win.set_name("vt-overlay")
        self._win.set_decorated(False)
        self._win.set_keep_above(True)
        self._win.set_accept_focus(False)
        self._win.set_resizable(False)
        self._win.stick()

        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self._win.set_visual(visual)
        self._win.set_app_paintable(True)

        self._label = Gtk.Label(label="")
        self._label.set_name("vt-overlay")
        self._win.add(self._label)

    def _reposition(self) -> None:
        """Center the overlay horizontally near the top of the primary monitor."""
        display = self._Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        self._win.show_all()
        alloc = self._win.get_allocation()
        x = geom.x + (geom.width - alloc.width) // 2
        y = geom.y + 32
        self._win.move(x, y)

    def show(self, text: str) -> None:
        self._label.set_text(text)
        self._reposition()
        self._win.show_all()

    def update_text(self, text: str) -> None:
        self._label.set_text(text)
        self._reposition()

    def hide(self) -> None:
        self._win.hide()
    # end RecordingOverlay


# ---------------------------------------------------------------------------
# Panel indicator (Ayatana AppIndicator3 → COSMIC / GNOME status area)
# ---------------------------------------------------------------------------


class PanelIndicator:
    """System tray indicator that lives in the COSMIC/GNOME panel."""

    def __init__(self, on_toggle_callback: Callable) -> None:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import Gtk, Gdk, GLib, AyatanaAppIndicator3

        self._Gtk = Gtk
        self._GLib = GLib
        self._on_toggle = on_toggle_callback

        # Shared state — written by worker threads, read by the GTK timer.
        self._desired_state = State.IDLE
        self._rendered_state: Optional[State] = None
        self._level_text: Optional[str] = None

        _write_icons()

        self._indicator = AyatanaAppIndicator3.Indicator.new(
            "voice-transcriber",
            _icon_path("vt-idle"),
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_icon_theme_path(str(_ICON_DIR))

        self._menu = Gtk.Menu()
        self._toggle_item = Gtk.MenuItem(label="Mic: ready — click to record")
        self._toggle_item.connect("activate", lambda _: threading.Thread(
            target=self._on_toggle, daemon=True).start())
        self._menu.append(self._toggle_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit)
        self._menu.append(quit_item)

        self._menu.show_all()
        self._indicator.set_menu(self._menu)

        self._overlay = RecordingOverlay(Gtk, Gdk, GLib)

        # Single timer drives all UI updates from the GTK main thread.
        GLib.timeout_add(150, self._poll_and_render)

    def _on_quit(self, *_) -> None:
        self._overlay.hide()
        self._Gtk.main_quit()

    def _poll_and_render(self) -> bool:
        """Called every 150ms on the GTK main thread. Reads shared state
        written by worker threads and updates the indicator + overlay."""
        state = self._desired_state

        if state != self._rendered_state:
            label, icon_stem = _STATE_UI[state]
            self._indicator.set_icon_full(_icon_path(icon_stem), label)
            self._toggle_item.set_label(label)
            self._rendered_state = state

            if state == State.RECORDING:
                self._overlay.show("Rec [............]")
            elif state == State.TRANSCRIBING:
                self._overlay.update_text("Transcribing...")
            else:
                self._overlay.hide()

        if state == State.RECORDING:
            level_text = self._level_text
            if level_text is not None:
                self._toggle_item.set_label(level_text)
                self._overlay.update_text(level_text)

        return True  # keep repeating

    # -- Public API (thread-safe: only sets plain Python attributes) ----------

    def set_state(self, state: State) -> None:
        self._desired_state = state
        self._level_text = None

    def set_level(self, normalized: float) -> None:
        filled = min(int(normalized * _METER_WIDTH), _METER_WIDTH)
        bar = "|" * filled + "." * (_METER_WIDTH - filled)
        self._level_text = f"Rec [{bar}]"
    # end PanelIndicator


# ---------------------------------------------------------------------------
# Tray daemon
# ---------------------------------------------------------------------------


class TrayDaemon:
    """Background daemon that owns the recording lifecycle and panel indicator."""

    def __init__(self) -> None:
        self._model = "base"
        self._language = "en"
        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._stop_recording_event: Optional[threading.Event] = None
        self._work_thread: Optional[threading.Thread] = None
        self._server_thread: Optional[threading.Thread] = None
        self._indicator: Optional[PanelIndicator] = None
        self._running = False
        self._sd = None  # cached sounddevice module
        self._whisper_model_cache: dict = {}

    # -- State management ----------------------------------------------------

    def _set_state(self, state: State) -> None:
        with self._state_lock:
            self._state = state
        if self._indicator is not None:
            self._indicator.set_state(state)

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
        # TRANSCRIBING: ignore

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
        """Background thread: record -> transcribe -> clipboard -> notify."""
        try:
            self._ensure_venv_imports()
            from transcriber import _import_sounddevice, transcribe, record_audio

            if self._sd is None:
                self._sd = _import_sounddevice()

            def _on_level(normalized: float) -> None:
                if self._indicator is not None and self._get_state() == State.RECORDING:
                    self._indicator.set_level(normalized)

            audio = record_audio(
                self._sd,
                stop_event=stop_event,
                interactive=False,
                on_level=_on_level,
            )

            if audio is None:
                self._set_state(State.IDLE)
                threading.Thread(
                    target=_notify,
                    args=("Voice Transcriber", "No audio captured."),
                    daemon=True,
                ).start()
                return

            self._set_state(State.TRANSCRIBING)

            # quiet=True: no Spinner, no stderr writes, no GIL contention.
            text = transcribe(
                audio,
                model_name=self._model,
                language=self._language,
                model_cache=self._whisper_model_cache,
                quiet=True,
            )

            # Copy to clipboard and go idle BEFORE sending the notification,
            # so the notification never blocks the state transition.
            if text:
                _copy_to_clipboard(text)
            self._set_state(State.IDLE)

            msg = text if text else "Transcription was empty."
            threading.Thread(
                target=_notify,
                args=("Voice Transcriber", msg),
                daemon=True,
            ).start()

        except Exception as exc:  # noqa: BLE001
            self._set_state(State.IDLE)
            threading.Thread(
                target=_notify,
                args=("Voice Transcriber - Error", str(exc)),
                daemon=True,
            ).start()
        # end _recording_worker

    def _ensure_venv_imports(self) -> None:
        """Inject the venv's site-packages so sounddevice/numpy/whisper are
        importable when tray.py runs under system python3."""
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

    # -- SIGUSR1 signal handler ----------------------------------------------

    def _setup_signal_handler(self) -> None:
        def _handler(signum, frame):
            threading.Thread(target=self.toggle, daemon=True).start()

        try:
            signal.signal(signal.SIGUSR1, _handler)
        except (OSError, ValueError):
            pass

    # -- Lifecycle -----------------------------------------------------------

    def run(self, model: str = "base", language: str = "en") -> None:
        """Start the daemon. Blocks until the user quits."""
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

        self._indicator = PanelIndicator(on_toggle_callback=self.toggle)

        try:
            Gtk.main()
        finally:
            self._running = False
            if _PID_PATH.exists():
                _PID_PATH.unlink()
        # end run


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def cmd_toggle() -> None:
    response = _send_command("toggle")
    if response is None:
        print("ERROR: voice-transcriber daemon is not running.", file=sys.stderr)
        print("Start it with: voice-transcriber-tray", file=sys.stderr)
        sys.exit(1)
    # end cmd_toggle


def cmd_status() -> None:
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
        description="Voice transcriber panel indicator.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["toggle", "status"],
        help="toggle: flip recording state; status: print state; "
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
