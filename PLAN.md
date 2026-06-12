# Voice Transcriber — Personal Intelligence Plan

> **Goal:** Evolve the voice transcriber from a dumb pipe into a context-aware assistant that learns your vocabulary, remembers what you're working on, and writes like you.

---

## Philosophy

The transcriber should be **augmentation**, not **replacement**. You speak your own words with your own intent — the system cleans, corrects, and routes them. It gets smarter the more you use it because it is connected to your memory.

---

## Phase 1: Context Bridge ✅ COMPLETE
**Goal:** The transcriber learns what you're currently doing by reading local context.

- ✅ Create `voice_transcriber/context.py` — reads `~/.config/voice-transcriber/context.json`
- ✅ Extend `ProcessingOptions` with optional `context` field
- ✅ Modify `detect_domain` to bias toward active domains and recent terms
- ✅ Add `context_enabled` to config
- ✅ Create domain glossaries: `csharp.json`, `savadeck.json`, `hermes.json`
- ✅ Populate starter context with user's actual domains and terms
- ✅ All 53 tests passing

**Deliverable:** Transcriber correctly detects when you're in "C# mode" vs "decking planner mode".

---

## Phase 2: Dynamic Glossaries ✅ COMPLETE
**Goal:** Stop writing JSON by hand. The system observes your speech and generates glossaries automatically.

- ✅ Create `voice_transcriber/history.py` — SQLite transcript history + pending glossary entries
- ✅ Create `voice_transcriber/observer.py` — pipeline hook that logs and proposes terms
- ✅ Create `voice_transcriber/term_classifier.py` — heuristic alias extraction with similarity scoring
- ✅ Create `voice_transcriber/reviewer.py` — interactive CLI for approving/rejecting candidates
- ✅ Add `--review` flag to `transcriber.py`
- ✅ Modify `pipeline.py` to call observer after every transcription
- ✅ Modify `config.py` to add `auto_glossary` toggle
- ✅ All 66 tests passing

**Deliverable:** Auto-growing glossaries that learn your vocabulary.

---

## Phase 3: Memory Sync
**Goal:** The transcriber remembers what you said yesterday and uses it today.

- SQLite transcript history with timestamps, domains, corrections
- Recency bias in domain detection (last N transcripts or last H hours)
- Shared learning between desktop transcriber and Telegram voice messages

**Deliverable:** "Oh, you were talking about Docker an hour ago, so 'compose' means Docker Compose."

---

## Phase 4: Style Learning
**Goal:** The transcriber writes like *you*, not like generic AI.

- Style corpus builder that reads your emails, messages, and docs
- Generate a `style.json` profile: formality, sentence length, opener patterns
- Smart formatter that adapts normalization to destination (email vs chat vs code)
- Detect active window and apply appropriate style

**Deliverable:** Pasted text sounds like you typed it.

---

## Phase 5: Quick-Capture Modes
**Goal:** Dictate once, route to the right place automatically.

- Lightweight intent detection (regex/heuristic)
- Router module: email → Gmail, idea → Notion Ideas, task → Kanban, etc.
- Feedback loop: confirm route via notification, learn from corrections

**Deliverable:** "Remind me to call dentist tomorrow at 10" → appears in Google Calendar.

---

## Phase 6: Integration & Polish
**Goal:** Everything works together smoothly.

- Unified config with all new features
- Full test coverage for context, glossary generation, style, routing
- Documentation and architecture diagrams
- Performance baseline measurements

**Deliverable:** Complete, documented, tested system used daily.

---

## Total Timeline

| Phase | Days | Deliverable |
|-------|------|-------------|
| 1: Context Bridge | 2–3 | Topic-aware transcription |
| 2: Dynamic Glossaries | 3–4 | Auto-learning vocabulary |
| 3: Memory Sync | 2–3 | Recency bias, shared learning |
| 4: Style Learning | 3–4 | Output sounds like you |
| 5: Quick-Capture | 2–3 | Dictate → routed to right app |
| 6: Integration | 3–4 | Tested, documented, polished |

**Total: ~15–21 days.**

You can stop after any phase and have something usable.

---

## Architecture Overview (Target State)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Microphone  │────▶│   Whisper    │────▶│  Domain Filter  │◀──┐
│ (phone/PC)   │     │   (local)    │     │  (local cache)  │   │
└─────────────┘     └──────────────┘     └─────────────────┘   │
                                                    │            │
                              ┌─────────────────────┘            │
                              ▼                                  │
                    ┌──────────────────┐                         │
                    │  Style Normalizer  │◀─────────────────────┘
                    │   (lightweight)    │    (context: recent topics,
                    └──────────────────┘     active project, style profile)
                              │
                              ▼
                    ┌──────────────────┐
                    │ Intent Router    │ (optional)
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Clipboard / App  │
                    └──────────────────┘
```

---

## Design Principles

1. **Speed first.** Whisper stays local. Context queries must be < 50ms.
2. **Offline by default.** Basic transcription works without network.
3. **Deterministic where possible.** Domain correction is rule-based. AI polish is opt-in.
4. **User owns the data.** All learning happens on-device. Cloud is sync-only.
5. **Transparent.** You can review and edit everything the system learned about you.
