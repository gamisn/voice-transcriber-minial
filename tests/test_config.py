from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_transcriber.config import AppConfig, load_config, save_config


class ConfigRoundTripTests(unittest.TestCase):
    def test_save_and_load_preserves_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "config.json"
            with (
                patch("voice_transcriber.config.CONFIG_DIR", tmp_path.parent),
                patch("voice_transcriber.config.CONFIG_PATH", tmp_path),
            ):
                config = AppConfig(
                    default_model="small",
                    default_language="de",
                    domain_hint="technical",
                    custom_terms=["AWS", "aws", "Kubernetes"],
                )
                save_config(config)
                reloaded = load_config()

        self.assertEqual(reloaded.default_model, "small")
        self.assertEqual(reloaded.default_language, "de")
        self.assertEqual(reloaded.domain_hint, "technical")
        self.assertEqual(reloaded.custom_terms, ["AWS", "Kubernetes"])
        # end test_save_and_load_preserves_values

    def test_load_returns_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "nonexistent.json"
            with patch("voice_transcriber.config.CONFIG_PATH", tmp_path):
                config = load_config()

        self.assertEqual(config.default_model, "base")
        self.assertEqual(config.default_language, "en")
        self.assertEqual(config.domain_hint, "auto")
        self.assertEqual(config.custom_terms, [])
        # end test_load_returns_defaults_when_missing

    def test_load_returns_defaults_on_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "config.json"
            tmp_path.write_text("{invalid json")
            with (
                patch("voice_transcriber.config.CONFIG_DIR", tmp_path.parent),
                patch("voice_transcriber.config.CONFIG_PATH", tmp_path),
            ):
                config = load_config()

        self.assertEqual(config.default_model, "base")
        # end test_load_returns_defaults_on_malformed_json

    def test_custom_terms_normalization_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "config.json"
            with (
                patch("voice_transcriber.config.CONFIG_DIR", tmp_path.parent),
                patch("voice_transcriber.config.CONFIG_PATH", tmp_path),
            ):
                config = AppConfig(custom_terms=["Docker", "docker", "  Docker  ", ""])
                save_config(config)
                reloaded = load_config()

        self.assertEqual(reloaded.custom_terms, ["Docker"])
        # end test_custom_terms_normalization_deduplicates


if __name__ == "__main__":
    unittest.main()
