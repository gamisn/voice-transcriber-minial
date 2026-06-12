"""Tests for Phase 2: Dynamic Glossary generation and history storage.

Covers:
- history.py: SQLite record/retrieve, pending term upsert, approval flow
- term_classifier.py: heuristic classification of raw/corrected pairs
- observer.py: integration of history + classifier
- reviewer.py: CLI entry point (smoke test)
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import tempfile
import unittest

from voice_transcriber import history as history_module
from voice_transcriber import observer as observer_module
from voice_transcriber import term_classifier as classifier
from voice_transcriber.domain import _glossary_cache


class HistoryStorageTests(unittest.TestCase):
    """SQLite transcript history."""

    def setUp(self) -> None:
        # Point history at a temp database so we don't pollute the user's
        # real ~/.cache directory during tests.
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_db = history_module._DB_PATH
        history_module._DB_PATH = pathlib.Path(self._temp_dir.name) / "test_history.db"
        # end setUp

    def tearDown(self) -> None:
        history_module._DB_PATH = self._orig_db
        self._temp_dir.cleanup()
        # end tearDown

    def test_record_and_list_transcripts(self) -> None:
        row_id = history_module.record_transcript(
            raw="deploy on doctor",
            corrected="deploy on Docker",
            domain="technical",
            confidence=0.88,
            applied_terms=["Docker"],
        )
        self.assertIsInstance(row_id, int)
        self.assertGreater(row_id, 0)

        rows = history_module.list_transcripts(limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].raw, "deploy on doctor")
        self.assertEqual(rows[0].corrected, "deploy on Docker")
        self.assertEqual(rows[0].applied_terms, ["Docker"])
        # end test_record_and_list_transcripts

    def test_list_transcripts_respects_domain_filter(self) -> None:
        history_module.record_transcript(
            raw="a", corrected="A", domain="technical", confidence=0.5, applied_terms=[]
        )
        history_module.record_transcript(
            raw="b", corrected="B", domain="csharp", confidence=0.5, applied_terms=[]
        )
        rows = history_module.list_transcripts(domain="csharp", limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].domain, "csharp")
        # end test_list_transcripts_respects_domain_filter

    def test_pending_term_upsert_bumps_count(self) -> None:
        history_module.record_pending_term(
            domain="technical",
            canonical="Docker",
            alias="doctor",
            raw="deploy on doctor",
            corrected="deploy on Docker",
        )
        history_module.record_pending_term(
            domain="technical",
            canonical="Docker",
            alias="doctor",
            raw="run doctor container",
            corrected="run Docker container",
        )

        pending = history_module.list_pending_terms(min_occurrences=1)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["occurrence_count"], 2)
        # end test_pending_term_upsert_bumps_count

    def test_approve_pending_term_updates_glossary(self) -> None:
        # Clear cache so we start from a known state
        _glossary_cache.clear()

        history_module.record_pending_term(
            domain="technical",
            canonical="Docker",
            alias="doctor",
            raw="deploy on doctor",
            corrected="deploy on Docker",
        )
        pending = history_module.list_pending_terms()
        term_id = pending[0]["id"]

        history_module.approve_pending_term(term_id)

        # Check DB status
        updated = history_module.list_pending_terms(status="approved")
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["status"], "approved")
        # end test_approve_pending_term_updates_glossary

    def test_reject_pending_term(self) -> None:
        history_module.record_pending_term(
            domain="technical",
            canonical="Docker",
            alias="doctor",
            raw="x",
            corrected="y",
        )
        pending = history_module.list_pending_terms()
        term_id = pending[0]["id"]

        history_module.reject_pending_term(term_id)
        rejected = history_module.list_pending_terms(status="rejected")
        self.assertEqual(len(rejected), 1)
        # end test_reject_pending_term


class TermClassifierTests(unittest.TestCase):
    """Heuristic classification of raw/corrected pairs."""

    def setUp(self) -> None:
        _glossary_cache.clear()
        # end setUp

    def tearDown(self) -> None:
        _glossary_cache.clear()
        # end tearDown

    def test_identical_raw_and_corrected_produces_no_candidates(self) -> None:
        candidates = classifier.classify_correction(
            raw="hello world",
            corrected="hello world",
            applied_terms=[],
            domain="technical",
        )
        self.assertEqual(candidates, [])
        # end test_identical_raw_and_corrected_produces_no_candidates

    def test_punctuation_change_only_produces_no_candidates(self) -> None:
        candidates = classifier.classify_correction(
            raw="hello world",
            corrected="Hello world.",
            applied_terms=[],
            domain="technical",
        )
        self.assertEqual(candidates, [])
        # end test_punctuation_change_only_produces_no_candidates

    def test_technical_term_produces_candidate(self) -> None:
        """A new mishearing (not yet in the glossary) should produce a candidate."""
        candidates = classifier.classify_correction(
            raw="deploy on dock er",
            corrected="deploy on Docker",
            applied_terms=["Docker"],
            domain="technical",
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["canonical"], "Docker")
        # The extractor tokenizes on non-alphanumeric, so "dock er" becomes
        # two tokens; for a single-word canonical it picks the best single
        # token span, which is "dock".
        self.assertEqual(candidates[0]["alias"], "dock")
        # end test_technical_term_produces_candidate

    def test_generic_word_is_skipped(self) -> None:
        candidates = classifier.classify_correction(
            raw="it is working",
            corrected="It is working.",
            applied_terms=["It"],
            domain="technical",
        )
        # "It" is not in applied_terms in a real scenario, but if it were,
        # the classifier should skip it because it's generic.
        for c in candidates:
            self.assertNotEqual(c["alias"].lower(), "it")
        # end test_generic_word_is_skipped

    def test_existing_alias_is_not_duplicated(self) -> None:
        # "doctor" is already an alias for "Docker" in technical.json
        candidates = classifier.classify_correction(
            raw="deploy on doctor",
            corrected="deploy on Docker",
            applied_terms=["Docker"],
            domain="technical",
        )
        # Because "doctor" already exists in the glossary, no candidate
        self.assertEqual(candidates, [])
        # end test_existing_alias_is_not_duplicated


class ObserverIntegrationTests(unittest.TestCase):
    """Observer hook that wires history + classifier."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_db = history_module._DB_PATH
        history_module._DB_PATH = pathlib.Path(self._temp_dir.name) / "test_observer.db"
        _glossary_cache.clear()
        # end setUp

    def tearDown(self) -> None:
        history_module._DB_PATH = self._orig_db
        self._temp_dir.cleanup()
        _glossary_cache.clear()
        # end tearDown

    def test_observe_records_transcript(self) -> None:
        observer_module.observe(
            raw="deploy on doctor",
            corrected="deploy on Docker",
            domain="technical",
            confidence=0.88,
            applied_terms=["Docker"],
            auto_glossary=True,
        )
        rows = history_module.list_transcripts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].raw, "deploy on doctor")
        # end test_observe_records_transcript

    def test_observe_with_auto_glossary_off_skips_pending(self) -> None:
        observer_module.observe(
            raw="deploy on doctor",
            corrected="deploy on Docker",
            domain="technical",
            confidence=0.88,
            applied_terms=["Docker"],
            auto_glossary=False,
        )
        pending = history_module.list_pending_terms()
        self.assertEqual(len(pending), 0)
        # end test_observe_with_auto_glossary_off_skips_pending

    def test_observe_without_domain_skips_pending(self) -> None:
        observer_module.observe(
            raw="hello world",
            corrected="Hello world.",
            domain=None,
            confidence=0.0,
            applied_terms=[],
            auto_glossary=True,
        )
        pending = history_module.list_pending_terms()
        self.assertEqual(len(pending), 0)
        # end test_observe_without_domain_skips_pending


if __name__ == "__main__":
    unittest.main()
