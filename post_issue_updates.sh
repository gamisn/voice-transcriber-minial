#!/usr/bin/env bash
# Post status updates to all open GitHub issues.
# Run: gh auth login   (once, to authenticate)
# Then: ./post_issue_updates.sh
set -euo pipefail

REPO="gamisn/voice-transcriber-minial"

echo "Posting issue updates to $REPO..."

# --- Issue #1: Integrate pipeline into CLI and tray ---
gh issue comment 1 --repo "$REPO" --body "$(cat <<'EOF'
## Status: Done

The shared pipeline is now wired into both entry points.

### What changed

- Extracted audio recording into `voice_transcriber/recorder.py` (shared between CLI and tray).
- Extracted Whisper model loading and transcription into `voice_transcriber/transcription.py` with thread-safe model caching.
- **`transcriber.py`** (CLI) now uses the full pipeline: `record_audio()` → `transcribe_audio()` → `process_transcript()` → clipboard. Down from 437 lines to ~130 lines.
- **`tray.py`** (Linux tray) now delegates all recording/transcription/post-processing to the shared package. The GTK/AppIndicator UI stays in `tray.py`, everything else lives in `voice_transcriber/`.
- Config is loaded via `load_config()` at startup in both entry points. CLI flags (`--model`, `--language`, `--domain`) override config values.

### Pipeline flow (same in CLI and tray)

```
raw Whisper output → domain detection → glossary correction → text normalisation → clipboard
```

### Files touched

- `voice_transcriber/recorder.py` (new)
- `voice_transcriber/transcription.py` (new)
- `voice_transcriber/__init__.py` (updated exports)
- `transcriber.py` (rewritten as thin shell)
- `tray.py` (rewritten to delegate to shared package)

This also covers Issue #2 (persistent config) since both entry points now consume `load_config()`.
EOF
)"
echo "  ✓ Issue #1 commented"

# --- Issue #2: Persistent config ---
gh issue comment 2 --repo "$REPO" --body "$(cat <<'EOF'
## Status: Done

Config integration is complete. Both CLI and tray entry points load config at startup via `load_config()`.

### What's wired

- `transcriber.py` loads config and uses `default_model`, `default_language`, `domain_hint`, `custom_terms` as defaults.
- `tray.py` loads config at startup and passes all four fields through to the recording worker and pipeline.
- `mac_menubar.py` (new macOS daemon) also loads config the same way.
- CLI flags (`--model`, `--language`, `--domain`) override config values when provided.
- MVP config shape: `default_model`, `default_language`, `domain_hint`, `custom_terms` — matching the scope note.

### Config file

`~/.config/voice-transcriber/config.json`:
```json
{
  "default_model": "base",
  "default_language": "en",
  "domain_hint": "auto",
  "custom_terms": ["MyTerm"]
}
```

Safe defaults when file is missing or malformed — no crashes, no surprises.
EOF
)"
echo "  ✓ Issue #2 commented"

# --- Issue #3: Documentation ---
gh issue comment 3 --repo "$REPO" --body "$(cat <<'EOF'
## Status: Done

README and MVP.md have been updated to reflect the current shipped state.

### README changes

- Added full macOS setup and testing instructions (install, CLI test, menubar test, config test, uninstall).
- Added Windows section (CLI mode with install_windows.bat).
- Added domain correction documentation with a table of common corrections.
- Added configuration reference table (all config keys, types, defaults).
- Added architecture overview showing the shared package structure.
- Updated commands reference to include macOS-specific commands.
- Updated troubleshooting for all three platforms (macOS hotkey permissions, Linux panel, etc.).
- Removed the old "macOS is CLI-only" section — replaced with full menubar daemon docs.

### MVP.md changes

- Updated all four milestones (M1–M4) with "DONE" status and specifics of what shipped.
- Added Windows partial status.
- Updated platform section to reflect macOS menubar support.
EOF
)"
echo "  ✓ Issue #3 commented"

# --- Issue #4: Unit test coverage ---
gh issue comment 4 --repo "$REPO" --body "$(cat <<'EOF'
## Status: Done

17 tests total, all passing.

### Test breakdown

