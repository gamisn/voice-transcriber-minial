"""Context query module for the voice transcriber.

Provides a lightweight bridge between the transcriber and the user's
world state (projects, recent topics, active learning focus).

Right now this reads from a local JSON file at
``~/.config/voice-transcriber/context.json``.

In the future it may query Hermes/Honcho directly via HTTP or a
local socket, but the interface must stay fast (< 50 ms) so the
transcription loop does not slow down.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Optional


_CONFIG_DIR: pathlib.Path = pathlib.Path.home() / ".config" / "voice-transcriber"
_CONTEXT_PATH: pathlib.Path = _CONFIG_DIR / "context.json"


@dataclass(slots=True)
class UserContext:
    """Lightweight snapshot of what the user is currently doing.

    All fields are optional and safe to omit. The transcriber falls
    back to pure transcript analysis when no context is available.
    """

    # Ordered list of active domains (most relevant first).
    active_domains: list[str] = field(default_factory=list)

    # Technical terms that have appeared recently — used to disambiguate
    # Whisper mishearings.
    recent_terms: list[str] = field(default_factory=list)

    # Human-readable label for the current project / focus.
    active_project: str = ""

    # How many hours back to look in transcript history for recent terms.
    recency_hours: int = 2

    # ISO-8601 timestamp of when this context was last updated.
    last_updated: str = ""

    def is_stale(self, max_age_seconds: int = 3600) -> bool:
        """Return True if the context is older than ``max_age_seconds``."""
        if not self.last_updated:
            return True
        from datetime import datetime, timezone
        try:
            updated = datetime.fromisoformat(self.last_updated)
            now = datetime.now(timezone.utc)
            return (now - updated).total_seconds() > max_age_seconds
        except ValueError:
            return True
        # end is_stale

    # end UserContext


def load_user_context() -> UserContext:
    """Load context from disk, merging static JSON with live memory.

    Recent terms and active domains are pulled from the transcript history
    database (via ``memory.py``) and mixed with whatever the user wrote in
    ``context.json``.  This means the transcriber adapts to what you were
    actually talking about, not just what you manually configured.
    """
    if not _CONTEXT_PATH.exists():
        return UserContext()

    try:
        payload = json.loads(_CONTEXT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UserContext()

    ctx = UserContext(
        active_domains=_list_of_str(payload.get("active_domains", [])),
        recent_terms=_list_of_str(payload.get("recent_terms", [])),
        active_project=_str_or_blank(payload.get("active_project", "")),
        recency_hours=int(payload.get("recency_hours", 2)),
        last_updated=_str_or_blank(payload.get("last_updated", "")),
    )

    # Merge memory-derived terms and domains
    try:
        from voice_transcriber.memory import build_user_context_from_memory

        mem_domains, mem_terms = build_user_context_from_memory(
            hours=ctx.recency_hours,
            max_terms=15,
        )
        # Memory domains prepend to the user-configured ones (most recent first)
        merged_domains = list(dict.fromkeys(mem_domains + ctx.active_domains))
        # Memory terms prepend similarly
        merged_terms = list(dict.fromkeys(mem_terms + ctx.recent_terms))
        ctx.active_domains = merged_domains
        ctx.recent_terms = merged_terms
    except Exception:
        # If memory query fails for any reason, fall back to static JSON only
        pass

    return ctx


def save_user_context(ctx: UserContext) -> None:
    """Persist context to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_domains": ctx.active_domains,
        "recent_terms": ctx.recent_terms,
        "active_project": ctx.active_project,
        "last_updated": ctx.last_updated,
    }
    _CONTEXT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # end save_user_context


def _list_of_str(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if str(v).strip()]


def _str_or_blank(value: object) -> str:
    return str(value) if value else ""
