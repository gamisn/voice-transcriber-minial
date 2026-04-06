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

- **Linux** (Pop!_OS / Ubuntu / Debian) — tray daemon with system shortcut. Already works.
- **macOS** — menubar presence or launchd-based shortcut handler so the shortcut works system-wide
  without an open terminal. The bare CLI-in-terminal approach is not MVP-quality.

Phone is **out of scope** for MVP.

## Install Experience

- **Linux:** `./install.sh` — installs deps, creates venv, registers shortcut.
- **macOS:** `./install_mac.sh` — installs deps, creates venv, sets up menubar/shortcut integration.

## What MVP is NOT

- Not an email client or email composer.
- Not a GUI text editor or preview window.
- No cloud APIs, no accounts, no network calls.
- No AI rewriting or style matching (future feature).
- No phone app.
- No real-time streaming transcription (record-then-process is fine).

## Milestones

### M1: Wire the Pipeline

- Connect the shared processing pipeline to both CLI and tray entry points.
- Simplify config to MVP fields: model, language, domain_hint, custom_terms.
- Keep current behavior intact (clipboard, notifications, shortcuts).

### M2: Domain Correction and Output Quality

- Ship the tech glossary with auto-detection.
- Add custom terms support via config.
- Add a normalization pass so output is truly paste-ready.
- Manual domain override via CLI flag and config.

### M3: macOS First-Class Support

- Menubar presence or launchd-based shortcut handler.
- System-wide shortcut that works without an open terminal.
- Same pipeline, same quality, clipboard output.
- `./install_mac.sh` sets everything up end to end.

### M4: Tests and Docs

- Unit tests for pipeline, config, domain, formatter.
- README update reflecting actual MVP features.
- Install docs for both platforms.

## Future (Post-MVP)

- AI-powered rewriting that learns the user's writing style.
- More domains (professional email tone, medical, legal).
- Phone companion app.
- Real-time streaming transcription.