- `tests/test_config.py` (4 tests): Config save/load round-trip, defaults on missing file, defaults on malformed JSON, custom terms deduplication.
- `tests/test_pipeline.py` (6 tests): Technical term correction, general domain passthrough, manual domain hint override, custom terms, empty transcript warning, output normalisation.
- `tests/test_integration.py` (7 tests, new): Full pipeline integration with realistic Whisper output — technical paste-ready output, general non-overcorrection, config-driven options, custom terms with glossary, common mishearing corrections (Docker, Kubernetes, TypeScript, SQL, Terraform), empty/whitespace transcripts, domain override via CLI flag.

### Scope per MVP note

- ✅ Config save/load round-trip tests
- ✅ Custom term normalisation tests
- ✅ Technical glossary correction tests
- ✅ Pipeline end-to-end tests (domain detection → glossary → normalisation)
- ✅ Email formatting tests dropped (email mode removed from MVP)

All tests run without audio hardware or model downloads.
EOF
)"
echo "  ✓ Issue #4 commented"

# --- Issue #6: Domain glossary correction ---
gh issue comment 6 --repo "$REPO" --body "$(cat <<'EOF'
## Status: Done

Domain correction is shipped and wired into the live pipeline.

### What works

- **Auto-detection**: Analyses transcript tokens against a keyword set (aws, docker, kubernetes, deploy, etc.). Assigns "technical" domain with confidence based on keyword density.
- **Glossary correction**: 16 tech glossary entries covering common Whisper mishearings:
  - "doctor" → Docker, "cooper netties" → Kubernetes, "aws lamda" → AWS Lambda
  - "type script" → TypeScript, "sequel" → SQL, "terra form" → Terraform, etc.
- **Custom terms**: User-supplied terms from config participate in correction alongside the built-in glossary.
- **Manual override**: `--domain technical` CLI flag or `domain_hint: "technical"` in config forces the domain.
- **Safe fallback**: General dictation gets no corrections — the "general" domain is a no-op.

### Integration

The glossary runs as part of the shared pipeline in `voice_transcriber/pipeline.py`. Both CLI and tray (Linux + macOS) go through the same path. The output includes which terms were corrected:

```
Domain: technical | Corrections: Docker, AWS Lambda, PostgreSQL
```

Validated with 7 integration tests covering realistic Whisper output scenarios.
EOF
)"
echo "  ✓ Issue #6 commented"

# --- Issue #7: macOS first-class support ---
gh issue comment 7 --repo "$REPO" --body "$(cat <<'EOF'
## Status: Done

macOS now has a full menubar daemon with a global keyboard shortcut.

### Implementation

- **`mac_menubar.py`**: New macOS menubar daemon (~470 lines) using PyObjC.
- **NSStatusItem**: Menubar icon showing idle (🎙), recording (🔴), and transcribing (⏳) states.
- **CGEventTap**: Global Cmd+Shift+R hotkey via Quartz CGEventTap (listen-only, per @m13v's recommendation). Requires Accessibility permission.
- **Same pipeline**: Uses the shared `voice_transcriber/` package — same domain detection, glossary correction, normalisation, and clipboard handling as Linux.
- **Notifications**: macOS notifications via osascript.
- **Socket protocol**: Same Unix socket protocol as Linux tray — `voice-transcriber-toggle` and `voice-transcriber-tray status` work on macOS.

### Install

`./install_mac.sh` now handles the full setup:
- Installs PyObjC frameworks (pyobjc-framework-Quartz, pyobjc-framework-Cocoa)
- Creates `voice-transcriber-tray` and `voice-transcriber-toggle` wrapper scripts
- Installs a launchd plist for auto-start on login

### Per @m13v's feedback

- Used PyObjC + NSStatusItem instead of rumps (rumps doesn't support global shortcuts).
- Used CGEventTap (not deprecated Carbon API) for the global hotkey.
- Emoji-based status icons (avoids dark mode colour issues with custom icon rendering).

### What still needs testing

- Real-world Accessibility permission flow on a clean Mac.
- launchd auto-start on login.
- Interaction with other apps that might claim Cmd+Shift+R.
EOF
)"
echo "  ✓ Issue #7 commented"

echo ""
echo "All issue updates posted."
