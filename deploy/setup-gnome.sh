#!/bin/bash
# Voice Transcriber — GNOME Wayland deployment script
# Installs systemd user services, toggle script, and GNOME keyboard shortcut.
#
# Usage:
#   bash deploy/setup-gnome.sh
#
# Prerequisites (apt):
#   sudo apt install -y \
#     gnome-shell-extension-appindicator \
#     libgirepository1.0-dev libcairo2-dev pkg-config python3-dev gcc \
#     libportaudio2
#
# Then in the project venv:
#   uv pip install "PyGObject<3.51" "numpy<2.5" openai-whisper sounddevice
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
LOCAL_BIN_DIR="$HOME/.local/bin"

echo "=== Voice Transcriber — GNOME Wayland Setup ==="
echo "Project: $PROJECT_DIR"
echo ""

# 1. Install systemd user services
echo "[1/4] Installing systemd user services..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$PROJECT_DIR/deploy/voice-transcriber-daemon.service" "$SYSTEMD_USER_DIR/"
cp "$PROJECT_DIR/deploy/voice-transcriber-tray.service" "$SYSTEMD_USER_DIR/"
# Expand %h in service files to actual home path
sed -i "s|%h|$HOME|g" "$SYSTEMD_USER_DIR/voice-transcriber-daemon.service"
sed -i "s|%h|$HOME|g" "$SYSTEMD_USER_DIR/voice-transcriber-tray.service"
systemctl --user daemon-reload
echo "  ✓ Services installed"

# 2. Install toggle script
echo "[2/4] Installing toggle script..."
mkdir -p "$LOCAL_BIN_DIR"
cp "$PROJECT_DIR/deploy/voice-transcriber-toggle" "$LOCAL_BIN_DIR/voice-transcriber-toggle"
chmod +x "$LOCAL_BIN_DIR/voice-transcriber-toggle"
echo "  ✓ Toggle script at $LOCAL_BIN_DIR/voice-transcriber-toggle"

# 3. Enable and start services
echo "[3/4] Starting services..."
systemctl --user enable --now voice-transcriber-daemon.service
systemctl --user enable --now voice-transcriber-tray.service
echo "  ✓ Daemon and tray running"

# 4. Set up GNOME keyboard shortcut (Ctrl+Shift+T)
echo "[4/4] Configuring GNOME shortcut (Ctrl+Shift+T)..."
CUSTOM_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['$CUSTOM_PATH']"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CUSTOM_PATH name "Voice Transcriber Toggle"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CUSTOM_PATH command "$LOCAL_BIN_DIR/voice-transcriber-toggle"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CUSTOM_PATH binding "<Shift><Control>t"
echo "  ✓ Shortcut: Ctrl+Shift+T"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Services:"
echo "  systemctl --user status voice-transcriber-daemon"
echo "  systemctl --user status voice-transcriber-tray"
echo ""
echo "Usage:"
echo "  Ctrl+Shift+T  — toggle recording"
echo "  Click tray icon — toggle recording"
echo ""
echo "Note: If the tray icon doesn't appear, log out and back in"
echo "      (GNOME needs to reload the AppIndicator extension)."