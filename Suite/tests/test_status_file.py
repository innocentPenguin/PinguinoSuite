"""Data/runtime/status.json: restart and health-miss counts readable without the API token."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402
from test_shutdown import _Base  # noqa: E402


class StatusFile(_Base):
    def test_counts_are_written(self):
        self._up()
        m = self.mods[0][0]
        m.refresh()
        suite.write_status()
        d = json.loads((Path(suite.DATA_DIR) / "status.json").read_text("utf8"))
        row = d["modules"][m.id]
        self.assertGreaterEqual(row["starts"], 1)
        self.assertEqual(row["downs"], 0)
        self.assertEqual(row["miss_now"], 0)
        self.assertIn("core_since", d)
        self.assertNotIn("token", json.dumps(d).lower())

    def test_a_missed_ping_is_counted(self):
        self._up()
        m = self.mods[0][0]
        m.stop()
        m.wanted = False
        m.refresh()
        self.assertGreaterEqual(m.misses_total, 1)


if __name__ == "__main__":
    unittest.main()
