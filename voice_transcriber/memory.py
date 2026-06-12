"""Recency-weighted term memory extracted from transcript history.

Provides two primary APIs:

1. ``get_recent_terms(hours=2, limit=10)`` — returns terms with a
   recency score so the transcriber knows what you've been talking about.

2. ``get_domain_boosts(hours=2)`` — returns a per-domain score based on
   how many corrected terms from that domain appeared recently.

Used by ``context.py`` (to populate ``recent_terms``) and ``domain.py``
(to bias domain detection).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from voice_transcriber import history as history_module


@dataclass(slots=True)
class RecentTerm:
    """One term with its recency score and originating domain."""

    term: str
    domain: str | None
    score: float  # higher = more recent / more frequent
    # end RecentTerm


@dataclass(slots=True)
class DomainBoost:
    """A domain with a recency-weighted score for detection bias."""

    domain_id: str
    score: float
    # end DomainBoost


# ── Public API ──────────────────────────────────────────────────────────


def get_recent_terms(
    hours: int = 2,
    limit: int = 10,
) -> list[RecentTerm]:
    """Return the most relevant recent terms from transcript history.

    Scoring: ``SUM(1.0 / hours_since)`` per term. A term used 10 minutes
    ago contributes 6.0 points; one used 1 hour ago contributes 1.0;
    one used 2 hours ago contributes 0.5.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    rows = history_module.list_transcripts(since=cutoff_iso, limit=1000)

    if not rows:
        return []

    now = datetime.now(timezone.utc)
    term_scores: dict[tuple[str, str | None], float] = {}

    for row in rows:
        try:
            created = datetime.fromisoformat(row.created_at)
        except ValueError:
            continue

        hours_since = max((now - created).total_seconds() / 3600.0, 0.0001)
        weight = 1.0 / hours_since

        for term in row.applied_terms:
            key = (term, row.domain)
            term_scores[key] = term_scores.get(key, 0.0) + weight

    # Sort by score descending, take top N
    sorted_terms = sorted(term_scores.items(), key=lambda kv: kv[1], reverse=True)
    return [
        RecentTerm(term=term, domain=domain, score=round(score, 2))
        for (term, domain), score in sorted_terms[:limit]
    ]
    # end get_recent_terms


def get_domain_boosts(
    hours: int = 2,
) -> list[DomainBoost]:
    """Return per-domain recency scores for detection bias.

    Each domain gets a score equal to the number of transcripts in the
    window weighted by recency. Used by ``detect_domain`` to boost
    confidence when the user was recently talking about a topic.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    rows = history_module.list_transcripts(since=cutoff_iso, limit=1000)

    if not rows:
        return []

    now = datetime.now(timezone.utc)
    domain_scores: dict[str, float] = {}

    for row in rows:
        if not row.domain:
            continue
        try:
            created = datetime.fromisoformat(row.created_at)
        except ValueError:
            continue

        hours_since = max((now - created).total_seconds() / 3600.0, 0.0001)
        weight = 1.0 / hours_since
        domain_scores[row.domain] = domain_scores.get(row.domain, 0.0) + weight

    sorted_domains = sorted(domain_scores.items(), key=lambda kv: kv[1], reverse=True)
    return [
        DomainBoost(domain_id=domain_id, score=round(score, 2))
        for domain_id, score in sorted_domains
    ]
    # end get_domain_boosts


def build_user_context_from_memory(
    hours: int = 2,
    max_terms: int = 15,
) -> tuple[list[str], list[str]]:
    """Convenience: return ``(active_domains, recent_terms)`` ready to
    inject into a ``UserContext``.

    Active domains are those with any boost score. Recent terms are the
    top-N scored terms from the window.
    """
    boosts = get_domain_boosts(hours=hours)
    active_domains = [b.domain_id for b in boosts]
    recent_terms = [t.term for t in get_recent_terms(hours=hours, limit=max_terms)]
    return active_domains, recent_terms
    # end build_user_context_from_memory
