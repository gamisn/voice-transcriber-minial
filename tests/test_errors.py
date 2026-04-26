from __future__ import annotations

import pathlib
import unittest
from unittest.mock import patch

from voice_transcriber import errors


class LogRecordingFailureTests(unittest.TestCase):
    def test_summary_includes_type_and_message(self) -> None:
        try:
            raise ValueError("bad value")
        except ValueError as exc:
            with patch.object(errors, "_CACHE_DIR", pathlib.Path("/tmp/vt-test-cache")), \
                 patch.object(errors, "_ERROR_LOG", pathlib.Path("/tmp/vt-test-cache/error.log")):
                summary = errors.log_recording_failure("unit_test", exc)

        self.assertIn("ValueError", summary)
        self.assertIn("bad value", summary)
        self.assertTrue(summary.startswith("unit_test:"))
        # end test_summary_includes_type_and_message

    def test_summary_falls_back_to_class_name_when_message_empty(self) -> None:
        try:
            raise RuntimeError()
        except RuntimeError as exc:
            with patch.object(errors, "_CACHE_DIR", pathlib.Path("/tmp/vt-test-cache")), \
                 patch.object(errors, "_ERROR_LOG", pathlib.Path("/tmp/vt-test-cache/error.log")):
                summary = errors.log_recording_failure("unit_test", exc)

        self.assertEqual(summary, "unit_test: RuntimeError")
        # end test_summary_falls_back_to_class_name_when_message_empty

    def test_writes_traceback_to_log_file(self) -> None:
        with self._tmp_log() as log_path:
            try:
                raise KeyError("missing")
            except KeyError as exc:
                errors.log_recording_failure("disk_test", exc)

            content = log_path.read_text()

        self.assertIn("stage=disk_test", content)
        self.assertIn("KeyError", content)
        self.assertIn("Traceback", content)
        # end test_writes_traceback_to_log_file

    def _tmp_log(self) -> "pathlib.Path":
        import tempfile

        class _LogContext:
            def __enter__(_self) -> pathlib.Path:
                _self._tmp = tempfile.TemporaryDirectory()
                tmp_dir = pathlib.Path(_self._tmp.name)
                _self._patches = [
                    patch.object(errors, "_CACHE_DIR", tmp_dir),
                    patch.object(errors, "_ERROR_LOG", tmp_dir / "error.log"),
                ]
                for p in _self._patches:
                    p.start()
                return tmp_dir / "error.log"

            def __exit__(_self, *args: object) -> None:
                for p in _self._patches:
                    p.stop()
                _self._tmp.cleanup()

        return _LogContext()
        # end _tmp_log


if __name__ == "__main__":
    unittest.main()
