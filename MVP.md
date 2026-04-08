# MVP: Voice Transcriber

## Product

Press a shortcut, talk, stop — polished text is in your clipboard, ready to paste anywhere.

No GUI editor, no cloud APIs, no accounts. Local Whisper transcription with domain-aware
correction so the output is paste-ready.

## Core Experience

1. **Trigger** — user presses a system shortcut (Super+Shift+R on Linux, Cmd+Shift+R on Mac).
2. **Record** — mic opens, a visual indicator shows recording state (tray icon on Linux, menubar icon on Mac).
3. **Stop** — user presses the shortcut again.
4. **Process** — transcription runs locally via Whisper, domain correction is applied, text is polished.
5. **Done** — final text lands in the system clipboard. A brief notification confirms it.

The user pastes with Ctrl+V / Cmd+V wherever they want — email client, Slack, doc, terminal.

## Quality Bar

Output text must be **paste-ready**:

- Proper punctuation (periods, commas, question marks).
- Proper capitalization (sentence starts, proper nouns, acronyms).
- Natural sentence structure — not a raw dump of words.
- Domain-specific terms spelled correctly (AWS, Docker, PostgreSQL, TypeScript, etc.).

Whisper handles punctuation and capitalization well out of the box. The main gap is
domain-specific vocabulary, which the glossary correction layer addresses.

## Domain System

- **Auto-detect by default** — analyze transcript content for domain keywords, apply the matching glossary.
- **Manual override** — force a domain via config or CLI flag when auto-detect is not enough.
- **Built-in domains** — "technical" (software engineering glossary) and "general" (no corrections).
- **Custom terms** — user adds their own terms to the config file for jargon specific to their work.
- **Extensible later** — professional writing, medical, legal. MVP ships with "technical" and "general" only.

## Platforms

- **Linux** (Pop!_OS / Ubuntu / Debian) — tray daemon with system shortcut. Working.
- **macOS** — menubar daemon with Cmd+Shift+R global hotkey via PyObjC/CGEventTap. Working.
- **Windows** — CLI mode with native clipboard support. Tray mode not yet implemented.

Phone is **out of scope** for MVP.

## Install Experience

- **Linux:** `./install.sh` — installs deps, creates venv, registers shortcut, auto-start.
- **macOS:** `./install_mac.sh` — installs deps, creates venv, sets up menubar daemon, launchd auto-start.
- **Windows:** `install_windows.bat` — creates venv, installs deps, creates wrapper script.

## What MVP is NOT

- Not an email client or email composer.
- Not a GUI text editor or preview window.
- No cloud APIs, no accounts, no network calls.
- No AI rewriting or style matching (future feature).
- No phone app.
- No real-time streaming transcription (record-then-process is fine).

## Milestones

### M1: Wire the Pipeline — DONE

- Extracted shared audio recording into `voice_transcriber/recorder.py`.
- Extracted shared Whisper transcription into `voice_transcriber/transcription.py`.
- Connected the shared processing pipeline to both CLI and tray entry points.
- Simplified config to MVP fields: model, language, domain_hint, custom_terms.
- CLI flags override config values; config loads with safe defaults.
- Both `transcriber.py` (CLI) and `tray.py` (Linux tray) now use the same pipeline:
  raw Whisper output -> domain detection -> glossary correction -> text normalisation -> clipboard.

### M2: Domain Correction and Output Quality — DONE

- Tech glossary shipped with auto-detection (`voice_transcriber/domain.py`).
- Custom terms support via config file.
- Normalisation pass produces paste-ready output (capitalisation, punctuation, whitespace).
- Manual domain override via `--domain` CLI flag and `domain_hint` config key.
- Integration tests validate correction of common Whisper mishearings
  (docker/Docker, cooper netties/Kubernetes, aws lamda/AWS Lambda, etc.).

### M3: macOS First-Class Support — DONE

- `mac_menubar.py`: macOS menubar daemon using PyObjC NSStatusItem.
- Global Cmd+Shift+R hotkey via Quartz CGEventTap (requires Accessibility permission).
- Same shared pipeline as Linux — same quality, same corrections.
- macOS notifications via osascript.
- `./install_mac.sh` sets up everything: venv, deps, wrapper scripts, launchd auto-start.
- `voice-transcriber-tray` and `voice-transcriber-toggle` commands work on macOS.

### M4: Tests and Docs — DONE

- Unit tests for config loading and round-tripping (`tests/test_config.py`).
- Unit tests for pipeline processing (`tests/test_pipeline.py`).
- Integration tests for full pipeline with realistic Whisper output (`tests/test_integration.py`).
- 17 tests total, all passing.
- README updated with full macOS setup, testing instructions, domain correction docs,
  configuration reference, architecture overview, and troubleshooting for all platforms.
- MVP.md updated to reflect completed milestones.

### Windows support — PARTIAL

- CLI mode works: clipboard via native win32 API (ctypes), key detection via msvcrt.
- `install_windows.bat` installer script.
- Tray/shortcut mode not yet implemented (would need pystray or similar).

## Future (Post-MVP)

- AI-powered rewriting that learns the user's writing style.
- More domains (professional email tone, medical, legal).
- Phone companion app.
- Real-time streaming transcription.
- Windows tray/shortcut mode.
- Performance optimisation: faster-whisper or whisper.cpp as drop-in replacement.
