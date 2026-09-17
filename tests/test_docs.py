"""Documentation consistency tests (issue #3).

The README is the user-facing contract: every config key the app reads,
every CLI flag it ships, and every data file it creates must be documented
there. These tests keep the docs aligned with the implementation so new
modes and keys cannot land silently undocumented.
"""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


class ConfigDocumentationTests(unittest.TestCase):
    def test_readme_documents_config_file_location(self) -> None:
        self.assertIn("~/.config/voice-transcriber/config.json", _README)
        # end test_readme_documents_config_file_location

    def test_readme_documents_every_config_key(self) -> None:
        for key in (
            "default_model",
            "default_language",
            "domain_hint",
            "custom_terms",
            "context_enabled",
            "auto_glossary",
            "style_enabled",
        ):
            with self.subTest(key=key):
                self.assertIn(key, _README)
        # end test_readme_documents_every_config_key

    def test_readme_documents_defaults_application(self) -> None:
        self.assertIn("CLI flags always override config values", _README)
        # end test_readme_documents_defaults_application


class AdvancedWorkflowDocumentationTests(unittest.TestCase):
    def test_readme_documents_review_flow(self) -> None:
        self.assertIn("--review", _README)
        # end test_readme_documents_review_flow

    def test_readme_documents_style_learning_flow(self) -> None:
        self.assertIn("--learn-style", _README)
        self.assertIn("style.json", _README)
        # end test_readme_documents_style_learning_flow

    def test_readme_documents_context_file(self) -> None:
        self.assertIn("context.json", _README)
        # end test_readme_documents_context_file

    def test_readme_documents_transcript_history(self) -> None:
        self.assertIn("history.db", _README)
        # end test_readme_documents_transcript_history

    def test_readme_does_not_document_email_mode(self) -> None:
        lowered = _README.lower()
        self.assertNotIn("email mode", lowered)
        self.assertNotIn("email-mode", lowered)
        # end test_readme_does_not_document_email_mode


if __name__ == "__main__":
    unittest.main()