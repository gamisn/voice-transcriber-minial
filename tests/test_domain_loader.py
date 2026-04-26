"""Tests for the JSON-based glossary loader.

These tests redirect ``_GLOSSARY_DIR`` to a temp dir to verify the loader
picks up arbitrary ``*.json`` files as domains, while leaving the production
glossary alone.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_transcriber import domain as domain_module


def _reset_cache() -> None:
    domain_module._glossary_cache.clear()
    # end _reset_cache


class DataDrivenGlossaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        self._patcher = patch.object(domain_module, "_GLOSSARY_DIR", self._tmp_path)
        self._patcher.start()
        _reset_cache()
        # end setUp

    def tearDown(self) -> None:
        self._patcher.stop()
        _reset_cache()
        self._tmp.cleanup()
        # end tearDown

    def _write(self, name: str, payload: dict) -> None:
        (self._tmp_path / name).write_text(json.dumps(payload))
        # end _write

    def test_available_domains_lists_json_files(self) -> None:
        self._write("foo.json", {"domain_id": "foo", "keywords": [], "entries": []})
        self._write("bar.json", {"domain_id": "bar", "keywords": [], "entries": []})

        self.assertEqual(domain_module.available_domains(), ["bar", "foo"])
        # end test_available_domains_lists_json_files

    def test_keywords_drive_auto_detection(self) -> None:
        self._write(
            "medical.json",
            {
                "domain_id": "medical",
                "keywords": ["mri", "patient"],
                "entries": [],
            },
        )
        self._write(
            "tech.json",
            {
                "domain_id": "tech",
                "keywords": ["docker", "kubernetes"],
                "entries": [],
            },
        )

        match = domain_module.detect_domain("schedule the patient mri", "auto")
        self.assertEqual(match.domain_id, "medical")
        self.assertEqual(match.keywords, ["mri", "patient"])
        # end test_keywords_drive_auto_detection

    def test_entries_apply_corrections(self) -> None:
        self._write(
            "tech.json",
            {
                "domain_id": "tech",
                "keywords": ["docker"],
                "entries": [
                    {"canonical": "Docker", "aliases": ["doctor"]},
                ],
            },
        )

        match = domain_module.detect_domain("docker doctor compose", "auto")
        corrected, applied = domain_module.apply_glossary(
            "docker doctor compose", match, custom_terms=[],
        )
        self.assertEqual(corrected, "Docker Docker compose")
        self.assertEqual(applied, ["Docker"])
        # end test_entries_apply_corrections

    def test_missing_domain_id_raises(self) -> None:
        self._write("broken.json", {"domain_id": "", "keywords": [], "entries": []})
        with self.assertRaises(ValueError):
            domain_module.available_domains()
        # end test_missing_domain_id_raises

    def test_invalid_keywords_field_raises(self) -> None:
        self._write("broken.json", {"domain_id": "x", "keywords": "nope"})
        with self.assertRaises(ValueError):
            domain_module.available_domains()
        # end test_invalid_keywords_field_raises


class ProductionGlossaryRegressionTests(unittest.TestCase):
    """Sanity checks against the real ``technical.json`` shipped in the repo."""

    def setUp(self) -> None:
        _reset_cache()
        # end setUp

    def tearDown(self) -> None:
        _reset_cache()
        # end tearDown

    def test_technical_glossary_is_loaded(self) -> None:
        self.assertIn("technical", domain_module.available_domains())
        # end test_technical_glossary_is_loaded

    def test_classic_doctor_to_docker_correction_still_works(self) -> None:
        match = domain_module.detect_domain("deploy docker on aws", "auto")
        self.assertEqual(match.domain_id, "technical")
        corrected, applied = domain_module.apply_glossary(
            "deploy doctor on aws", match, custom_terms=[],
        )
        self.assertIn("Docker", corrected)
        self.assertIn("AWS", corrected)
        # end test_classic_doctor_to_docker_correction_still_works


if __name__ == "__main__":
    unittest.main()
