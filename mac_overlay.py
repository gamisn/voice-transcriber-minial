"""Always-on-top floating overlay for macOS voice transcriber.

Shows recording state with a live audio level meter, transcription progress,
and the final result — visible regardless of which app is focused.

All public functions schedule work on the main thread via AppHelper.callAfter
and are safe to call from any thread.
"""

from __future__ import annotations

import threading
from typing import Optional

from AppKit import (
    NSBackgroundStyleRaised,
    NSBezierPath,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSScreen,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskBorderless,
)
from AppKit import NSWindowCollectionBehaviorCanJoinAllSpaces as _JOIN_ALL_SPACES
from AppKit import NSWindowCollectionBehaviorStationary as _STATIONARY
from AppKit import NSFloatingWindowLevel
from PyObjCTools import AppHelper


_OVERLAY_WIDTH: float = 320.0
_OVERLAY_HEIGHT: float = 80.0
_RESULT_HEIGHT: float = 120.0
_CORNER_RADIUS: float = 14.0
_MARGIN_TOP: float = 48.0
_BAR_HEIGHT: float = 8.0
_DISMISS_DELAY_S: float = 3.0


# ---------------------------------------------------------------------------
# Level-bar custom view
# ---------------------------------------------------------------------------


class _LevelBarView(NSView):
    """Draws a horizontal audio level bar with rounded caps."""

    _level: float = 0.0

    def setLevel_(self, level: float) -> None:
        self._level = max(0.0, min(level, 1.0))
        self.setNeedsDisplay_(True)
    # end setLevel_

    def drawRect_(self, rect: object) -> None:
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height

        bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, h / 2.0, h / 2.0,
        )
        NSColor.colorWithCalibratedWhite_alpha_(0.3, 1.0).setFill()
        bg.fill()

        if self._level > 0.01:
            bar_w = max(h, w * self._level)
            bar_rect = NSMakeRect(0, 0, bar_w, h)
            bar = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bar_rect, h / 2.0, h / 2.0,
            )
            _level_color(self._level).setFill()
            bar.fill()
    # end drawRect_


def _level_color(level: float) -> NSColor:
    if level < 0.5:
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.2, 0.85, 0.4, 1.0,
        )
    if level < 0.8:
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 0.75, 0.0, 1.0,
        )
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        1.0, 0.3, 0.25, 1.0,
    )
# end _level_color


# ---------------------------------------------------------------------------
# Overlay controller
# ---------------------------------------------------------------------------


