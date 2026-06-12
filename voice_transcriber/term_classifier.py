"""Heuristic classifier that decides whether a raw/corrected pair
should become a glossary candidate.

Rules (all must be true for a proposal to be generated):
1. The raw text and corrected text differ (something was actually fixed).
2. The corrected form is not just a punctuation/whitespace change.
3. The corrected form contains at least one capital letter or technical
   character (dash, underscore, slash) — suggesting it's a proper term,
   not common English.
4. The raw form is not already in the glossary aliases for this domain
   (no duplicates).
5. The alias is not "too generic" (e.g. "it", "the", "a", "and").

These are deterministic heuristics. They can be tuned without retraining.
"""

from __future__ import annotations

import re

from voice_transcriber.domain import _load_glossaries


def _is_generic_word(word: str) -> bool:
    """Exclude very common English words from becoming aliases."""
    generic = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "he", "in", "is", "it", "its", "of", "on", "or", "that",
        "the", "to", "was", "will", "with",
    }
    return word.lower() in generic


def _looks_technical(text: str) -> bool:
    """Heuristic: does this look like a technical/proper term rather than
    plain English?

    True if the text contains any of:
    - uppercase letter (CamelCase, PascalCase)
    - digit
    - special chars: _ - / . + #
    """
    return bool(re.search(r"[A-Z0-9_\-/.+#]", text))


def _is_just_punctuation_change(raw: str, corrected: str) -> bool:
    """Return True if the only difference is whitespace, capitalization,
    or trailing punctuation."""
    # Normalize both: lowercase, strip whitespace, remove trailing period
    norm_raw = raw.lower().strip().rstrip(".")
    norm_corr = corrected.lower().strip().rstrip(".")
    return norm_raw == norm_corr


def _alias_exists_in_glossary(domain: str, alias: str) -> bool:
    """Check whether this alias is already registered for the domain."""
    glossaries = _load_glossaries()
    glossary = glossaries.get(domain)
    if glossary is None:
        return False
    alias_lc = alias.lower()
    for entry in glossary.entries:
        if entry.canonical.lower() == alias_lc:
            return True
        if any(a.lower() == alias_lc for a in entry.aliases):
            return True
    return False


def classify_correction(
    raw: str,
    corrected: str,
    applied_terms: list[str],
    domain: str,
) -> list[dict]:
    """Given a raw/corrected transcript pair, return zero or more candidate
    glossary entries that should be proposed for user approval.

    Each candidate is a dict:
        {
            "domain": str,
            "canonical": str,   -- the corrected form
            "alias": str,       -- the raw mishearing
            "raw": str,         -- full original transcript
            "corrected": str,   -- full corrected transcript
        }
    """
    candidates: list[dict] = []

    # 1. Nothing was corrected → no candidates
    if raw == corrected:
        return candidates

    # 2. Only punctuation changed → no candidates
    if _is_just_punctuation_change(raw, corrected):
        return candidates

    # 3. For each applied term, try to find the raw alias that maps to it.
    #    We do this heuristically: look for a contiguous span in the raw
    #    text that "sounds like" the canonical term.
    for term in applied_terms:
        # Find the raw alias by looking for the longest lowercase substring
        # in raw that could correspond to this term.
        alias = _extract_alias_for_term(raw, term)
        if alias is None:
            continue

        # 4. Skip generic words
        if _is_generic_word(alias):
            continue

        # 5. Skip if already in glossary
        if _alias_exists_in_glossary(domain, alias):
            continue

        # 6. The corrected term must look technical
        if not _looks_technical(term):
            continue

        candidates.append(
            {
                "domain": domain,
                "canonical": term,
                "alias": alias,
                "raw": raw,
                "corrected": corrected,
            }
        )

    return candidates


def _extract_alias_for_term(raw: str, canonical: str) -> str | None:
    """Given the raw transcript and a canonical term that was applied,
    try to find the raw mishearing that corresponds to it.

    Strategy:
    1. Tokenize both raw and canonical.
    2. For single-word canonicals, pick the raw token with highest
       character similarity to the canonical (excluding exact matches).
    3. For multi-word canonicals, look for a contiguous span in raw with
       the same token count and pick the one with highest similarity.
    4. Only return an alias if similarity exceeds a threshold (prevents
       false positives like 'deploy' for 'Docker').
    """
    raw_lower = raw.lower()
    canon_lower = canonical.lower()

    raw_tokens = [t for t in re.split(r"[^a-z0-9]+", raw_lower) if t]
    canon_tokens = [t for t in re.split(r"[^a-z0-9]+", canon_lower) if t]

    if not raw_tokens:
        return None

    best_alias: str | None = None
    best_score = 0.0

    n = len(canon_tokens)
    for i in range(len(raw_tokens) - n + 1):
        span = raw_tokens[i : i + n]
        span_text = " ".join(span)

        # Skip if the span is literally the canonical (not a mishearing)
        if span_text == canon_lower:
            continue

        score = _token_similarity(span_text, canon_lower)
        if score > best_score:
            best_score = score
            best_alias = span_text

    # Threshold: require at least 50% character similarity to avoid
    # spurious matches like "deploy" for "Docker".
    if best_alias is not None and best_score >= 0.5:
        return best_alias

    # Fallback: return the whole raw text if it's short
    if len(raw_tokens) <= 4:
        return raw_lower.strip()

    return None


def _token_similarity(a: str, b: str) -> float:
    """Normalized character-based similarity (0.0–1.0).

    Combines:
    - Jaccard overlap of character sets
    - Length ratio penalty (very different lengths score lower)
    """
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0

    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    jaccard = intersection / union

    # Length penalty: if lengths differ by > 2x, heavily penalize
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))

    return (jaccard * 0.7) + (len_ratio * 0.3)


def _character_overlap(a: str, b: str) -> float:
    """Return Jaccard-ish overlap of character sets (0.0–1.0)."""
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union
