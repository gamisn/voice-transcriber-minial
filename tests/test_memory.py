"""Tests for Phase 3: Memory Sync — recency-weighted term memory.

Covers:
- memory.get_recent_terms: recency scoring from transcript history
- memory.get_domain_boosts: per-domain recency scores
- memory.build_user_context_from_memory: tuple output
- context.load_user_context: merges static JSON with live memory
- domain.detect_domain: uses memory-derived recency bias
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from voice_transcriber import history as history_module
from voice_transcriber import memory as memory_module
from voice_transcriber.domain import _glossary_cache, detect_domain


class MemoryRecentTermsTests(unittest.TestCase):
    """Recency-weighted term extraction from history."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_db = history_module._DB_PATH
        history_module._DB_PATH = pathlib.Path(self._temp_dir.name) / "test_memory.db"
        _glossary_cache.clear()
        # end setUp

    def tearDown(self) -> None:
        history_module._DB_PATH = self._orig_db
        self._temp_dir.cleanup()
        _glossary_cache.clear()
        # end tearDown

    def _seed_transcript(
        self,
        raw: str,
        corrected: str,
        domain: str,
        applied_terms: list[str],
        minutes_ago: int = 0,
    ) -> None:
        """Insert a transcript row with a backdated timestamp."""
        # Ensure schema exists via history module's connection helper
        _ = history_module.list_transcripts(limit=1)

        ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        with sqlite3.connect(history_module._DB_PATH, check_same_thread=False) as conn:
            conn.execute(
                """
                INSERT INTO transcripts (raw, corrected, domain, confidence, applied_terms, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (raw, corrected, domain, 0.9, json.dumps(applied_terms), ts.isoformat()),
            )
            conn.commit()
        # end _seed_transcript

    def test_get_recent_terms_returns_empty_when_no_history(self) -> None:
        terms = memory_module.get_recent_terms(hours=2, limit=10)
        self.assertEqual(terms, [])
        # end test_get_recent_terms_returns_empty_when_no_history

    def test_get_recent_terms_weights_by_recency(self) -> None:
        # 10 min ago: Docker (weight ~6.0)
        self._seed_transcript("use docker", "use Docker", "technical", ["Docker"], minutes_ago=10)
        # 60 min ago: Kubernetes (weight ~1.0)
        self._seed_transcript("use k8s", "use Kubernetes", "technical", ["Kubernetes"], minutes_ago=60)

        terms = memory_module.get_recent_terms(hours=2, limit=10)
        self.assertEqual(len(terms), 2)
        # Docker should have higher score than Kubernetes
        self.assertEqual(terms[0].term, "Docker")
        self.assertGreater(terms[0].score, terms[1].score)
        # end test_get_recent_terms_weights_by_recency

    def test_get_recent_terms_filters_by_hours(self) -> None:
        self._seed_transcript("old term", "Old Term", "technical", ["OldTerm"], minutes_ago=180)
        self._seed_transcript("new term", "New Term", "technical", ["NewTerm"], minutes_ago=10)

        # 1-hour window: only NewTerm
        terms = memory_module.get_recent_terms(hours=1, limit=10)
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0].term, "NewTerm")
        # end test_get_recent_terms_filters_by_hours

    def test_get_domain_boosts(self) -> None:
        self._seed_transcript("a", "A", "technical", ["Docker"], minutes_ago=10)
        self._seed_transcript("b", "B", "technical", ["Kubernetes"], minutes_ago=20)
        self._seed_transcript("c", "C", "csharp", ["Async"], minutes_ago=30)

        boosts = memory_module.get_domain_boosts(hours=2)
        self.assertEqual(len(boosts), 2)
        # technical should rank higher (two transcripts, more recent)
        self.assertEqual(boosts[0].domain_id, "technical")
        self.assertGreater(boosts[0].score, boosts[1].score)
        # end test_get_domain_boosts

    def test_build_user_context_from_memory(self) -> None:
        self._seed_transcript("a", "A", "technical", ["Docker"], minutes_ago=10)
        self._seed_transcript("b", "B", "csharp", ["Async"], minutes_ago=20)

        domains, terms = memory_module.build_user_context_from_memory(hours=2, max_terms=10)
        self.assertIn("technical", domains)
        self.assertIn("csharp", domains)
        self.assertIn("Docker", terms)
        self.assertIn("Async", terms)
        # end test_build_user_context_from_memory


class MemoryDomainDetectionTests(unittest.TestCase):
    """Domain detection uses memory-derived recency bias."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_db = history_module._DB_PATH
        history_module._DB_PATH = pathlib.Path(self._temp_dir.name) / "test_domain.db"
        _glossary_cache.clear()
        # end setUp

    def tearDown(self) -> None:
        history_module._DB_PATH = self._orig_db
        self._temp_dir.cleanup()
        _glossary_cache.clear()
        # end tearDown

    def _seed_transcript(
        self,
        raw: str,
        corrected: str,
        domain: str,
        applied_terms: list[str],
        minutes_ago: int = 0,
    ) -> None:
        """Insert a transcript row with a backdated timestamp."""
        # Ensure schema exists via history module's connection helper
        _ = history_module.list_transcripts(limit=1)

        ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        with sqlite3.connect(history_module._DB_PATH, check_same_thread=False) as conn:
            conn.execute(
                """
                INSERT INTO transcripts (raw, corrected, domain, confidence, applied_terms, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (raw, corrected, domain, 0.9, json.dumps(applied_terms), ts.isoformat()),
            )
            conn.commit()
        # end _seed_transcript

    def test_memory_boost_tips_domain_when_keywords_are_weak(self) -> None:
        """If user was recently talking about Docker, a phrase with a weak
        technical signal ('deploy') should tip toward technical due to
        recency bias."""
        # Seed history: Docker was corrected 10 min ago
        self._seed_transcript(
            "use docker compose",
            "use Docker Compose",
            "technical",
            ["Docker", "Compose"],
            minutes_ago=10,
        )

        # "deploy" is a weak signal — it appears in technical keywords but
        # also in general English. With memory boost from recent technical
        # transcripts, technical should win.
        result = detect_domain("deploy the app", domain_hint="auto")
        self.assertEqual(result.domain_id, "technical")
        # end test_memory_boost_tips_domain_when_keywords_are_weak

    def test_no_memory_boost_when_history_is_empty(self) -> None:
        result = detect_domain("hello world how are you", domain_hint="auto")
        self.assertEqual(result.domain_id, "general")
        # end test_no_memory_boost_when_history_is_empty


if __name__ == "__main__":
    unittest.main()
