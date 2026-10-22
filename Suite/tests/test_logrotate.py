"""Core: oversized module logs are moved to logs/Archive (never deleted); /assets serves the shell images."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402


class LogRotate(unittest.TestCase):
    def test_big_log_is_archived_not_deleted(self):
        d = Path(tempfile.mkdtemp())
        f = d / "x.log"
        f.write_bytes(b"a" * 2000)
        dest = suite.rotate_log(f, limit=1000)
        self.assertIsNotNone(dest)
        self.assertFalse(f.exists())
        self.assertEqual(dest.read_bytes(), b"a" * 2000)
        self.assertEqual(dest.parent.name, "Archive")

    def test_small_or_missing_log_is_left_alone(self):
        d = Path(tempfile.mkdtemp())
        f = d / "y.log"
        self.assertIsNone(suite.rotate_log(f, limit=1000))
        f.write_bytes(b"a" * 10)
        self.assertIsNone(suite.rotate_log(f, limit=1000))
        self.assertTrue(f.exists())


class Assets(unittest.TestCase):
    def test_logo_served_and_traversal_refused(self):
        r = suite.shell_asset("logo.png")
        self.assertEqual(r.media_type, "image/png")
        for bad in ("..", "x/../../index.html", "nope.png", "index.html"):
            with self.assertRaises(suite.HTTPException):
                suite.shell_asset(bad)


if __name__ == "__main__":
    unittest.main()
