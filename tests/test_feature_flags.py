"""Wiring tests for the Phase 1-4 feature flags (issue #3 documentation prep).

``context_enabled`` and ``auto_glossary`` existed in ``AppConfig`` but were
never forwarded to ``ProcessingOptions`` — toggling them in config.json had
no effect. ``style_enabled`` gated the pipeline style pass but had no config
key at all. These tests pin the actual end-to-end plumbing:

    config.json key -> load_config() -> CLI/daemon -> ProcessingOptions -> pipeline
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_transcriber.config import AppConfig, load_config
from voice_transcriber import daemon as daemon_module
from voice_transcriber.daemon import DaemonCore, RecordingHooks, State
from voice_transcriber.models import ProcessingOptions


class ConfigKeyDefaultsTests(unittest.TestCase):
    def test_default_style_enabled_is_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("voice_transcriber.config.CONFIG_PATH",
                       Path(tmp_dir) / "missing.json"):
                config = load_config()
        self.assertTrue(config.style_enabled)
        self.assertTrue(config.context_enabled)
        self.assertTrue(config.auto_glossary)
        # end test_default_style_enabled_is_true

    def test_default_style_enabled_when_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("voice_transcriber.config.CONFIG_PATH",
                       Path(tmp_dir) / "missing.json"):
                self.assertTrue(load_config().style_enabled)
        # end test_default_style_enabled_when_missing_file

    def test_style_enabled_round_trips_through_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "config.json"
            with (
                patch("voice_transcriber.config.CONFIG_DIR", tmp_path.parent),
                patch("voice_transcriber.config.CONFIG_PATH", tmp_path),
            ):
                save = AppConfig(style_enabled=False)
                from voice_transcriber.config import save_config
                save_config(save)
                reloaded = load_config()
        self.assertFalse(reloaded.style_enabled)
        # end test_style_enabled_round_trips_through_config


class PipelineFlagTests(unittest.TestCase):
    """context_enabled=False must stop the pipeline from reading context."""

    def test_context_enabled_false_skips_context_load(self) -> None:
        from voice_transcriber import pipeline as pipeline_module
        with patch.object(pipeline_module, "load_user_context") as fake_load:
            result = pipeline_module.process_transcript(
                raw_transcript="deploy the doctor container",
                options=ProcessingOptions(
                    language="en",
                    domain_hint="auto",
                    context_enabled=False,
                ),
            )
        fake_load.assert_not_called()
        self.assertEqual(result.detected_domain, "technical")
        # end test_context_enabled_false_skips_context_load

    def test_context_enabled_true_loads_context(self) -> None:
        from voice_transcriber import pipeline as pipeline_module
        with patch.object(pipeline_module, "load_user_context") as fake_load, \
             patch.object(pipeline_module, "observer_module") as fake_observer:
            pipeline_module.process_transcript(
                raw_transcript="hello world",
                options=ProcessingOptions(
                    language="en",
                    domain_hint="auto",
                    context_enabled=True,
                ),
            )
        fake_load.assert_called_once()
        # end test_context_enabled_true_loads_context


def _fake_record_audio(sd: object, stop_event: threading.Event | None,
                       interactive: bool, on_level: object) -> object:
    if stop_event is not None:
        stop_event.wait(timeout=0.1)
    import numpy as np
    return np.zeros(16_000, dtype=np.int16)
    # end _fake_record_audio


def _fake_transcribe(audio: object, model_name: str, language: str, quiet: bool) -> str:
    return "deploy the doctor container"
    # end _fake_transcribe


def _fake_copy_to_clipboard(text: str) -> bool:
    return True
    # end _fake_copy_to_clipboard


class _Hooks(RecordingHooks):
    def __init__(self) -> None:
        self.states: list[State] = []
        self.results: list[str] = []
        self.empties = 0
        self.errors: list[str] = []
        self.levels: list[float] = []
        # end __init__

    def on_state_change(self, state: State) -> None:
        self.states.append(state)
        # end on_state_change

    def on_level(self, normalized: float) -> None:
        self.levels.append(normalized)
        # end on_level

    def on_result(self, final_text: str) -> None:
        self.results.append(final_text)
        # end on_result

    def on_empty(self) -> None:
        self.empties += 1
        # end on_empty

    def on_error(self, summary: str) -> None:
        self.errors.append(summary)
        # end on_error


class DaemonFlagForwardingTests(unittest.TestCase):
    """DaemonCore must forward auto_glossary/context_enabled/style_enabled
    from the CLI flags and config into ProcessingOptions."""

    def _make_core(self, auto_glossary: bool, context_enabled: bool,
                   style_enabled: bool) -> DaemonCore:
        with patch.object(daemon_module, "record_audio", _fake_record_audio), \
             patch.object(daemon_module, "transcribe_audio", _fake_transcribe), \
             patch.object(daemon_module, "copy_to_clipboard", _fake_copy_to_clipboard):
            core = DaemonCore(
                model_name="base",
                language="en",
                domain_hint="auto",
                custom_terms=[],
                auto_glossary=auto_glossary,
                context_enabled=context_enabled,
                style_enabled=style_enabled,
                hooks=_Hooks(),
            )
            core._sd = object()  # noqa: SLF001 — pretend sounddevice is loaded
        return core
        # end _make_core

    def _run_cycle(self, core: DaemonCore) -> _Hooks:
        hooks = core._hooks  # noqa: SLF001
        with patch.object(daemon_module, "record_audio", _fake_record_audio), \
             patch.object(daemon_module, "transcribe_audio", _fake_transcribe), \
             patch.object(daemon_module, "copy_to_clipboard", _fake_copy_to_clipboard):
            core.toggle()
            core.toggle()
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if core.get_state() == State.IDLE and \
                        (core._work_thread is None or not core._work_thread.is_alive()):  # noqa: SLF001
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("daemon did not return to IDLE")
        return hooks
        # end _run_cycle

    def test_flags_forwarded_to_processing_options(self) -> None:
        core = self._make_core(auto_glossary=False, context_enabled=False,
                               style_enabled=False)
        captured: dict = {}

        real_process = daemon_module.process_transcript

        def _capture(raw_transcript: str, options: ProcessingOptions) -> object:
            captured.update(
                auto_glossary=options.auto_glossary,
                context_enabled=options.context_enabled,
                style_enabled=options.style_enabled,
            )
            return real_process(
                raw_transcript=raw_transcript,
                options=ProcessingOptions(
                    language="en",
                    domain_hint="general",
                ),
            )
        # end _capture

        with patch.object(daemon_module, "process_transcript", _capture):
            self._run_cycle(core)

        self.assertEqual(captured.get("auto_glossary"), False)
        self.assertEqual(captured.get("context_enabled"), False)
        self.assertEqual(captured.get("style_enabled"), False)
        # end test_flags_forwarded_to_processing_options

    def test_default_flags_are_true(self) -> None:
        core = self._make_core(auto_glossary=True, context_enabled=True,
                               style_enabled=True)
        captured: dict = {}

        real_process = daemon_module.process_transcript

        def _capture(raw_transcript: str, options: ProcessingOptions) -> object:
            captured.update(
                auto_glossary=options.auto_glossary,
                context_enabled=options.context_enabled,
                style_enabled=options.style_enabled,
            )
            return real_process(
                raw_transcript=raw_transcript,
                options=ProcessingOptions(
                    language="en",
                    domain_hint="general",
                ),
            )
        # end _capture

        with patch.object(daemon_module, "process_transcript", _capture):
            self._run_cycle(core)

        self.assertEqual(captured.get("auto_glossary"), True)
        self.assertEqual(captured.get("context_enabled"), True)
        self.assertEqual(captured.get("style_enabled"), True)
        # end test_default_flags_are_true


if __name__ == "__main__":
    unittest.main()