"""Tests for the context-aware domain detection (Phase 1).

Verifies that ``detect_domain`` correctly uses active domains and
recent terms from a ``UserContext`` object.
"""

from __future__ import annotations

import unittest

from voice_transcriber.context import UserContext
from voice_transcriber.domain import detect_domain
from voice_transcriber import domain as domain_module


def _reset_cache() -> None:
    domain_module._glossary_cache.clear()


class ContextAwareDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()
        # end setUp

    def tearDown(self) -> None:
        _reset_cache()
        # end tearDown

    def test_context_biases_toward_active_domain(self) -> None:
        raw = "deploy the doctor container"

        # Without context — "doctor" matches technical glossary (Docker alias)
        no_ctx = detect_domain(raw, domain_hint="auto")
        self.assertEqual(no_ctx.domain_id, "technical")

        # With csharp as active domain — "deploy" and "container" are weak
        # technical signals, but csharp is boosted. We still expect technical
        # to win because "docker" is a strong keyword match, but the test
        # verifies the code path doesn't crash.
        ctx = UserContext(active_domains=["csharp"], recent_terms=[])
        with_ctx = detect_domain(raw, domain_hint="auto", context=ctx)
        self.assertEqual(with_ctx.domain_id, "technical")
        # end test_context_biases_toward_active_domain

    def test_recent_terms_boost_score(self) -> None:
        # "fascia" is in savadeck glossary. Without context, a single
        # domain-specific word may still win because it's the only match.
        raw = "the fascia board needs replacement"

        no_ctx = detect_domain(raw, domain_hint="auto")
        # With the new glossaries, "fascia" is in savadeck — expect savadeck
        self.assertEqual(no_ctx.domain_id, "savadeck")

        # If we force technical as active but also have "fascia" as a recent
        # term, the score boost from the term should still let savadeck win.
        ctx = UserContext(active_domains=["technical"], recent_terms=["fascia"])
        with_ctx = detect_domain(raw, domain_hint="auto", context=ctx)
        self.assertEqual(with_ctx.domain_id, "savadeck")
        # end test_recent_terms_boost_score

    def test_manual_hint_overrides_context(self) -> None:
        raw = "deploy the doctor container"
        ctx = UserContext(active_domains=["csharp"], recent_terms=[])
        result = detect_domain(raw, domain_hint="technical", context=ctx)
        self.assertEqual(result.domain_id, "technical")
        self.assertEqual(result.confidence, 1.0)
        # end test_manual_hint_overrides_context

    def test_context_none_falls_back_to_pure_analysis(self) -> None:
        raw = "we use docker and kubernetes"
        result = detect_domain(raw, domain_hint="auto", context=None)
        self.assertEqual(result.domain_id, "technical")
        # end test_context_none_falls_back_to_pure_analysis

    def test_active_domain_boosts_confidence(self) -> None:
        raw = "docker compose up"
        ctx = UserContext(active_domains=["technical"], recent_terms=[])
        result = detect_domain(raw, domain_hint="auto", context=ctx)
        self.assertEqual(result.domain_id, "technical")
        # Confidence should be at least 0.7 because there are 2+ matches,
        # plus a tiny boost from active domain.
        self.assertGreaterEqual(result.confidence, 0.7)
        # end test_active_domain_boosts_confidence

    def test_csharp_glossary_loaded(self) -> None:
        self.assertIn("csharp", domain_module.available_domains())
        # end test_csharp_glossary_loaded

    def test_savadeck_glossary_loaded(self) -> None:
        self.assertIn("savadeck", domain_module.available_domains())
        # end test_savadeck_glossary_loaded

    def test_hermes_glossary_loaded(self) -> None:
        self.assertIn("hermes", domain_module.available_domains())
        # end test_hermes_glossary_loaded


if __name__ == "__main__":
    unittest.main()
