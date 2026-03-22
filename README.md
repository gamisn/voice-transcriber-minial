# voice-transcriber

Record your voice and transcribe it locally using [OpenAI Whisper](https://github.com/openai/whisper). No cloud APIs, no data leaves your machine.

## Quick Start

**Linux (Pop!_OS / Ubuntu / Debian):**

```bash
./install.sh
```

**macOS:**

```bash
./install_mac.sh
```

The Linux installer handles everything automatically:

- Installs system packages (PortAudio, ffmpeg, notify-send) via `apt`
- Creates a Python venv and installs Whisper + dependencies
- Adds `voice-transcriber`, `voice-transcriber-tray`, and `voice-transcriber-toggle` to your PATH
- Registers a **Super+Shift+R** keyboard shortcut to toggle recording from any app
- Sets the floating status window to auto-start on login

## Usage

### Floating window mode (recommended)

Start the status window once — then use the keyboard shortcut from anywhere:

```bash
voice-transcriber-tray
```

A small pill appears in the corner of your screen.

1. Press **Super+Shift+R** from any app
2. Pill turns **red** — recording
3. Press **Super+Shift+R** again to stop
4. Pill turns **amber** — transcribing
5. Notification pops up with the text
6. Text is in your clipboard — **Ctrl+V** to paste
7. Pill returns to **grey** — ready again

You can also click the pill to toggle recording.

### CLI mode

For terminal usage or scripting:

```bash
# Record and transcribe (prints to stdout)
voice-transcriber

# Use a larger model for better accuracy
voice-transcriber -m medium

# Copy result to clipboard
voice-transcriber --clipboard

# Save audio alongside transcription
voice-transcriber --save recording.wav

# Pipe to a file
voice-transcriber > note.txt
```

## Model Sizes

| Model    | Parameters | English Accuracy | Speed  | VRAM   |
| -------- | ---------- | ---------------- | ------ | ------ |
| `tiny`   | 39M        | Good             | Fast   | ~1 GB  |
| `base`   | 74M        | Better           | Fast   | ~1 GB  |
| `small`  | 244M       | Great            | Medium | ~2 GB  |
| `medium` | 769M       | Excellent        | Slow   | ~5 GB  |
| `large`  | 1550M      | Best             | Slow   | ~10 GB |

> `base` is a great default. Step up to `small` or `medium` for higher accuracy.

### Change the model for the floating window

```bash
voice-transcriber-tray -m small
```

## GPU Acceleration

For significantly faster transcription on NVIDIA GPUs:

```bash
make install-gpu
```

## Commands Reference

| Command | What it does |
|---------|-------------|
| `voice-transcriber` | CLI mode — record, transcribe, print to stdout |
| `voice-transcriber-tray` | Start the floating status window |
| `voice-transcriber-toggle` | Toggle recording in the running daemon |
| `make tray` | Same as `voice-transcriber-tray` (from project dir) |
| `make toggle` | Same as `voice-transcriber-toggle` (from project dir) |

## Troubleshooting

**"PortAudio not found"**
Re-run `./install.sh` — it installs the required system packages.

**No audio captured / level meter stays flat**
Check that your microphone is the default input device, or specify it explicitly:

```bash
voice-transcriber --list-devices
voice-transcriber -d <index>
```

**Slow transcription on CPU**
Use a smaller model (`-m tiny` or `-m base`) or install GPU support with `make install-gpu`.

**Keyboard shortcut not working**
Check it was registered: Settings → Keyboard → Custom Shortcuts. The command should be:

```
voice-transcriber-toggle
```

**Floating window not appearing on login**
Check `~/.config/autostart/voice-transcriber.desktop` exists. You can also start it manually with `voice-transcriber-tray`.

## macOS

On macOS the floating window is not available (no GTK). The CLI mode works identically, and the result is auto-copied to your clipboard via `pbcopy`.

### Install (macOS)

Requires [Homebrew](https://brew.sh):

```bash
./install_mac.sh
```

This installs `portaudio` and `ffmpeg` via Homebrew, creates a venv, and drops a `voice-transcriber` wrapper in `~/.local/bin`.

### Usage (macOS)

```bash
# Record, transcribe, and copy to clipboard in one shot
voice-transcriber --clipboard

# Use a more accurate model
voice-transcriber -m small --clipboard
```

Workflow:
1. Run `voice-transcriber --clipboard`
2. Speak
3. Press **Enter** or **Space** to stop
4. Result is printed and already in your clipboard — **Cmd+V** to paste

### Tip: bind a hotkey on macOS

Use **macOS Shortcuts** (or Alfred/Raycast) to create an action that runs:

```
/Users/YOUR_USER/.local/bin/voice-transcriber --clipboard
```

in a terminal window. That gives you a one-key workflow similar to the Linux tray mode.

## Uninstall

**Linux:**

```bash
rm ~/.local/bin/voice-transcriber ~/.local/bin/voice-transcriber-tray ~/.local/bin/voice-transcriber-toggle
rm ~/.config/autostart/voice-transcriber.desktop
```

**macOS:**

```bash
rm ~/.local/bin/voice-transcriber
```

## License

MIT
