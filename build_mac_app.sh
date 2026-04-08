#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Build "Voice Transcriber.app" — a minimal macOS .app bundle that wraps
# mac_menubar.py so macOS treats it as its own application for Accessibility
# and Input Monitoring permissions (instead of inheriting from Terminal/Cursor).
#
# Called by install_mac.sh; can also be run standalone.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
APP_NAME="Voice Transcriber"
BUNDLE_ID="com.voice-transcriber.menubar"
APP_DIR="$PROJECT_DIR/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES"

# ── Info.plist ───────────────────────────────────────────────────────────────
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Voice Transcriber</string>
    <key>CFBundleDisplayName</key>
    <string>Voice Transcriber</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>voice-transcriber-launcher</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Voice Transcriber needs microphone access to record audio for transcription.</string>
</dict>
</plist>
PLIST

# ── Launcher script (the executable macOS runs) ─────────────────────────────
cat > "$MACOS_DIR/voice-transcriber-launcher" <<LAUNCHER
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$PROJECT_DIR/mac_menubar.py" "\$@"
LAUNCHER
chmod +x "$MACOS_DIR/voice-transcriber-launcher"

echo "[+] Built $APP_DIR"
