#!/usr/bin/env python3
"""
voice-transcriber macOS menubar daemon — puts a microphone icon in the
macOS menu bar and lets you toggle recording via a global keyboard shortcut
(Cmd+Shift+R) or by clicking the menu bar icon.

Usage:
    mac_menubar.py             # start the daemon
    mac_menubar.py toggle      # toggle recording in the running daemon
    mac_menubar.py status      # print current state and exit

Requires macOS Accessibility permission for the global keyboard shortcut.
Grant it in: System Settings > Privacy & Security > Accessibility.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import socket
import subprocess
import sys
import threading
from enum import Enum, auto
from typing import Optional


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


_STATE_TITLES = {
    State.IDLE: "🎙",
    State.RECORDING: "🔴",
    State.TRANSCRIBING: "⏳",
}

_STATE_MENU_LABELS = {
    State.IDLE: "Click to record",
    State.RECORDING: "Recording... (click to stop)",
    State.TRANSCRIBING: "Transcribing...",
}


# ---------------------------------------------------------------------------
# macOS notifications
# ---------------------------------------------------------------------------


def _notify(title: str, body: str) -> None:
    """Send a macOS notification via osascript (best-effort)."""
    script = f'display notification "{body}" with title "{title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass
    # end _notify


# ---------------------------------------------------------------------------
# Unix socket helpers (same protocol as Linux tray)
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
# Menubar daemon
# ---------------------------------------------------------------------------


class MacMenubarDaemon:
    """macOS menu bar daemon with global hotkey support."""

    def __init__(self) -> None:
        self._model: str = "base"
        self._language: str = "en"
        self._domain_hint: str = "auto"
        self._custom_terms: list[str] = []
        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._stop_recording_event: Optional[threading.Event] = None
        self._work_thread: Optional[threading.Thread] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._sd: Optional[object] = None

        self._status_item: Optional[object] = None
        self._toggle_menu_item: Optional[object] = None
        self._app: Optional[object] = None
        self._delegate: Optional[object] = None
        self._overlay: Optional[object] = None

    # -- State management ----------------------------------------------------

    def _set_state(self, state: State) -> None:
        with self._state_lock:
            self._state = state
        self._update_ui()

    def _get_state(self) -> State:
        with self._state_lock:
            return self._state

    def _update_ui(self) -> None:
        """Update the menu bar icon and menu label from any thread."""
        if self._status_item is None:
            return
        try:
            from AppKit import NSApplication
            from PyObjCTools import AppHelper

            state = self._get_state()
            title = _STATE_TITLES[state]
            label = _STATE_MENU_LABELS[state]

            def _do_update() -> None:
                self._status_item.setTitle_(title)
                if self._toggle_menu_item is not None:
                    self._toggle_menu_item.setTitle_(label)

            AppHelper.callAfter(_do_update)
        except Exception:
            pass
        # end _update_ui

    # -- Toggle logic --------------------------------------------------------

    def toggle(self) -> None:
        state = self._get_state()
        if state == State.IDLE:
            self._start_recording()
        elif state == State.RECORDING:
            self._stop_recording()

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
        """Background thread: record -> transcribe -> pipeline -> clipboard -> overlay."""
        try:
            from voice_transcriber.clipboard import copy_to_clipboard
            from voice_transcriber.models import ProcessingOptions
            from voice_transcriber.pipeline import process_transcript
            from voice_transcriber.recorder import import_sounddevice, record_audio
            from voice_transcriber.transcription import transcribe_audio

            if self._sd is None:
                self._sd = import_sounddevice()

            if self._overlay is not None:
                self._overlay.show_recording()

            def _on_level(level: float) -> None:
                if self._overlay is not None:
                    self._overlay.update_level(level)

            audio = record_audio(
                self._sd,
                stop_event=stop_event,
                interactive=False,
                on_level=_on_level,
            )

            if audio is None:
                self._set_state(State.IDLE)
                if self._overlay is not None:
                    self._overlay.dismiss()
                return

            self._set_state(State.TRANSCRIBING)
            if self._overlay is not None:
                self._overlay.show_transcribing()

            raw_text = transcribe_audio(
                audio,
                model_name=self._model,
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

            output = result.final_output if result.final_output else ""
            if output:
                copy_to_clipboard(output)

            self._set_state(State.IDLE)

            if self._overlay is not None:
                if output:
                    self._overlay.show_result(output)
                else:
                    self._overlay.show_result("(no speech detected)")

        except Exception as exc:
            self._set_state(State.IDLE)
            if self._overlay is not None:
                self._overlay.show_result(f"Error: {exc}")
            else:
                threading.Thread(
                    target=_notify,
                    args=("Voice Transcriber - Error", str(exc)),
                    daemon=True,
                ).start()
        # end _recording_worker

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

    # -- Global hotkey via Quartz CGEventTap ---------------------------------

    def _setup_global_hotkey(self) -> None:
        """Register Cmd+Shift+R as a global hotkey via CGEventTap.

        Requires Accessibility permission in System Settings.
        """
        try:
            import Quartz
            from AppKit import NSEvent

            _CMD_SHIFT_MASK = (
                Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift
            )
            _KEY_R = 15

            def _tap_callback(proxy: int, event_type: int, event: object, refcon: object) -> object:
                if event_type == Quartz.kCGEventKeyDown:
                    keycode = Quartz.CGEventGetIntegerValueField(
                        event, Quartz.kCGKeyboardEventKeycode,
                    )
                    flags = Quartz.CGEventGetFlags(event)
                    modifier_only = flags & (
                        Quartz.kCGEventFlagMaskCommand
                        | Quartz.kCGEventFlagMaskShift
                        | Quartz.kCGEventFlagMaskAlternate
                        | Quartz.kCGEventFlagMaskControl
                    )
                    if keycode == _KEY_R and modifier_only == _CMD_SHIFT_MASK:
                        threading.Thread(target=self.toggle, daemon=True).start()
                return event

            event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                event_mask,
                _tap_callback,
                None,
            )

            if tap is None:
                sys.stderr.write(
                    "WARNING: Could not create global hotkey (Cmd+Shift+R).\n"
                    "Grant Accessibility permission in:\n"
                    "  System Settings > Privacy & Security > Accessibility\n\n"
                )
                return

            run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(),
                run_loop_source,
                Quartz.kCFRunLoopDefaultMode,
            )
            Quartz.CGEventTapEnable(tap, True)

        except ImportError:
            sys.stderr.write(
                "WARNING: PyObjC Quartz framework not available. "
                "Global hotkey (Cmd+Shift+R) disabled.\n"
                "Install with: pip install pyobjc-framework-Quartz\n\n"
            )
        # end _setup_global_hotkey

    # -- Lifecycle -----------------------------------------------------------

    def run(self, model: str, language: str, domain_hint: str, custom_terms: list[str]) -> None:
        """Start the menubar daemon. Blocks until the user quits."""
        from AppKit import (
            NSApplication,
            NSMenu,
            NSMenuItem,
            NSStatusBar,
            NSVariableStatusItemLength,
        )
        from PyObjCTools import AppHelper

        from mac_overlay import Overlay

        self._model = model
        self._language = language
        self._domain_hint = domain_hint
        self._custom_terms = custom_terms
        self._running = True
        self._overlay = Overlay()

        _ensure_cache_dir()
        _PID_PATH.write_text(str(os.getpid()))

        self._app = NSApplication.sharedApplication()

        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(
            NSVariableStatusItemLength,
        )
        self._status_item.setTitle_(_STATE_TITLES[State.IDLE])
        self._status_item.setHighlightMode_(True)

        menu = NSMenu.new()

        self._toggle_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            _STATE_MENU_LABELS[State.IDLE],
            "toggleRecording:",
            "",
        )
        menu.addItem_(self._toggle_menu_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q",
        )
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)

        _register_toggle_action(self)

        self._start_socket_server()
        self._setup_global_hotkey()

        try:
            AppHelper.runEventLoop()
        finally:
            self._running = False
            if _PID_PATH.exists():
                _PID_PATH.unlink()
        # end run


# ---------------------------------------------------------------------------
# Objective-C delegate to handle menu actions
# ---------------------------------------------------------------------------

def _register_toggle_action(daemon: MacMenubarDaemon) -> None:
    """Register a Python-backed Obj-C selector for the toggle menu item."""
    import objc
    from Foundation import NSObject

    class ToggleDelegate(NSObject):
        def toggleRecording_(self, sender: object) -> None:
            threading.Thread(target=daemon.toggle, daemon=True).start()

    delegate = ToggleDelegate.alloc().init()
    daemon._toggle_menu_item.setTarget_(delegate)
    daemon._delegate = delegate
    # end _register_toggle_action


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def cmd_toggle() -> None:
    response = _send_command("toggle")
    if response is None:
        print("ERROR: voice-transcriber daemon is not running.", file=sys.stderr)
        print("Start it with: voice-transcriber-tray (macOS)", file=sys.stderr)
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
    parser = argparse.ArgumentParser(
        prog="voice-transcriber-tray",
        description="Voice transcriber macOS menubar daemon.",
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
        default=None,
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size. Overrides config default.",
    )
    parser.add_argument(
        "-l", "--language",
        default=None,
        help="Language code for transcription. Overrides config default.",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Force a domain hint (e.g. 'technical', 'general'). Overrides config.",
    )

    args = parser.parse_args()

    if args.command == "toggle":
        cmd_toggle()
    elif args.command == "status":
        cmd_status()
    else:
        from voice_transcriber.config import load_config

        config = load_config()
        model = args.model if args.model is not None else config.default_model
        language = args.language if args.language is not None else config.default_language
        domain_hint = args.domain if args.domain is not None else config.domain_hint

        daemon = MacMenubarDaemon()
        daemon.run(
            model=model,
            language=language,
            domain_hint=domain_hint,
            custom_terms=config.custom_terms,
        )
    # end main


if __name__ == "__main__":
    main()
