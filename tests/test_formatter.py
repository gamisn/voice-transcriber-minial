from __future__ import annotations

import unittest

from voice_transcriber.formatter import normalize_transcript


class NormalizeTranscriptTests(unittest.TestCase):
    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(normalize_transcript(""), "")
        self.assertEqual(normalize_transcript("   "), "")
        # end test_empty_input_returns_empty

    def test_collapses_whitespace_and_capitalizes(self) -> None:
        self.assertEqual(
            normalize_transcript("  hello   world  "),
            "Hello world.",
        )
        # end test_collapses_whitespace_and_capitalizes

    def test_adds_trailing_period_when_missing(self) -> None:
        self.assertEqual(normalize_transcript("hello world"), "Hello world.")
        # end test_adds_trailing_period_when_missing

    def test_preserves_existing_terminator(self) -> None:
        self.assertEqual(normalize_transcript("hello world!"), "Hello world!")
        self.assertEqual(normalize_transcript("hello world?"), "Hello world?")
        # end test_preserves_existing_terminator

    def test_capitalizes_after_period(self) -> None:
        self.assertEqual(
            normalize_transcript("hello world. how are you"),
            "Hello world. How are you.",
        )
        # end test_capitalizes_after_period

    def test_capitalizes_after_question_mark(self) -> None:
        self.assertEqual(
            normalize_transcript("hello? are you there"),
            "Hello? Are you there.",
        )
        # end test_capitalizes_after_question_mark

    def test_capitalizes_after_exclamation(self) -> None:
        self.assertEqual(
            normalize_transcript("wow! that is great"),
            "Wow! That is great.",
        )
        # end test_capitalizes_after_exclamation

    def test_handles_multiple_sentences(self) -> None:
        self.assertEqual(
            normalize_transcript("first sentence. second sentence. third one"),
            "First sentence. Second sentence. Third one.",
        )
        # end test_handles_multiple_sentences

    def test_preserves_already_capitalized_terms(self) -> None:
        # Glossary corrections produce mixed case — normalizer must not
        # downcase mid-sentence proper nouns.
        self.assertEqual(
            normalize_transcript("deploy Docker on AWS Lambda"),
            "Deploy Docker on AWS Lambda.",
        )
        # end test_preserves_already_capitalized_terms


if __name__ == "__main__":
    unittest.main()