class Overlay:
    """Manages the floating overlay window lifecycle."""

    def __init__(self) -> None:
        self._window: Optional[NSWindow] = None
        self._label: Optional[NSTextField] = None
        self._level_bar: Optional[_LevelBarView] = None
        self._dismiss_timer: Optional[threading.Timer] = None
    # end __init__

    # -- public API (thread-safe, schedule on main thread) -------------------

    def show_recording(self) -> None:
        AppHelper.callAfter(self._do_show_recording)
    # end show_recording

    def update_level(self, level: float) -> None:
        AppHelper.callAfter(self._do_update_level, level)
    # end update_level

    def show_transcribing(self) -> None:
        AppHelper.callAfter(self._do_show_transcribing)
    # end show_transcribing

    def show_result(self, text: str) -> None:
        AppHelper.callAfter(self._do_show_result, text)
    # end show_result

    def dismiss(self) -> None:
        AppHelper.callAfter(self._do_dismiss)
    # end dismiss

    # -- internal (must run on main thread) ----------------------------------

    def _ensure_window(self, height: float) -> None:
        screen = NSScreen.mainScreen()
        if screen is None:
            return
        screen_frame = screen.frame()
        x = (screen_frame.size.width - _OVERLAY_WIDTH) / 2.0
        y = screen_frame.size.height - height - _MARGIN_TOP
        frame = NSMakeRect(x, y, _OVERLAY_WIDTH, height)

        if self._window is not None:
            self._window.setFrame_display_animate_(frame, True, True)
            return

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,
            2,  # NSBackingStoreBuffered
            False,
        )
        self._window.setLevel_(NSFloatingWindowLevel + 1)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(True)
        self._window.setIgnoresMouseEvents_(True)
        self._window.setCollectionBehavior_(_JOIN_ALL_SPACES | _STATIONARY)
    # end _ensure_window

    def _build_recording_content(self) -> NSView:
        container = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _OVERLAY_WIDTH, _OVERLAY_HEIGHT),
        )

        bg = _RoundedBackgroundView.alloc().initWithFrame_(container.bounds())
        container.addSubview_(bg)

        label = self._make_label("🔴  Recording...", 16.0)
        label.setFrame_(NSMakeRect(16, 30, _OVERLAY_WIDTH - 32, 30))
        container.addSubview_(label)
        self._label = label

        bar = _LevelBarView.alloc().initWithFrame_(
            NSMakeRect(16, 14, _OVERLAY_WIDTH - 32, _BAR_HEIGHT),
        )
        container.addSubview_(bar)
        self._level_bar = bar

        return container
    # end _build_recording_content

    def _build_text_content(self, title: str, body: str, height: float) -> NSView:
        container = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _OVERLAY_WIDTH, height),
        )

        bg = _RoundedBackgroundView.alloc().initWithFrame_(container.bounds())
        container.addSubview_(bg)

        title_label = self._make_label(title, 14.0)
        title_label.setFrame_(NSMakeRect(16, height - 36, _OVERLAY_WIDTH - 32, 24))
        container.addSubview_(title_label)

        body_label = self._make_label(body, 13.0)
        body_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.8, 1.0))
        body_label.setFrame_(NSMakeRect(16, 8, _OVERLAY_WIDTH - 32, height - 46))
        body_label.setMaximumNumberOfLines_(4)
        body_label.setLineBreakMode_(5)  # NSLineBreakByTruncatingTail
        container.addSubview_(body_label)
        self._label = title_label

        return container
    # end _build_text_content

    def _make_label(self, text: str, size: float) -> NSTextField:
        label = NSTextField.labelWithString_(text)
        label.setFont_(NSFont.systemFontOfSize_weight_(size, 0.5))
        label.setTextColor_(NSColor.whiteColor())
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        return label
    # end _make_label

    def _do_show_recording(self) -> None:
        self._cancel_dismiss_timer()
        self._ensure_window(_OVERLAY_HEIGHT)
        content = self._build_recording_content()
        self._window.setContentView_(content)
        self._window.orderFrontRegardless()
    # end _do_show_recording

    def _do_update_level(self, level: float) -> None:
        if self._level_bar is not None:
            self._level_bar.setLevel_(level)
    # end _do_update_level

    def _do_show_transcribing(self) -> None:
        self._cancel_dismiss_timer()
        if self._label is not None:
            self._label.setStringValue_("⏳  Transcribing...")
        if self._level_bar is not None:
            self._level_bar.setLevel_(0.0)
    # end _do_show_transcribing

    def _do_show_result(self, text: str) -> None:
        self._cancel_dismiss_timer()
        preview = text[:200] if text else "(empty)"
        self._ensure_window(_RESULT_HEIGHT)
        content = self._build_text_content("✅  Copied to clipboard", preview, _RESULT_HEIGHT)
        self._window.setContentView_(content)
        self._window.orderFrontRegardless()
        self._dismiss_timer = threading.Timer(_DISMISS_DELAY_S, self.dismiss)
        self._dismiss_timer.daemon = True
        self._dismiss_timer.start()
    # end _do_show_result

    def _do_dismiss(self) -> None:
        self._cancel_dismiss_timer()
        if self._window is not None:
            self._window.orderOut_(None)
        self._level_bar = None
        self._label = None
    # end _do_dismiss

    def _cancel_dismiss_timer(self) -> None:
        if self._dismiss_timer is not None:
            self._dismiss_timer.cancel()
            self._dismiss_timer = None
    # end _cancel_dismiss_timer


# ---------------------------------------------------------------------------
# Rounded background view
# ---------------------------------------------------------------------------


class _RoundedBackgroundView(NSView):
    """Draws the dark rounded-rect background for the overlay."""

    def drawRect_(self, rect: object) -> None:
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), _CORNER_RADIUS, _CORNER_RADIUS,
        )
        NSColor.colorWithCalibratedWhite_alpha_(0.1, 0.92).setFill()
        path.fill()
    # end drawRect_
