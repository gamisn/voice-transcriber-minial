# voice-transcriber

A minimal CLI tool that records your voice from the microphone and transcribes it locally using [OpenAI Whisper](https://github.com/openai/whisper). No cloud APIs, no data leaves your machine.

## Features

- **One-key recording** — press Enter, Space, or `q` to stop
- **Live level meter** — visual feedback while recording
- **100% offline** — Whisper runs locally, nothing is sent anywhere
- **Multiple model sizes** — from `tiny` (fast) to `large` (accurate)
- **Clipboard support** — pipe the result straight to your clipboard
- **Optional WAV export** — save the raw audio if needed

## Prerequisites

| Dependency   | Why                        | Install                                            |
| ------------ | -------------------------- | -------------------------------------------------- |
| Python ≥3.10 | Runtime                    | Usually pre-installed                              |
| PortAudio    | Audio I/O backend          | See below                                          |
| ffmpeg       | Whisper audio processing   | `sudo dnf install ffmpeg` / `sudo apt install ffmpeg` |

### Install PortAudio

```bash
# Fedora / Nobara
sudo dnf install portaudio-devel

# Ubuntu / Pop!_OS
sudo apt install libportaudio2 portaudio19-dev

# Arch
sudo pacman -S portaudio
```

## Installation

### With uv (recommended)

```bash
# Create a venv and install deps in one shot
uv venv .venv && source .venv/bin/activate
uv pip install openai-whisper sounddevice numpy
```

### With pip

```bash
python -m venv .venv && source .venv/bin/activate
pip install openai-whisper sounddevice numpy
```

### With Makefile

```bash
make install       # CPU
make install-gpu   # NVIDIA GPU (CUDA)
```

> **GPU users:** If you have an NVIDIA GPU, install the CUDA variant of PyTorch for significantly faster transcription. The `install-gpu` target handles this.

## Usage

```bash
# Basic — record and transcribe
python transcriber.py

# Use a larger model for better accuracy
python transcriber.py -m medium

# Copy result to clipboard
python transcriber.py --clipboard

# Save audio alongside transcription
python transcriber.py --save recording.wav

# List audio devices
python transcriber.py --list-devices

# Use a specific input device
python transcriber.py -d 3
```

### Workflow

1. Run the command — recording starts immediately
2. Speak into your microphone (watch the live level meter)
3. Press **Enter**, **Space**, or **q** to stop
4. Whisper loads and transcribes the audio
5. The transcription is printed to stdout

### Piping

The transcription goes to **stdout** while all UI/progress goes to **stderr**, so you can pipe cleanly:

```bash
# Save to file
python transcriber.py > note.txt

# Pipe to another command
python transcriber.py | xargs -I{} echo "You said: {}"

# Append to a log
python transcriber.py >> journal.txt
```

## Model Sizes

| Model    | Parameters | English Accuracy | Speed  | VRAM   |
| -------- | ---------- | ---------------- | ------ | ------ |
| `tiny`   | 39M        | Good             | Fast   | ~1 GB  |
| `base`   | 74M        | Better           | Fast   | ~1 GB  |
| `small`  | 244M       | Great            | Medium | ~2 GB  |
| `medium` | 769M       | Excellent        | Slow   | ~5 GB  |
| `large`  | 1550M      | Best             | Slow   | ~10 GB |

> For English-only use, `base` is a great default. Step up to `small` or `medium` if you need higher accuracy.

## Troubleshooting

**"PortAudio not found"**
Install the PortAudio development package for your distro (see Prerequisites).

**No audio captured / level meter stays flat**
Check that your microphone is the default input device, or specify it explicitly with `-d`.

```bash
python transcriber.py --list-devices   # find your mic's index
python transcriber.py -d <index>
```

**Slow transcription on CPU**
Use a smaller model (`-m tiny` or `-m base`) or install the CUDA version of PyTorch for GPU acceleration.

## License

MIT
