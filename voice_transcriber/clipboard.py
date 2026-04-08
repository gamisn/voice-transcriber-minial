from __future__ import annotations

import platform
import subprocess


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard (Linux/macOS/Windows).

    On Windows, uses the win32 clipboard API directly.
    On Unix, tries platform clipboard tools in order. Uses Popen with
    DEVNULL to avoid blocking on wl-copy's forked background child.
    """
    if platform.system() == "Windows":
        return _copy_windows(text)
    return _copy_unix(text)
    # end copy_to_clipboard


def _copy_windows(text: str) -> bool:
    """Copy text via the Windows clipboard API (ctypes, no extra deps)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    CF_UNICODETEXT = 13

    if not user32.OpenClipboard(0):
        return False
    try:
        user32.EmptyClipboard()
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(0x0042, len(encoded))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return True
    finally:
        user32.CloseClipboard()
    # end _copy_windows


def _copy_unix(text: str) -> bool:
    """Copy text via command-line clipboard tools (Linux/macOS)."""
    data = text.encode()
    for cmd in (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],
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
    # end _copy_unix
