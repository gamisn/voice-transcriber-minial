from __future__ import annotations

import unittest

from voice_transcriber.models import ProcessingOptions
from voice_transcriber.pipeline import process_transcript


class PipelineTests(unittest.TestCase):
    def test_technical_terms_are_corrected(self) -> None:
        result = process_transcript(
            raw_transcript="deploy this on doctor with aws lamda and postgres",
            options=ProcessingOptions(language="en"),
        )

        self.assertEqual(result.detected_domain, "technical")
        self.assertIn("Docker", result.corrected_transcript)
        self.assertIn("AWS Lambda", result.corrected_transcript)
        self.assertIn("PostgreSQL", result.corrected_transcript)
        # end test_technical_terms_are_corrected

    def test_general_domain_leaves_text_intact(self) -> None:
        result = process_transcript(
            raw_transcript="please send the report to the client tomorrow morning",
            options=ProcessingOptions(language="en"),
        )

        self.assertEqual(result.detected_domain, "general")
        self.assertEqual(result.applied_terms, [])
        self.assertEqual(
            result.final_output,
            "Please send the report to the client tomorrow morning.",
        )
        # end test_general_domain_leaves_text_intact

    def test_manual_domain_hint_overrides_detection(self) -> None:
        result = process_transcript(
            raw_transcript="deploy doctor on the server",
            options=ProcessingOptions(language="en", domain_hint="technical"),
        )

        self.assertEqual(result.detected_domain, "technical")
        self.assertEqual(result.domain_confidence, 1.0)
        self.assertIn("Docker", result.corrected_transcript)
        # end test_manual_domain_hint_overrides_detection

    def test_custom_terms_applied(self) -> None:
        result = process_transcript(
            raw_transcript="we need to update the my-custom-lib for the release",
            options=ProcessingOptions(
                language="en",
                custom_terms=["my-custom-lib"],
            ),
        )

        self.assertIn("my-custom-lib", result.final_output)
        # end test_custom_terms_applied

    def test_empty_transcript_warns(self) -> None:
        result = process_transcript(
            raw_transcript="   ",
            options=ProcessingOptions(language="en"),
        )

        self.assertIn("Transcription was empty.", result.warnings)
        self.assertEqual(result.final_output, "")
        # end test_empty_transcript_warns

    def test_output_is_normalized(self) -> None:
        result = process_transcript(
            raw_transcript="  hello   world  ",
            options=ProcessingOptions(language="en"),
        )

        self.assertEqual(result.final_output, "Hello world.")
        # end test_output_is_normalized


if __name__ == "__main__":
    unittest.main()
