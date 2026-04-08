"""Integration tests verifying the full pipeline flow that both CLI and tray use.

Simulates realistic Whisper output (including common mishearings) and
verifies domain detection, glossary correction, normalisation, and the
final paste-ready output.
"""

from __future__ import annotations

import unittest

from voice_transcriber.config import AppConfig, load_config
from voice_transcriber.models import ProcessingOptions
from voice_transcriber.pipeline import process_transcript


class FullPipelineIntegrationTests(unittest.TestCase):
    """Test the complete pipeline as it would be invoked by transcriber.py
    and tray.py after Whisper returns raw text."""

    def test_technical_transcript_produces_paste_ready_output(self) -> None:
        raw = "we need to deploy the doctor container on aws lamda and connect it to postgres"

        result = process_transcript(
            raw_transcript=raw,
            options=ProcessingOptions(
                language="en",
                domain_hint="auto",
                custom_terms=[],
            ),
        )

        self.assertEqual(result.detected_domain, "technical")
        self.assertIn("Docker", result.final_output)
        self.assertIn("AWS Lambda", result.final_output)
        self.assertIn("PostgreSQL", result.final_output)
        self.assertTrue(result.final_output[0].isupper())
        self.assertTrue(result.final_output.endswith("."))
        self.assertGreater(result.domain_confidence, 0.5)
        # end test_technical_transcript_produces_paste_ready_output

    def test_general_transcript_is_not_overcorrected(self) -> None:
        raw = "hey can you send the meeting notes to the team by end of day"

        result = process_transcript(
            raw_transcript=raw,
            options=ProcessingOptions(
                language="en",
                domain_hint="auto",
                custom_terms=[],
            ),
        )

        self.assertEqual(result.detected_domain, "general")
        self.assertEqual(result.applied_terms, [])
        self.assertTrue(result.final_output[0].isupper())
        self.assertTrue(result.final_output.endswith("."))
        # end test_general_transcript_is_not_overcorrected

    def test_config_driven_options_are_respected(self) -> None:
        config = AppConfig(
            default_model="small",
            default_language="en",
            domain_hint="technical",
            custom_terms=["MyCompanyAPI"],
        )

        raw = "update the my company a p i endpoint to use the new docker image"
        result = process_transcript(
            raw_transcript=raw,
            options=ProcessingOptions(
                language=config.default_language,
                domain_hint=config.domain_hint,
                custom_terms=config.custom_terms,
            ),
        )

        self.assertEqual(result.detected_domain, "technical")
        self.assertEqual(result.domain_confidence, 1.0)
        self.assertIn("Docker", result.final_output)
        # end test_config_driven_options_are_respected

    def test_custom_terms_integrate_with_glossary(self) -> None:
        raw = "refactor the kube config parser and deploy to aws lamda"
        result = process_transcript(
            raw_transcript=raw,
            options=ProcessingOptions(
                language="en",
                domain_hint="auto",
                custom_terms=["kube-config-parser"],
            ),
        )

        self.assertEqual(result.detected_domain, "technical")
        self.assertIn("AWS Lambda", result.final_output)
        # end test_custom_terms_integrate_with_glossary

    def test_whisper_style_mishearings_are_corrected(self) -> None:
        samples = [
            ("we use cooper netties for orchestration", "Kubernetes"),
            ("check the git hub repository", "GitHub"),
            ("write it in type script", "TypeScript"),
            ("the sequel database is down", "SQL"),
            ("deploy with terra form", "Terraform"),
        ]
        for raw, expected_term in samples:
            with self.subTest(raw=raw):
                result = process_transcript(
                    raw_transcript=raw,
                    options=ProcessingOptions(
                        language="en",
                        domain_hint="technical",
                    ),
                )
                self.assertIn(expected_term, result.final_output)
        # end test_whisper_style_mishearings_are_corrected

    def test_empty_and_whitespace_only_transcripts(self) -> None:
        for raw in ("", "   ", "\n\t"):
            with self.subTest(raw=repr(raw)):
                result = process_transcript(
                    raw_transcript=raw,
                    options=ProcessingOptions(language="en"),
                )
                self.assertEqual(result.final_output, "")
                self.assertIn("Transcription was empty.", result.warnings)
        # end test_empty_and_whitespace_only_transcripts

    def test_domain_override_via_cli_flag(self) -> None:
        raw = "send the doctor report by Friday"
        result = process_transcript(
            raw_transcript=raw,
            options=ProcessingOptions(
                language="en",
                domain_hint="technical",
                custom_terms=[],
            ),
        )

        self.assertIn("Docker", result.final_output)
        self.assertEqual(result.domain_confidence, 1.0)

        result_general = process_transcript(
            raw_transcript=raw,
            options=ProcessingOptions(
                language="en",
                domain_hint="general",
                custom_terms=[],
            ),
        )
        self.assertNotIn("Docker", result_general.final_output)
        self.assertIn("doctor", result_general.final_output.lower())
        # end test_domain_override_via_cli_flag


if __name__ == "__main__":
    unittest.main()
