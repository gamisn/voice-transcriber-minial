from __future__ import annotations

import subprocess


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard (Linux/macOS).

    Tries platform clipboard tools in order. Uses Popen with DEVNULL
    to avoid blocking on wl-copy's forked background child.
    """
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
    # end copy_to_clipboard
