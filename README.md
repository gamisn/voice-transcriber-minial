# voice-transcriber

Record your voice and transcribe it locally using [OpenAI Whisper](https://github.com/openai/whisper). No cloud APIs, no data leaves your machine.

Transcriptions go through a domain-aware correction pipeline that fixes common Whisper mishearings of technical terms (Docker, Kubernetes, AWS Lambda, etc.), normalises formatting, and lands the result in your clipboard — paste-ready.

## Quick Start

**macOS:**

```bash
./install_mac.sh
```

**Linux (Pop!_OS / Ubuntu / Debian):**

```bash
./install.sh
```

**Windows:**

```bat
install_windows.bat
```

## macOS — Full Setup and Testing

### Install

Requires [Homebrew](https://brew.sh) and Python 3.10+.

```bash
./install_mac.sh
```

This installs:
- System deps (`portaudio`, `ffmpeg`) via Homebrew
- Python venv with `openai-whisper`, `sounddevice`, `numpy`, and PyObjC frameworks
- **Voice Transcriber.app** in `~/Applications` — a proper macOS `.app` bundle so it gets its own identity in System Settings (Accessibility, Microphone)
- Three commands in `~/.local/bin`: `voice-transcriber`, `voice-transcriber-tray`, `voice-transcriber-toggle`
- A launchd agent for auto-start on login

After install, **open a new terminal tab** (or `source ~/.zshrc`) so the PATH update takes effect.

### Accessibility permission (one-time)

The global hotkey (Cmd+Shift+R) uses a CGEventTap, which requires Accessibility permission. Because the daemon runs as a standalone `.app`, you grant permission to "Voice Transcriber" — not to your terminal.

1. Open **System Settings > Privacy & Security > Accessibility**
2. Click **+** and select **Voice Transcriber** from `~/Applications`
3. Restart the daemon

Without this, the hotkey won't work (but menu-click and `voice-transcriber-toggle` still do).

### Test 1: CLI mode

The simplest way to verify everything works:

```bash
voice-transcriber --clipboard
```

1. Speak into your microphone
2. Press **Enter** or **Space** to stop
3. The transcript is printed and copied to your clipboard
4. **Cmd+V** to paste anywhere

To test domain correction, say something technical like "deploy the docker container on AWS lambda":

```bash
voice-transcriber --clipboard --domain technical
```

You should see corrections like "Docker", "AWS Lambda" in the output, plus a line showing which terms were corrected.

Other CLI options:

```bash
voice-transcriber -m small --clipboard    # more accurate model
voice-transcriber --list-devices          # show available microphones
voice-transcriber -d 2 --clipboard        # use a specific mic by index
voice-transcriber --save test.wav         # save the audio too
```

### Test 2: Menubar daemon mode

Start the menubar daemon via the `.app` bundle (recommended):

```bash
open ~/Applications/Voice\ Transcriber.app
```

Or from the command line:

```bash
voice-transcriber-tray
```

A microphone emoji appears in your menu bar. Then:

1. Press **Cmd+Shift+R** — emoji changes to red circle (recording)
2. Speak
3. Press **Cmd+Shift+R** again — emoji changes to hourglass (transcribing)
4. A macOS notification appears with the transcribed text
5. Text is already in your clipboard — **Cmd+V** to paste
6. Emoji returns to microphone — ready for next recording

You can also click the menu bar item to toggle recording.

**Important:** The global hotkey requires Accessibility permission granted to the `.app` — see the [Accessibility permission](#accessibility-permission-one-time) section above.

If the hotkey does not work, you can still toggle via the socket:

```bash
voice-transcriber-toggle
```

### Test 3: Configuration

Create or edit `~/.config/voice-transcriber/config.json`:

```json
{
  "default_model": "small",
  "default_language": "en",
  "domain_hint": "auto",
  "custom_terms": ["MyCompany", "SpecialTool"]
}
```

Both CLI and menubar modes read this config at startup. CLI flags override config values.

### Uninstall (macOS)

```bash
rm ~/.local/bin/voice-transcriber ~/.local/bin/voice-transcriber-tray ~/.local/bin/voice-transcriber-toggle
launchctl unload ~/Library/LaunchAgents/com.voice-transcriber.menubar.plist
rm ~/Library/LaunchAgents/com.voice-transcriber.menubar.plist
rm -rf ~/Applications/Voice\ Transcriber.app
```

## Linux — Panel Icon Mode (recommended)

Start the daemon once — a microphone icon appears in your COSMIC / GNOME panel:

```bash
voice-transcriber-tray
```

Then use the keyboard shortcut from any app:

1. Press **Super+Shift+R** — icon turns **red** (recording)
2. Press **Super+Shift+R** again to stop
3. Icon turns **amber** — transcribing in the background
4. A desktop notification pops up with the transcribed text
5. Text is already in your clipboard — **Ctrl+V** to paste
6. Icon returns to **grey** — ready for next recording

You can also click the panel icon to toggle recording, or right-click for a menu with a Quit option.

The Linux installer handles everything automatically:

- Installs system packages (PortAudio, ffmpeg, notify-send, AppIndicator3) via `apt`
- Creates a Python venv and installs Whisper + dependencies
- Adds `voice-transcriber`, `voice-transcriber-tray`, and `voice-transcriber-toggle` to your PATH
- Registers a **Super+Shift+R** keyboard shortcut to toggle recording from any app
- Sets the panel icon daemon to auto-start on login

## Windows — CLI Mode

```bat
install_windows.bat
```

Prerequisites: Python 3.10+ and ffmpeg on PATH.

After install, from any terminal:

```bat
voice-transcriber --clipboard
```

Windows currently supports CLI mode only. Tray/shortcut support is planned.

## CLI Mode (all platforms)

```bash
voice-transcriber                         # record and transcribe to stdout
voice-transcriber --clipboard             # also copy to clipboard
voice-transcriber -m medium               # use a larger model
voice-transcriber --domain technical      # force technical domain correction
voice-transcriber --save recording.wav    # save audio alongside transcription
voice-transcriber --list-devices          # list available microphones
voice-transcriber -d <index>              # use a specific microphone
voice-transcriber > note.txt              # pipe to a file
```

## Domain Correction

The pipeline auto-detects technical dictation and corrects common Whisper mishearings:

| What you say | What Whisper hears | What you get |
|---|---|---|
| "Docker" | "doctor" | Docker |
| "Kubernetes" | "cooper netties" | Kubernetes |
| "AWS Lambda" | "aws lamda" | AWS Lambda |
| "TypeScript" | "type script" | TypeScript |
| "PostgreSQL" | "postgres" | PostgreSQL |

Auto-detection uses keyword analysis. Force a domain with `--domain technical` or set `domain_hint` in the config file.

Add your own terms in `~/.config/voice-transcriber/config.json`:

```json
{
  "custom_terms": ["MyCompanyAPI", "SpecialTool", "InternalService"]
}
```

## Configuration

Config file: `~/.config/voice-transcriber/config.json`

| Key | Type | Default | Description |
|---|---|---|---|
| `default_model` | string | `"base"` | Whisper model size |
| `default_language` | string | `"en"` | Language code |
| `domain_hint` | string | `"auto"` | Domain for glossary correction (`auto`, `technical`, `general`) |
| `custom_terms` | string[] | `[]` | Additional terms for glossary correction |

CLI flags always override config values. The config file is optional — sane defaults are used when it does not exist.

## Model Sizes

| Model    | Parameters | English Accuracy | Speed  | VRAM   |
| -------- | ---------- | ---------------- | ------ | ------ |
| `tiny`   | 39M        | Good             | Fast   | ~1 GB  |
| `base`   | 74M        | Better           | Fast   | ~1 GB  |
| `small`  | 244M       | Great            | Medium | ~2 GB  |
| `medium` | 769M       | Excellent        | Slow   | ~5 GB  |
| `large`  | 1550M      | Best             | Slow   | ~10 GB |

> `base` is a great default. Step up to `small` or `medium` for higher accuracy.

## GPU Acceleration

For significantly faster transcription on NVIDIA GPUs:

```bash
make install-gpu
```

## Commands Reference

| Command | What it does |
|---------|-------------|
| `voice-transcriber` | CLI mode — record, transcribe, print to stdout |
| `voice-transcriber-tray` | Start the panel/menubar daemon (Linux or macOS) |
| `voice-transcriber-toggle` | Toggle recording in the running daemon |
| `make run` | CLI mode from the project directory |
| `make tray` | Start Linux tray daemon (from project dir) |
| `make tray-mac` | Start macOS menubar daemon (from project dir) |
| `make test` | Run the test suite |

## Architecture

The codebase is structured as a shared Python package (`voice_transcriber/`) with thin entry points:

```
voice_transcriber/          Shared core
  recorder.py               Audio capture (sounddevice)
  transcription.py          Whisper model loading and transcription
  pipeline.py               Post-processing: domain detection -> glossary -> normalisation
  domain.py                 Domain detection and glossary correction
  formatter.py              Text normalisation
  config.py                 Config load/save (~/.config/voice-transcriber/config.json)
  clipboard.py              Cross-platform clipboard (Linux/macOS/Windows)
  models.py                 Data models

transcriber.py              CLI entry point (~130 lines)
tray.py                     Linux tray daemon — GTK/AppIndicator (~490 lines)
mac_menubar.py              macOS menubar daemon — PyObjC/NSStatusItem (~530 lines)
build_mac_app.sh            Builds Voice Transcriber.app bundle for macOS
```

All three entry points use the same pipeline. Adding a new platform means writing only the UI shell.

## Troubleshooting

**"PortAudio not found"**
Re-run the installer for your platform — it installs the required system packages.

**No audio captured / level meter stays flat**
Check that your microphone is the default input device, or specify it explicitly:

```bash
voice-transcriber --list-devices
voice-transcriber -d <index>
```

**Slow transcription on CPU**
Use a smaller model (`-m tiny` or `-m base`) or install GPU support with `make install-gpu`.

**macOS: global hotkey not working**
Grant Accessibility permission: System Settings > Privacy & Security > Accessibility. Click **+** and add **Voice Transcriber** from `~/Applications`. Do **not** add Cursor or Terminal — the `.app` bundle has its own identity.

**macOS: menubar daemon not starting on login**
Check the launchd agent: `launchctl list | grep voice-transcriber`. Re-run `./install_mac.sh` to reinstall the plist.

**Linux: keyboard shortcut not working**
Check it was registered: Settings > Keyboard > Custom Shortcuts. The command should be `voice-transcriber-toggle`.

**Linux: panel icon not appearing on login**
Check `~/.config/autostart/voice-transcriber.desktop` exists. You can also start it manually with `voice-transcriber-tray`.

**Linux: panel icon not visible (no AppIndicator support)**
Install the GIR package manually and restart the daemon:

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1
pkill -f tray.py
voice-transcriber-tray
```

## License

MIT
