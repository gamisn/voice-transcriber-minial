"""Domain auto-detection and glossary correction.

Glossaries are loaded from ``voice_transcriber/glossaries/*.json`` at first
use. Each JSON file declares a ``domain_id``, a list of detection
``keywords``, and a list of ``entries`` mapping canonical terms to alias
lists. Adding a new domain (e.g. medical, legal, email) is a matter of
dropping a JSON file in that directory.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass

from voice_transcriber import context as context_module
from .models import DomainMatch


_GLOSSARY_DIR: pathlib.Path = pathlib.Path(__file__).parent / "glossaries"


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    """One canonical term plus the aliases that should map to it."""

    canonical: str
    aliases: tuple[str, ...]
    # end GlossaryEntry


@dataclass(frozen=True, slots=True)
class Glossary:
    """A loaded glossary file: detection keywords plus correction entries."""

    domain_id: str
    keywords: frozenset[str]
    entries: tuple[GlossaryEntry, ...]
    # end Glossary


_glossary_cache: dict[str, Glossary] = {}


def _load_glossaries() -> dict[str, Glossary]:
    """Load all glossaries from disk on first use; cache the result."""
    if _glossary_cache:
        return _glossary_cache

    if not _GLOSSARY_DIR.exists():
        return _glossary_cache

    for path in sorted(_GLOSSARY_DIR.glob("*.json")):
        glossary = _read_glossary_file(path)
        _glossary_cache[glossary.domain_id] = glossary
    return _glossary_cache
    # end _load_glossaries


def _read_glossary_file(path: pathlib.Path) -> Glossary:
    """Parse a single glossary JSON file into a typed ``Glossary``."""
    payload = json.loads(path.read_text())

    domain_id = str(payload["domain_id"]).strip()
    if not domain_id:
        raise ValueError(f"Glossary {path.name} has empty domain_id.")

    raw_keywords = payload.get("keywords", [])
    if not isinstance(raw_keywords, list):
        raise ValueError(f"Glossary {path.name}: keywords must be a list.")
    keywords = frozenset(str(kw).lower() for kw in raw_keywords if str(kw).strip())

    raw_entries = payload.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ValueError(f"Glossary {path.name}: entries must be a list.")

    entries = tuple(
        GlossaryEntry(
            canonical=str(entry["canonical"]),
            aliases=tuple(str(a) for a in entry.get("aliases", [])),
        )
        for entry in raw_entries
    )

    return Glossary(domain_id=domain_id, keywords=keywords, entries=entries)
    # end _read_glossary_file


def available_domains() -> list[str]:
    """Return the list of domain ids that have a glossary on disk."""
    return sorted(_load_glossaries().keys())
    # end available_domains


def detect_domain(
    text: str,
    domain_hint: str,
    context: "context_module.UserContext | None" = None,
) -> DomainMatch:
    """Detect the speech domain from transcript content or an explicit hint.

    With ``domain_hint == "auto"`` we tally how many tokens in the transcript
    appear in each glossary's ``keywords`` set **and** in the aliases of its
    ``entries``. This means a mangled technical term (e.g. "i space" for
    ``IServiceScopeFactory``) can still trigger the correct domain.

    When ``context`` is provided, we bias the scoring toward the user's
    active domains and boost confidence for terms that appear in the
    ``recent_terms`` list.
    """
    normalized = text.strip().lower()

    if domain_hint and domain_hint != "auto":
        return DomainMatch(domain_id=domain_hint, confidence=1.0, keywords=[])

    tokens = [token for token in re.split(r"[^a-z0-9+#.-]+", normalized) if token]
    if not tokens:
        return DomainMatch()

    glossaries = _load_glossaries()
    best_id: str = "general"
    best_matches: list[str] = []
    best_score: float = 0.0

    active_domains: set[str] = set()
    recent_terms_set: set[str] = set()
    if context is not None:
        active_domains = {d.lower() for d in context.active_domains}
        recent_terms_set = {t.lower() for t in context.recent_terms}

    # Load memory-derived domain boosts (independent of UserContext)
    memory_boosts: dict[str, float] = {}
    try:
        from voice_transcriber.memory import get_domain_boosts

        memory_boosts = {b.domain_id: b.score for b in get_domain_boosts(hours=2)}
    except Exception:
        pass

    # Pre-build alias-to-domain index for fast lookup
    alias_to_domain: dict[str, list[str]] = {}
    for glossary in glossaries.values():
        for entry in glossary.entries:
            for alias in entry.aliases:
                alias_key = alias.lower()
                alias_to_domain.setdefault(alias_key, []).append(glossary.domain_id)
            # Also index the canonical form
            alias_to_domain.setdefault(entry.canonical.lower(), []).append(glossary.domain_id)

    for glossary in glossaries.values():
        # 1. Keyword matches
        keyword_matched = sorted({token for token in tokens if token in glossary.keywords})
        # 2. Alias matches (tokens that appear in any entry alias for this domain)
        alias_matched = sorted({
            token for token in tokens
            if glossary.domain_id in alias_to_domain.get(token, [])
        })
        # 2b. Phrase-level scan for multi-word aliases
        # (e.g. "i space" for IServiceScopeFactory, "as no tracking" for AsNoTracking)
        for entry in glossary.entries:
            for alias in entry.aliases:
                if " " in alias and alias in normalized:
                    alias_matched.append(alias)
        alias_matched = sorted(set(alias_matched))

        # Combine without duplicates
        all_matched = sorted(set(keyword_matched) | set(alias_matched))
        score = float(len(all_matched))

        # Only apply bias when the transcript actually contains some matches.
        # This prevents active domains from winning on completely generic text.
        if len(all_matched) > 0:
            # Bias: boost score if glossary domain is in user's active domains
            if glossary.domain_id.lower() in active_domains:
                score += 0.5

            # Bias: boost score for matched tokens that are recent terms
            score += sum(1 for token in all_matched if token in recent_terms_set)

            # Phase 3: Memory Sync — recency bias from transcript history
            mem_boost = memory_boosts.get(glossary.domain_id, 0.0)
            if mem_boost > 0:
                score += min(mem_boost * 0.15, 0.6)  # cap at 0.6 to avoid overriding keywords

        if score > best_score:
            best_score = score
            best_matches = all_matched
            best_id = glossary.domain_id

    if not best_matches and best_score == 0.0:
        return DomainMatch()

    confidence = min(0.35 + (len(best_matches) / max(len(tokens), 1)) * 3.2, 0.99)
    if len(best_matches) >= 2:
        confidence = max(confidence, 0.7)

    # Boost confidence slightly when context helped us pick this domain
    if best_id.lower() in active_domains:
        confidence = min(confidence + 0.05, 0.99)

    return DomainMatch(
        domain_id=best_id,
        confidence=round(confidence, 2),
        keywords=best_matches,
    )
    # end detect_domain


def apply_glossary(
    text: str,
    domain: DomainMatch,
    custom_terms: list[str],
) -> tuple[str, list[str]]:
    """Apply glossary corrections and custom terms to the transcript."""
    corrected = text
    applied_terms: list[str] = []

    glossary = _load_glossaries().get(domain.domain_id)
    if glossary is not None:
        for entry in glossary.entries:
            corrected, applied = _apply_entry(corrected, entry)
            if applied:
                applied_terms.append(entry.canonical)

    for term in custom_terms:
        corrected, applied = _apply_custom_term(corrected, term)
        if applied:
            applied_terms.append(term)

    return corrected, applied_terms
    # end apply_glossary


def _apply_entry(text: str, entry: GlossaryEntry) -> tuple[str, bool]:
    updated = text
    applied = False
    for alias in (entry.canonical, *entry.aliases):
        pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
        updated, count = pattern.subn(entry.canonical, updated)
        if count:
            applied = True
    return updated, applied
    # end _apply_entry


def _apply_custom_term(text: str, term: str) -> tuple[str, bool]:
    fragments = [frag for frag in re.split(r"[\s_-]+", term) if frag]
    if not fragments:
        return text, False

    pattern = re.compile(
        r"\b" + r"[\s_-]*".join(re.escape(frag) for frag in fragments) + r"\b",
        re.IGNORECASE,
    )
    updated, count = pattern.subn(term, text)
    return updated, bool(count)
    # end _apply_custom_term
