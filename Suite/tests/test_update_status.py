"""Core: /api/update/status reads what the PinguinoUpdater wrote (read-only; missing files are fine)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402


class UpdateStatus(unittest.TestCase):
    def test_nothing_written_yet(self):
        root = Path(tempfile.mkdtemp())
        s = suite.read_update_status(root / "Data" / "updates")
        self.assertEqual(s, {"version": None, "result": None, "deferred": None})

    def test_reads_result_deferred_and_version(self):
        root = Path(tempfile.mkdtemp())
        up = root / "Data" / "updates"
        up.mkdir(parents=True)
        (up / "update_result.json").write_text(json.dumps({"ok": True, "message": "updated 1.0.0 -> 1.1.0"}))
        (up / "update_deferred.json").write_text(json.dumps({"to": "1.2.0", "reason": "you are live"}))
        (root / "install.json").write_text(json.dumps({"version": "1.1.0"}))
        s = suite.read_update_status(up)
        self.assertEqual(s["version"], "1.1.0")
        self.assertTrue(s["result"]["ok"])
        self.assertEqual(s["deferred"]["to"], "1.2.0")

    def test_damaged_file_is_ignored(self):
        root = Path(tempfile.mkdtemp())
        up = root / "Data" / "updates"
        up.mkdir(parents=True)
        (up / "update_result.json").write_text("{not json")
        self.assertIsNone(suite.read_update_status(up)["result"])


if __name__ == "__main__":
    unittest.main()
