# Deployment — GNOME Wayland

Systemd user services and GNOME integration for the voice transcriber.

## One-time setup

```bash
# 1. System dependencies (PyGObject build + audio + tray)
sudo apt install -y \
  gnome-shell-extension-appindicator \
  libgirepository1.0-dev libcairo2-dev pkg-config python3-dev gcc \
  libportaudio2

# 2. Venv dependencies (PyGObject must be <3.51 for Ubuntu 24.04,
#    NumPy must be <2.5 for numba/openai-whisper compat)
cd ~/Workspace/voice-transcriber-minial
uv pip install "PyGObject<3.51" "numpy<2.5" openai-whisper sounddevice

# 3. Run the setup script (installs services, toggle script, GNOME shortcut)
bash deploy/setup-gnome.sh
```

## What gets installed

| Component | Location | Purpose |
|-----------|----------|---------|
| `voice-transcriber-daemon.service` | `~/.config/systemd/user/` | Backend: Whisper + glossary + pipeline |
| `voice-transcriber-tray.service` | `~/.config/systemd/user/` | Frontend: GTK tray icon + recording toggle |
| `voice-transcriber-toggle` | `~/.local/bin/` | Wrapper script for keyboard shortcut |
| GNOME shortcut `Ctrl+Shift+T` | gsettings | Toggle recording from any app |

## Known issues on Ubuntu 24.04 / GNOME Wayland

- **PyGObject 3.56+** requires `girepository-2.0` which Ubuntu 24.04 doesn't ship. Must pin `PyGObject<3.51`.
- **NumPy 2.5** breaks `numba` (required by openai-whisper). Must pin `numpy<2.5`.
- **PYTHONNOUSERSITE=1** in both services prevents NumPy collision with other Python venvs on the system.
- **Tray icon** requires `gnome-shell-extension-appindicator` + GNOME restart (log out/in).