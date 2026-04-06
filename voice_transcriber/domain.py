from __future__ import annotations

import re
from dataclasses import dataclass

from .models import DomainMatch


TECH_KEYWORDS: frozenset[str] = frozenset({
    "aws",
    "api",
    "backend",
    "bug",
    "ci",
    "cloud",
    "code",
    "database",
    "deploy",
    "docker",
    "frontend",
    "git",
    "github",
    "javascript",
    "kubernetes",
    "lambda",
    "linux",
    "postgres",
    "postgresql",
    "python",
    "react",
    "refactor",
    "repository",
    "server",
    "service",
    "sql",
    "terraform",
    "typescript",
})


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    canonical: str
    aliases: tuple[str, ...]
    # end GlossaryEntry


TECH_GLOSSARY: tuple[GlossaryEntry, ...] = (
    GlossaryEntry("AWS", ("a w s", "aw s", "a double u s", "adobius")),
    GlossaryEntry("AWS Lambda", ("aws lamda", "aws lamba", "a w s lambda")),
    GlossaryEntry("Amazon S3", ("amazon s 3", "amazon s three", "s3")),
    GlossaryEntry("API", ("a p i", "ap i")),
    GlossaryEntry("CI/CD", ("ci cd", "c i c d", "ci slash cd")),
    GlossaryEntry("Docker", ("doctor", "dock er")),
    GlossaryEntry("Git", ("get",)),
    GlossaryEntry("GitHub", ("git hub", "github")),
    GlossaryEntry("Kubernetes", ("kubernettes", "cooper netties", "kuber netes")),
    GlossaryEntry("Linux", ("linucks", "linix")),
    GlossaryEntry("PostgreSQL", ("postgres q l", "postgre sequel", "postgres")),
    GlossaryEntry("Python", ("pie thon",)),
    GlossaryEntry("React", ("re act",)),
    GlossaryEntry("SQL", ("sequel", "s q l")),
    GlossaryEntry("Terraform", ("terra form",)),
    GlossaryEntry("TypeScript", ("type script", "typescript")),
)


def detect_domain(text: str, domain_hint: str) -> DomainMatch:
    """Detect the speech domain from transcript content or an explicit hint."""
    normalized = text.strip().lower()

    if domain_hint and domain_hint != "auto":
        return DomainMatch(domain_id=domain_hint, confidence=1.0, keywords=[])

    tokens = [token for token in re.split(r"[^a-z0-9+#.-]+", normalized) if token]
    matched = sorted({token for token in tokens if token in TECH_KEYWORDS})
    if not tokens or not matched:
        return DomainMatch()

    confidence = min(0.35 + (len(matched) / max(len(tokens), 1)) * 3.2, 0.99)
    if len(matched) >= 2:
        confidence = max(confidence, 0.7)

    return DomainMatch(
        domain_id="technical",
        confidence=round(confidence, 2),
        keywords=matched,
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

    if domain.domain_id == "technical":
        for entry in TECH_GLOSSARY:
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
