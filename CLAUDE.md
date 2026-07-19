# Voice Transcriber — Project Instruction File

## Purpose
Local voice transcription with OpenAI Whisper, domain-aware glossary correction, style learning, and memory. No cloud APIs. All data stays on-device.

## Architecture
```
microphone → recorder → whisper(transcribe) → domain(glossary) → style(formatter) → clipboard/output
                                    ↓
                               context.py (active domain hint)
                               memory.py (recency-weighted terms)
                               history.py (SQLite transcript log)
```

## Key Modules & Their Responsibilities
| Module | What it does |
|--------|--------------|
| `recorder.py` | Capture audio from mic via sounddevice |
| `transcription.py` | Load Whisper model, transcribe to text |
| `domain.py` | Detect domain, apply glossary corrections |
| `pipeline.py` | Orchestrate recorder → transcription → domain → style → clipboard |
| `context.py` | Read `~/.config/voice-transcriber/context.json` for active-project hints |
| `memory.py` | Recency-weighted boost based on transcript history |
| `history.py` | SQLite store of all transcripts + pending glossary candidates |
| `style.py` / `style_formatter.py` | User style profile: capitalization, contractions, fragments |
| `config.py` | `~/.config/voice-transcriber/config.json` round-trip persistence |

## Common Mistakes to Avoid
- NEVER run `pytest -x` during the nightly loop. The full report needs ALL failures, not just the first.
- `Parallel.ForEach` (or `multiprocessing.Pool` with Whisper) causes OOM on 8GB VRAM. Audio is processed sequentially.
- Glossary corrections MUST preserve case. "IServiceScopeFactory" not "iservicescopefactory".
- `custom_terms` in config.json are deduplicated on save but order matters for display.
- `style.json` lives outside git in `~/.config/voice-transcriber/`; it is machine-specific.

## Verification Rules
- After ANY change to `domain.py`, run: `.venv/bin/python -m pytest tests/test_domain_loader.py -v`
- After ANY change to `pipeline.py`, run: `.venv/bin/python -m pytest tests/test_pipeline.py tests/test_integration.py -v`
- Style changes require: `.venv/bin/python -m pytest tests/test_style.py -v`
- Full regression: `.venv/bin/python -m pytest -v` (86 tests, expect < 2s on RTX 4070)
- Lint check: `ruff check voice_transcriber/ tests/` (if ruff is installed)

## Context Minimalism
- When working on glossary generation, only load `history.py`, `observer.py`, `term_classifier.py`, `reviewer.py`
- When working on style, only load `style.py`, `style_formatter.py`, `style_corpus.py`
- When working on domain detection, only load `domain.py`, `context.py`, `memory.py`
- Don't load `daemon.py` or `tray.py` unless you're working on the system tray / menubar integration

## Nightly Loop (Automated)
- Script: `~/.hermes/scripts/vt-nightly-test.py`
- Schedule: 02:00 daily via Hermes cron
- Reports saved to: `~/.local/share/voice-transcriber/reports/`
- Latest report symlink: `~/.local/share/voice-transcriber/reports/latest.txt`
- On failure: the report contains git commit, failed test names, line numbers, likely source files, and full pytest output
- The loop NEVER commits or auto-fixes. It reports. You decide.

## How to run the loop manually
```bash
python3 ~/.hermes/scripts/vt-nightly-test.py
```

## Next-phase loop ideas (for future implementation)
- Glossary drift detector: scan last 7 days of transcripts for uncorrected technical terms, propose additions to `pending_terms`
- Style drift detector: compare recent transcript style against `style.json`, flag deviations
- Pre-commit hook: run `pytest -q` before any commit to `main`

## User Preferences
- Deterministic, inspectable systems over opaque AI magic
- Human approval for any destructive or state-changing action
- Prefer `--review` / `--learn-style` interactive CLI flows over silent automation
- The user documented real mishearings from voice testing on 2026-06-12; these are canonical glossary seed data
