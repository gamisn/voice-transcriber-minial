from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


CONFIG_DIR: Path = Path.home() / ".config" / "voice-transcriber"
CONFIG_PATH: Path = CONFIG_DIR / "config.json"


@dataclass(slots=True)
class AppConfig:
    """Persistent application configuration."""

    default_model: str = "base"
    default_language: str = "en"
    domain_hint: str = "auto"
    custom_terms: list[str] = field(default_factory=list)

    # Phase 1: Context Bridge
    context_enabled: bool = True
    # end AppConfig


def load_config() -> AppConfig:
    """Load config from disk, returning sane defaults on any failure."""
    if not CONFIG_PATH.exists():
        return AppConfig()

    try:
        payload = json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return AppConfig()

    return AppConfig(
        default_model=str(payload.get("default_model", "base")),
        default_language=str(payload.get("default_language", "en")),
        domain_hint=str(payload.get("domain_hint", "auto")),
        custom_terms=_normalize_terms(payload.get("custom_terms", [])),
        context_enabled=bool(payload.get("context_enabled", True)),
    )
    # end load_config


def save_config(config: AppConfig) -> None:
    """Persist config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    payload["custom_terms"] = _normalize_terms(config.custom_terms)
    CONFIG_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    # end save_config


def _normalize_terms(terms: list[str] | tuple[str, ...] | object) -> list[str]:
    """Deduplicate and strip custom terms, preserving insertion order."""
    if not isinstance(terms, (list, tuple)):
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_term in terms:
        term = str(raw_term).strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped
    # end _normalize_terms
