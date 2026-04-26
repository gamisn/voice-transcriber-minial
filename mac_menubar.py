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
import subprocess
import sys
import threading
from typing import Optional

from voice_transcriber.config import load_config
from voice_transcriber.daemon import (
    PID_PATH,
    DaemonCore,
    RecordingHooks,
    SocketServer,
    State,
    ensure_cache_dir,
    preload_model_async,
    send_command,
)
from voice_transcriber.errors import log_recording_failure


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
# Menubar daemon shell
# ---------------------------------------------------------------------------


class MacMenubarHooks(RecordingHooks):
    """Routes ``DaemonCore`` events to the macOS menu bar UI and overlay."""

    def __init__(self, daemon: "MacMenubarDaemon") -> None:
        self._daemon = daemon
        # end __init__

    def on_state_change(self, state: State) -> None:
        self._daemon._render_state(state)  # noqa: SLF001 — UI bridge
        overlay = self._daemon._overlay
        if overlay is None:
            return
        if state == State.RECORDING:
            overlay.show_recording()
        elif state == State.TRANSCRIBING:
            overlay.show_transcribing()
        # end on_state_change

    def on_level(self, normalized: float) -> None:
        if self._daemon._overlay is not None:
            self._daemon._overlay.update_level(normalized)
        # end on_level

    def on_result(self, final_text: str) -> None:
        if self._daemon._overlay is not None:
            self._daemon._overlay.show_result(final_text)
        # end on_result

    def on_empty(self) -> None:
        if self._daemon._overlay is not None:
            self._daemon._overlay.show_result("(no speech detected)")
        # end on_empty

    def on_error(self, summary: str) -> None:
        short_msg = f"{summary}\nSee ~/.cache/voice-transcriber/error.log for details."
        if self._daemon._overlay is not None:
            self._daemon._overlay.show_result(short_msg)
        else:
            threading.Thread(
                target=_notify,
                args=("Voice Transcriber - Error", short_msg),
                daemon=True,
            ).start()
        # end on_error


class MacMenubarDaemon:
    """macOS NSStatusItem shell around ``DaemonCore`` with global hotkey."""

    def __init__(self) -> None:
        self._core: Optional[DaemonCore] = None
        self._socket_server: Optional[SocketServer] = None

        self._status_item: Optional[object] = None
        self._toggle_menu_item: Optional[object] = None
        self._app: Optional[object] = None
        self._delegate: Optional[object] = None
        self._overlay: Optional[object] = None
        # end __init__

    def _toggle(self) -> None:
        if self._core is not None:
            self._core.toggle()
        # end _toggle

    def _render_state(self, state: State) -> None:
        """Update the menu bar icon and menu label from any thread."""
        if self._status_item is None:
            return
        try:
            from PyObjCTools import AppHelper
        except ImportError as exc:
            log_recording_failure("update_ui_import", exc)
            return

        title = _STATE_TITLES[state]
        label = _STATE_MENU_LABELS[state]

        def _do_update() -> None:
            self._status_item.setTitle_(title)
            if self._toggle_menu_item is not None:
                self._toggle_menu_item.setTitle_(label)

        AppHelper.callAfter(_do_update)
        # end _render_state

    # -- Global hotkey via Quartz CGEventTap ---------------------------------

    def _setup_global_hotkey(self) -> None:
        """Register Cmd+Shift+R as a global hotkey via CGEventTap.

        Requires Accessibility permission in System Settings.
        """
        try:
            import Quartz
        except ImportError:
            sys.stderr.write(
                "WARNING: PyObjC Quartz framework not available. "
                "Global hotkey (Cmd+Shift+R) disabled.\n"
                "Install with: pip install pyobjc-framework-Quartz\n\n"
            )
            return

        cmd_shift_mask = (
            Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift
        )
        key_r = 15

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
                if keycode == key_r and modifier_only == cmd_shift_mask:
                    threading.Thread(target=self._toggle, daemon=True).start()
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

        self._overlay = Overlay()

        ensure_cache_dir()
        PID_PATH.write_text(str(os.getpid()))

        hooks = MacMenubarHooks(self)
        self._core = DaemonCore(
            model_name=model,
            language=language,
            domain_hint=domain_hint,
            custom_terms=custom_terms,
            hooks=hooks,
        )

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

        self._socket_server = SocketServer(
            on_toggle=self._toggle,
            on_status=self._core.get_state,
        )
        self._socket_server.start()

        self._setup_global_hotkey()

        # Warm the Whisper model so the first hotkey press is instant.
        preload_model_async(model)

        # Show the recording overlay only when entering RECORDING state. The
        # initial state is IDLE so the overlay stays hidden until the first
        # toggle.
        try:
            AppHelper.runEventLoop()
        finally:
            if self._socket_server is not None:
                self._socket_server.stop()
            if PID_PATH.exists():
                PID_PATH.unlink()
        # end run


# ---------------------------------------------------------------------------
# Objective-C delegate to handle menu actions
# ---------------------------------------------------------------------------

def _register_toggle_action(daemon: MacMenubarDaemon) -> None:
    """Register a Python-backed Obj-C selector for the toggle menu item."""
    from Foundation import NSObject

    class ToggleDelegate(NSObject):
        def toggleRecording_(self, sender: object) -> None:
            threading.Thread(target=daemon._toggle, daemon=True).start()

    delegate = ToggleDelegate.alloc().init()
    daemon._toggle_menu_item.setTarget_(delegate)
    daemon._delegate = delegate
    # end _register_toggle_action


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def cmd_toggle() -> None:
    response = send_command("toggle")
    if response is None:
        print("ERROR: voice-transcriber daemon is not running.", file=sys.stderr)
        print("Start it with: voice-transcriber-tray (macOS)", file=sys.stderr)
        sys.exit(1)
    # end cmd_toggle


def cmd_status() -> None:
    response = send_command("status")
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
