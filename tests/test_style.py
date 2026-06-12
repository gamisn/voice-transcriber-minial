"""Tests for Phase 4: Style Learning — style profile generation and formatting.

Covers:
- style.build_profile_from_samples: formality, contractions, sentence length
- style.StyleProfile: round-trip dict serialization
- style_formatter.apply_style: capitalizes_i, contractions, trailing period
- style_corpus: sample collection and profile building (integration-ish)
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from voice_transcriber import style as style_module
from voice_transcriber import style_formatter as formatter_module


class StyleProfileTests(unittest.TestCase):
    """Style profile analysis from writing samples."""

    def test_casual_sample_detects_casual_style(self) -> None:
        """Casual chat should produce low formality, contractions enabled."""
        samples = [
            "Hey, what's up? I wanted to check if you're free tomorrow. Let me know!",
            "Yeah, I'm gonna be there. Don't worry about it.",
        ]
        profile = style_module.build_profile_from_samples(samples)

        self.assertLess(profile.formality, 0.5)
        self.assertTrue(profile.uses_contractions)
        self.assertTrue(profile.capitalizes_i)
        self.assertTrue(profile.trailing_period)
        # end test_casual_sample_detects_casual_style

    def test_formal_sample_detects_formal_style(self) -> None:
        """Business email should produce high formality, contractions disabled."""
        samples = [
            "Dear John, I am writing to follow up on the project discussed last week.",
            "Furthermore, we would like to schedule a meeting. Sincerely, Jane.",
        ]
        profile = style_module.build_profile_from_samples(samples)

        self.assertGreater(profile.formality, 0.5)
        self.assertFalse(profile.uses_contractions)
        # end test_formal_sample_detects_formal_style

    def test_empty_samples_return_default_profile(self) -> None:
        """No samples should return a safe default profile."""
        profile = style_module.build_profile_from_samples([])
        self.assertEqual(profile.formality, 0.5)
        self.assertTrue(profile.capitalizes_i)
        # end test_empty_samples_return_default_profile

    def test_profile_round_trip_dict(self) -> None:
        """Profile serializes and deserializes correctly."""
        original = style_module.StyleProfile(
            formality=0.3,
            capitalizes_i=False,
            uses_contractions=True,
            avg_sentence_length=8.5,
            trailing_period=False,
            greeting_style="casual",
            lowercase_fragments=True,
        )
        data = original.to_dict()
        restored = style_module.StyleProfile.from_dict(data)
        self.assertEqual(original.formality, restored.formality)
        self.assertEqual(original.capitalizes_i, restored.capitalizes_i)
        self.assertEqual(original.uses_contractions, restored.uses_contractions)
        self.assertEqual(original.avg_sentence_length, restored.avg_sentence_length)
        self.assertEqual(original.trailing_period, restored.trailing_period)
        self.assertEqual(original.greeting_style, restored.greeting_style)
        self.assertEqual(original.lowercase_fragments, restored.lowercase_fragments)
        # end test_profile_round_trip_dict

    def test_save_and_load_style_profile(self) -> None:
        """Profile persists to disk and reloads."""
        with tempfile.TemporaryDirectory() as td:
            orig_path = style_module._STYLE_PATH
            style_module._STYLE_PATH = pathlib.Path(td) / "style.json"

            profile = style_module.StyleProfile(
                formality=0.7,
                capitalizes_i=True,
                uses_contractions=False,
            )
            style_module.save_style_profile(profile)
            loaded = style_module.load_style_profile()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.formality, 0.7)
            self.assertEqual(loaded.capitalizes_i, True)
            self.assertEqual(loaded.uses_contractions, False)

            style_module._STYLE_PATH = orig_path
        # end test_save_and_load_style_profile


class StyleFormatterTests(unittest.TestCase):
    """Style-aware formatting rules."""

    def test_capitalize_i_enabled(self) -> None:
        profile = style_module.StyleProfile(capitalizes_i=True, uses_contractions=False)
        result = formatter_module.apply_style("hello i will go", profile)
        self.assertIn("I will", result)
        # end test_capitalize_i_enabled

    def test_capitalize_i_disabled(self) -> None:
        profile = style_module.StyleProfile(capitalizes_i=False, uses_contractions=False)
        result = formatter_module.apply_style("Hello i will go", profile)
        self.assertIn("i will", result)
        # end test_capitalize_i_disabled

    def test_contractions_enabled(self) -> None:
        profile = style_module.StyleProfile(uses_contractions=True)
        result = formatter_module.apply_style("I am going to the store. Do not forget.", profile)
        # After contraction expansion + sentence capitalization
        self.assertIn("I'm", result)
        self.assertIn("Don't", result)
        # end test_contractions_enabled

    def test_contractions_disabled(self) -> None:
        profile = style_module.StyleProfile(uses_contractions=False)
        result = formatter_module.apply_style("I'm going. Don't forget.", profile)
        # After contraction expansion + sentence capitalization
        self.assertIn("I am", result)
        self.assertIn("Do not", result)
        # end test_contractions_disabled

    def test_trailing_period_enabled(self) -> None:
        profile = style_module.StyleProfile(trailing_period=True)
        result = formatter_module.apply_style("hello world", profile)
        self.assertTrue(result.endswith("."))
        # end test_trailing_period_enabled

    def test_trailing_period_disabled(self) -> None:
        profile = style_module.StyleProfile(trailing_period=False)
        result = formatter_module.apply_style("hello world.", profile)
        self.assertFalse(result.endswith("."))
        # end test_trailing_period_disabled

    def test_lowercase_fragments_enabled(self) -> None:
        profile = style_module.StyleProfile(lowercase_fragments=True)
        result = formatter_module.apply_style("ok. Hello world.", profile)
        self.assertIn("ok", result)
        # "Hello world" has 2 words → treated as fragment → lowercased
        self.assertIn("hello world", result)
        # end test_lowercase_fragments_enabled

    def test_no_profile_returns_text_unchanged(self) -> None:
        result = formatter_module.apply_style("hello i am here", None)
        self.assertEqual(result, "hello i am here")
        # end test_no_profile_returns_text_unchanged


if __name__ == "__main__":
    unittest.main()
