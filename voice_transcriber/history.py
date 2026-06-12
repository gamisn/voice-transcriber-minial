"""SQLite-based transcript history for learning from usage.

Every transcription produces a row in ``transcripts``:
- raw: what Whisper actually heard
- corrected: after glossary + formatter
- domain: which glossary was applied
- applied_terms: list of canonical terms that were corrected
- timestamp: ISO 8601 UTC

Pending glossary candidates are extracted from this history and stored
in ``pending_glossary_entries`` for user review.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


_CACHE_DIR: pathlib.Path = pathlib.Path.home() / ".cache" / "voice-transcriber"
_DB_PATH: pathlib.Path = _CACHE_DIR / "history.db"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables on first use."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw TEXT NOT NULL,
            corrected TEXT NOT NULL,
            domain TEXT,
            confidence REAL,
            applied_terms TEXT,  -- JSON list
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_transcripts_domain
            ON transcripts(domain);

        CREATE INDEX IF NOT EXISTS idx_transcripts_created
            ON transcripts(created_at);

        CREATE TABLE IF NOT EXISTS pending_glossary_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            canonical TEXT NOT NULL,
            alias TEXT NOT NULL,
            raw TEXT NOT NULL,          -- the original mishearing
            corrected TEXT NOT NULL,    -- the corrected form
            occurrence_count INTEGER DEFAULT 1,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            status TEXT DEFAULT 'pending'  -- pending | approved | rejected
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_domain_alias
            ON pending_glossary_entries(domain, alias);
        """
    )
    conn.commit()


def _connection() -> sqlite3.Connection:
    """Open (and possibly create) the history database."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


# ── Public API ──────────────────────────────────────────────────────────


def record_transcript(
    raw: str,
    corrected: str,
    domain: str | None,
    confidence: float,
    applied_terms: list[str],
) -> int:
    """Store one transcription result. Returns the inserted row id."""
    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO transcripts (raw, corrected, domain, confidence, applied_terms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                raw,
                corrected,
                domain,
                confidence,
                json.dumps(applied_terms),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("Failed to get lastrowid after INSERT")
        return row_id


@dataclass(slots=True)
class TranscriptRow:
    id: int
    raw: str
    corrected: str
    domain: str | None
    confidence: float
    applied_terms: list[str]
    created_at: str


def list_transcripts(
    since: str | None = None,
    domain: str | None = None,
    limit: int = 100,
) -> list[TranscriptRow]:
    """Fetch recent transcripts with optional filters."""
    clauses: list[str] = []
    params: list[str | int] = []

    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    if domain:
        clauses.append("domain = ?")
        params.append(domain)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM transcripts {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with _connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [
            TranscriptRow(
                id=r["id"],
                raw=r["raw"],
                corrected=r["corrected"],
                domain=r["domain"],
                confidence=r["confidence"],
                applied_terms=json.loads(r["applied_terms"] or "[]"),
                created_at=r["created_at"],
            )
            for r in rows
        ]


def record_pending_term(
    domain: str,
    canonical: str,
    alias: str,
    raw: str,
    corrected: str,
) -> None:
    """Upsert a candidate glossary entry.

    If the (domain, alias) pair already exists, bump occurrence_count
    and update last_seen.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO pending_glossary_entries
                (domain, canonical, alias, raw, corrected, occurrence_count, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(domain, alias) DO UPDATE SET
                occurrence_count = occurrence_count + 1,
                last_seen = excluded.last_seen,
                raw = excluded.raw,
                corrected = excluded.corrected
            """,
            (domain, canonical, alias, raw, corrected, now, now),
        )
        conn.commit()


def list_pending_terms(
    status: str = "pending",
    min_occurrences: int = 1,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Return pending glossary candidates for user review."""
    with _connection() as conn:
        return conn.execute(
            """
            SELECT * FROM pending_glossary_entries
            WHERE status = ? AND occurrence_count >= ?
            ORDER BY occurrence_count DESC, last_seen DESC
            LIMIT ?
            """,
            (status, min_occurrences, limit),
        ).fetchall()


def approve_pending_term(term_id: int) -> None:
    """Mark a pending term as approved and append it to the domain glossary."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM pending_glossary_entries WHERE id = ?",
            (term_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No pending term with id {term_id}")

        conn.execute(
            "UPDATE pending_glossary_entries SET status = 'approved' WHERE id = ?",
            (term_id,),
        )
        conn.commit()

        # Append to the domain glossary JSON file
        _append_to_glossary(
            domain=row["domain"],
            canonical=row["canonical"],
            alias=row["alias"],
        )


def reject_pending_term(term_id: int) -> None:
    """Mark a pending term as rejected (user explicitly said no)."""
    with _connection() as conn:
        conn.execute(
            "UPDATE pending_glossary_entries SET status = 'rejected' WHERE id = ?",
            (term_id,),
        )
        conn.commit()


# ── Internal helpers ────────────────────────────────────────────────────


def _append_to_glossary(domain: str, canonical: str, alias: str) -> None:
    """Append one entry to the on-disk glossary JSON for the given domain."""
    glossary_dir = pathlib.Path(__file__).parent / "glossaries"
    path = glossary_dir / f"{domain}.json"

    # If the domain file doesn't exist yet, create a minimal skeleton
    if path.exists():
        payload = json.loads(path.read_text())
    else:
        payload = {
            "domain_id": domain,
            "description": f"Auto-generated glossary for {domain}",
            "keywords": [],
            "entries": [],
        }

    entries: list[dict] = payload.get("entries", [])

    # Check if canonical already exists — if so, add alias to it
    for entry in entries:
        if entry["canonical"] == canonical:
            existing_aliases = set(entry.get("aliases", []))
            existing_aliases.add(alias)
            entry["aliases"] = sorted(existing_aliases)
            break
    else:
        entries.append({"canonical": canonical, "aliases": [alias]})

    payload["entries"] = entries
    path.write_text(json.dumps(payload, indent=2) + "\n")

    # Invalidate in-memory cache so the next transcription picks it up
    from voice_transcriber.domain import _glossary_cache

    _glossary_cache.clear()
