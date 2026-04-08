#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# voice-transcriber macOS installer
#
# Run once:   ./install_mac.sh
# Then use:   voice-transcriber             (CLI mode — record and transcribe)
#             voice-transcriber --clipboard  (auto-copy result to clipboard)
#             voice-transcriber-tray         (menubar daemon with Cmd+Shift+R)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOCAL_BIN="$HOME/.local/bin"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_NAME="com.voice-transcriber.menubar.plist"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[x]${NC} $*"; exit 1; }

# ── 1. Homebrew ──────────────────────────────────────────────────────────────

if ! command -v brew &>/dev/null; then
    fail "Homebrew is not installed. Install it first: https://brew.sh"
fi

info "Checking system dependencies (Homebrew)..."

brew_install() {
    if brew list "$1" &>/dev/null; then
        info "$1 already installed."
    else
        info "Installing $1..."
        brew install "$1"
    fi
}

brew_install portaudio
brew_install ffmpeg

# ── 2. Python (native arm64 required) ────────────────────────────────────────
#
# On Apple-Silicon Macs the interpreter MUST be a native arm64 binary,
# otherwise uv/pip will look for x86_64 wheels that don't exist for
# torch + Python ≥ 3.13.  We search Homebrew pythons first (3.13 → 3.12 → 3.11 → 3.10),
# then fall back to whatever "python3" is on PATH.

PYTHON=""
MACHINE="$(uname -m)"

find_homebrew_python() {
    for minor in 13 12 11 10; do
        local candidate="/opt/homebrew/bin/python3.${minor}"
        if [ -x "$candidate" ]; then
            if [ "$MACHINE" = "arm64" ]; then
                local arch
                arch="$(file -b "$candidate" 2>/dev/null)"
                case "$arch" in
                    *arm64*) PYTHON="$candidate"; return 0 ;;
                esac
            else
                PYTHON="$candidate"; return 0
            fi
        fi
    done
    return 1
}

if ! find_homebrew_python; then
    PYTHON="$(command -v python3 || true)"
fi

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    fail "No suitable Python found. Install one with: brew install python@3.13"
fi

if [ "$MACHINE" = "arm64" ]; then
    PY_ARCH="$(file -b "$PYTHON" 2>/dev/null)"
    case "$PY_ARCH" in
        *x86_64*|*i386*)
            warn "Python at $PYTHON is x86_64 (Rosetta) — torch has no x86_64 wheels for Python ≥ 3.13."
            fail "Install a native arm64 Python: brew install python@3.13"
            ;;
    esac
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Using Python $PY_VERSION at $PYTHON ($(uname -m))"

if [[ "$PY_VERSION" < "3.10" ]]; then
    fail "Python 3.10 or newer is required. Install it with: brew install python@3.13"
fi

# ── 3. Python venv + packages ────────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

info "Installing Python packages (this may take a few minutes the first time)..."
if command -v uv &>/dev/null; then
    uv pip install --python "$VENV_DIR/bin/python" "openai-whisper>=20250625" sounddevice numpy pyobjc-framework-Quartz pyobjc-framework-Cocoa
else
    "$VENV_DIR/bin/python" -m ensurepip --upgrade 2>/dev/null || true
    "$VENV_DIR/bin/python" -m pip install --quiet "openai-whisper>=20250625" sounddevice numpy pyobjc-framework-Quartz pyobjc-framework-Cocoa
fi

# ── 4. Build macOS .app bundle ──────────────────────────────────────────────
#
# The .app gives the daemon its own identity in System Settings > Accessibility
# so the user grants permission to "Voice Transcriber", not to Terminal/Cursor.

APP_NAME="Voice Transcriber"
APP_INSTALL_DIR="$HOME/Applications"
APP_SRC="$PROJECT_DIR/$APP_NAME.app"
APP_DST="$APP_INSTALL_DIR/$APP_NAME.app"

info "Building $APP_NAME.app ..."
VENV_DIR="$VENV_DIR" bash "$PROJECT_DIR/build_mac_app.sh"

mkdir -p "$APP_INSTALL_DIR"
rm -rf "$APP_DST"
cp -R "$APP_SRC" "$APP_DST"
info "Installed $APP_NAME.app to $APP_INSTALL_DIR"

# ── 5. Wrapper scripts in ~/.local/bin ───────────────────────────────────────

mkdir -p "$LOCAL_BIN"

info "Installing 'voice-transcriber' command to $LOCAL_BIN ..."

cat > "$LOCAL_BIN/voice-transcriber" <<WRAPPER
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$PROJECT_DIR/transcriber.py" "\$@"
WRAPPER
chmod +x "$LOCAL_BIN/voice-transcriber"

info "Installing 'voice-transcriber-tray' command to $LOCAL_BIN ..."

cat > "$LOCAL_BIN/voice-transcriber-tray" <<WRAPPER
#!/usr/bin/env bash
exec "$(echo "$APP_DST/Contents/MacOS/voice-transcriber-launcher")" "\$@"
WRAPPER
chmod +x "$LOCAL_BIN/voice-transcriber-tray"

info "Installing 'voice-transcriber-toggle' command to $LOCAL_BIN ..."

cat > "$LOCAL_BIN/voice-transcriber-toggle" <<WRAPPER
#!/usr/bin/env bash
exec "$(echo "$APP_DST/Contents/MacOS/voice-transcriber-launcher")" toggle "\$@"
WRAPPER
chmod +x "$LOCAL_BIN/voice-transcriber-toggle"

# ── 6. Ensure ~/.local/bin is on PATH ────────────────────────────────────────

for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
    if [ -f "$rc" ] && ! grep -q '/.local/bin' "$rc" 2>/dev/null; then
        echo '' >> "$rc"
        echo '# Added by voice-transcriber install_mac.sh' >> "$rc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
        info "Added ~/.local/bin to PATH in $rc"
        break
    fi
done

# ── 7. launchd plist for auto-start on login ────────────────────────────────
#
# Launches the .app via open(1) so macOS attributes Accessibility permissions
# to "Voice Transcriber" rather than the raw Python binary.

mkdir -p "$PLIST_DIR"

cat > "$PLIST_DIR/$PLIST_NAME" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voice-transcriber.menubar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$APP_DST</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/.cache/voice-transcriber/menubar-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.cache/voice-transcriber/menubar-stderr.log</string>
</dict>
</plist>
PLIST

info "LaunchAgent installed at $PLIST_DIR/$PLIST_NAME"
info "The menubar daemon will auto-start on login."

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
info "Installation complete!"
echo ""
echo "  Reload your shell first (or open a new terminal tab), then:"
echo ""
echo "  CLI mode:"
echo "    voice-transcriber              Record and transcribe to stdout"
echo "    voice-transcriber --clipboard  Transcribe and copy to clipboard"
echo "    voice-transcriber -m small     Use a more accurate Whisper model"
echo ""
echo "  Menubar mode (recommended — start the .app):"
echo "    open '$APP_DST'               Start via the .app bundle"
echo "    voice-transcriber-tray         Start via the command line"
echo "    voice-transcriber-toggle       Toggle recording (for hotkey binding)"
echo ""
echo "  The menubar daemon (Cmd+Shift+R hotkey) will auto-start on login."
echo ""
echo "  ── Accessibility permission (one-time) ──"
echo ""
echo "    1. Open: System Settings > Privacy & Security > Accessibility"
echo "    2. Click + and add '$APP_DST'"
echo "       (or add 'Voice Transcriber' from ~/Applications)"
echo "    3. Restart the daemon: voice-transcriber-tray"
echo ""
