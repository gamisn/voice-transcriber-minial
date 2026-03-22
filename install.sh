#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# voice-transcriber installer
#
# Run once:   ./install.sh
# Then use:   voice-transcriber        (CLI mode)
#             voice-transcriber-tray    (floating window daemon)
#             voice-transcriber-toggle  (toggle recording from any app)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOCAL_BIN="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"
CACHE_DIR="$HOME/.cache/voice-transcriber"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[x]${NC} $*"; exit 1; }

# ── 1. System dependencies ──────────────────────────────────────────────────

info "Checking system dependencies..."

missing_pkgs=()
dpkg -s libportaudio2 &>/dev/null     || missing_pkgs+=(libportaudio2)
dpkg -s portaudio19-dev &>/dev/null   || missing_pkgs+=(portaudio19-dev)
dpkg -s ffmpeg &>/dev/null            || missing_pkgs+=(ffmpeg)
dpkg -s libnotify-bin &>/dev/null     || missing_pkgs+=(libnotify-bin)

if [ ${#missing_pkgs[@]} -gt 0 ]; then
    info "Installing system packages: ${missing_pkgs[*]}"
    if sudo apt-get install -y "${missing_pkgs[@]}"; then
        info "System packages installed."
    else
        warn "Could not install some system packages. Please run manually:"
        warn "  sudo apt-get install ${missing_pkgs[*]}"
    fi
else
    info "System dependencies already installed."
fi

# ── 2. Python venv + packages ───────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

info "Installing Python packages..."
if command -v uv &>/dev/null; then
    uv pip install --python "$VENV_DIR/bin/python" openai-whisper sounddevice numpy
else
    "$VENV_DIR/bin/python" -m ensurepip --upgrade 2>/dev/null || true
    "$VENV_DIR/bin/python" -m pip install --quiet openai-whisper sounddevice numpy
fi

# ── 3. Wrapper scripts in ~/.local/bin ──────────────────────────────────────

mkdir -p "$LOCAL_BIN"

info "Installing commands to $LOCAL_BIN ..."

# voice-transcriber  — CLI mode (runs in terminal)
cat > "$LOCAL_BIN/voice-transcriber" <<WRAPPER
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$PROJECT_DIR/transcriber.py" "\$@"
WRAPPER
chmod +x "$LOCAL_BIN/voice-transcriber"

# voice-transcriber-tray  — floating window daemon
cat > "$LOCAL_BIN/voice-transcriber-tray" <<WRAPPER
#!/usr/bin/env bash
exec /usr/bin/python3 "$PROJECT_DIR/tray.py" "\$@"
WRAPPER
chmod +x "$LOCAL_BIN/voice-transcriber-tray"

# voice-transcriber-toggle  — toggle recording in the running daemon
cat > "$LOCAL_BIN/voice-transcriber-toggle" <<WRAPPER
#!/usr/bin/env bash
exec /usr/bin/python3 "$PROJECT_DIR/tray.py" toggle
WRAPPER
chmod +x "$LOCAL_BIN/voice-transcriber-toggle"

# ── 4. Desktop file for autostart ───────────────────────────────────────────

mkdir -p "$AUTOSTART_DIR"
mkdir -p "$CACHE_DIR"

DESKTOP_FILE="$AUTOSTART_DIR/voice-transcriber.desktop"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Voice Transcriber
GenericName=Voice to Text
Comment=Record your voice and transcribe it locally with Whisper
Exec=/usr/bin/python3 $PROJECT_DIR/tray.py
Icon=audio-input-microphone
Terminal=false
StartupNotify=false
Categories=Utility;AudioVideo;
Keywords=transcribe;voice;speech;whisper;dictation;
X-GNOME-Autostart-enabled=true
DESKTOP

info "Autostart desktop file installed to $DESKTOP_FILE"

# ── 5. GNOME keyboard shortcut  (Super+Shift+R → toggle) ───────────────────

SHORTCUT_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-transcriber/"
SCHEMA_BASE="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
SCHEMA_LIST="org.gnome.settings-daemon.plugins.media-keys"

current_list=$(gsettings get "$SCHEMA_LIST" custom-keybindings 2>/dev/null || echo "@as []")

if echo "$current_list" | grep -q "voice-transcriber"; then
    info "Keyboard shortcut already registered."
else
    info "Adding keyboard shortcut: Super+Shift+R → toggle recording"

    gsettings set "$SCHEMA_BASE:$SHORTCUT_PATH" name "Voice Transcriber Toggle"
    gsettings set "$SCHEMA_BASE:$SHORTCUT_PATH" command "$LOCAL_BIN/voice-transcriber-toggle"
    gsettings set "$SCHEMA_BASE:$SHORTCUT_PATH" binding "<Super><Shift>r"

    # Append to the shortcut list
    if [ "$current_list" = "@as []" ] || [ "$current_list" = "[]" ]; then
        new_list="['$SHORTCUT_PATH']"
    else
        new_list="${current_list%]*}, '$SHORTCUT_PATH']"
    fi
    gsettings set "$SCHEMA_LIST" custom-keybindings "$new_list"
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
info "Installation complete!"
echo ""
echo "  Commands available (from anywhere):"
echo ""
echo "    voice-transcriber          CLI mode (terminal)"
echo "    voice-transcriber-tray     Start the floating status window"
echo "    voice-transcriber-toggle   Toggle recording (also bound to Super+Shift+R)"
echo ""
echo "  The floating window will auto-start on login."
echo "  To start it now:  voice-transcriber-tray"
echo ""
