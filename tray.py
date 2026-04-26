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

import argparse
import os
import pathlib
import signal
import subprocess
import sys
import threading
from typing import Callable, Optional


def _ensure_venv_imports_on_path() -> None:
    """Prepend the project venv's site-packages so the shared package is
    importable when ``tray.py`` is invoked under system python3."""
    here = pathlib.Path(__file__).parent
    venv_lib = here / ".venv" / "lib"
    if venv_lib.exists():
        for pydir in venv_lib.iterdir():
            site = pydir / "site-packages"
            if site.exists() and str(site) not in sys.path:
                sys.path.insert(0, str(site))
                break
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    # end _ensure_venv_imports_on_path


_ensure_venv_imports_on_path()

from voice_transcriber.config import load_config
from voice_transcriber.daemon import (
    CACHE_DIR,
    PID_PATH,
    DaemonCore,
    RecordingHooks,
    SocketServer,
    State,
    ensure_cache_dir,
    preload_model_async,
    send_command,
)


# ---------------------------------------------------------------------------
# Runtime paths (icons live alongside the shared cache dir)
# ---------------------------------------------------------------------------

_ICON_DIR = CACHE_DIR / "icons"


# ---------------------------------------------------------------------------
# State -> UI mapping
# ---------------------------------------------------------------------------

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

    def __init__(self, Gtk: object, Gdk: object, GLib: object) -> None:
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

    def __init__(self, on_toggle_callback: Callable[[], None]) -> None:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import Gtk, Gdk, GLib, AyatanaAppIndicator3

        self._Gtk = Gtk
        self._GLib = GLib
        self._on_toggle = on_toggle_callback

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

        GLib.timeout_add(150, self._poll_and_render)

    def _on_quit(self, *_args: object) -> None:
        self._overlay.hide()
        self._Gtk.main_quit()

    def _poll_and_render(self) -> bool:
        """Called every 150ms on the GTK main thread."""
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

        return True

    def set_state(self, state: State) -> None:
        self._desired_state = state
        self._level_text = None

    def set_level(self, normalised: float) -> None:
        filled = min(int(normalised * _METER_WIDTH), _METER_WIDTH)
        bar = "|" * filled + "." * (_METER_WIDTH - filled)
        self._level_text = f"Rec [{bar}]"

    def hide_overlay(self) -> None:
        """Force the recording overlay off-screen (used after an error)."""
        try:
            self._GLib.idle_add(self._overlay.hide)
        except AttributeError:
            self._overlay.hide()
    # end PanelIndicator


# ---------------------------------------------------------------------------
# Tray daemon shell
# ---------------------------------------------------------------------------


class TrayHooks(RecordingHooks):
    """Routes ``DaemonCore`` events to the panel indicator and notifications."""

    def __init__(self, indicator_getter: Callable[[], Optional[PanelIndicator]]) -> None:
        self._indicator_getter = indicator_getter
        # end __init__

    def on_state_change(self, state: State) -> None:
        indicator = self._indicator_getter()
        if indicator is not None:
            indicator.set_state(state)
        # end on_state_change

    def on_level(self, normalized: float) -> None:
        indicator = self._indicator_getter()
        if indicator is not None:
            indicator.set_level(normalized)
        # end on_level

    def on_result(self, final_text: str) -> None:
        threading.Thread(
            target=_notify,
            args=("Voice Transcriber", final_text),
            daemon=True,
        ).start()
        # end on_result

    def on_empty(self) -> None:
        threading.Thread(
            target=_notify,
            args=("Voice Transcriber", "Transcription was empty."),
            daemon=True,
        ).start()
        # end on_empty

    def on_error(self, summary: str) -> None:
        indicator = self._indicator_getter()
        if indicator is not None:
            indicator.hide_overlay()
        threading.Thread(
            target=_notify,
            args=(
                "Voice Transcriber - Error",
                f"{summary}\nSee ~/.cache/voice-transcriber/error.log for details.",
            ),
            daemon=True,
        ).start()
        # end on_error


class TrayDaemon:
    """GTK shell around ``DaemonCore``. Owns only the panel indicator + GTK loop."""

    def __init__(self) -> None:
        self._indicator: Optional[PanelIndicator] = None
        self._core: Optional[DaemonCore] = None
        self._socket_server: Optional[SocketServer] = None
        # end __init__

    def _toggle(self) -> None:
        if self._core is not None:
            self._core.toggle()
        # end _toggle

    def _setup_signal_handler(self) -> None:
        def _handler(signum: int, frame: object) -> None:
            threading.Thread(target=self._toggle, daemon=True).start()
        try:
            signal.signal(signal.SIGUSR1, _handler)
        except (OSError, ValueError):
            pass
        # end _setup_signal_handler

    def run(self, model: str, language: str, domain_hint: str, custom_terms: list[str]) -> None:
        """Start the daemon. Blocks until the user quits."""
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        ensure_cache_dir()
        PID_PATH.write_text(str(os.getpid()))

        hooks = TrayHooks(indicator_getter=lambda: self._indicator)
        self._core = DaemonCore(
            model_name=model,
            language=language,
            domain_hint=domain_hint,
            custom_terms=custom_terms,
            hooks=hooks,
        )

        self._setup_signal_handler()

        self._socket_server = SocketServer(
            on_toggle=self._toggle,
            on_status=self._core.get_state,
        )
        self._socket_server.start()

        # Warm the Whisper model so the first hotkey press is instant.
        preload_model_async(model)

        self._indicator = PanelIndicator(on_toggle_callback=self._toggle)

        try:
            Gtk.main()
        finally:
            if self._socket_server is not None:
                self._socket_server.stop()
            if PID_PATH.exists():
                PID_PATH.unlink()
        # end run


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def cmd_toggle() -> None:
    response = send_command("toggle")
    if response is None:
        print("ERROR: voice-transcriber daemon is not running.", file=sys.stderr)
        print("Start it with: voice-transcriber-tray", file=sys.stderr)
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

        daemon = TrayDaemon()
        daemon.run(
            model=model,
            language=language,
            domain_hint=domain_hint,
            custom_terms=config.custom_terms,
        )
    # end main


if __name__ == "__main__":
    main()
