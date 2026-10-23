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


class Caps(unittest.TestCase):
    def test_archive_is_gzipped_and_nothing_lost(self):
        import gzip
        d = Path(tempfile.mkdtemp()) / "Archive"
        d.mkdir()
        (d / "a-1.log").write_bytes(b"line\n" * 5000)
        (d / "keep.txt").write_bytes(b"x")
        self.assertEqual(suite.pack_archive(d), 1)
        self.assertFalse((d / "a-1.log").exists())
        self.assertEqual(gzip.open(d / "a-1.log.gz").read(), b"line\n" * 5000)
        self.assertTrue((d / "keep.txt").exists())
        self.assertEqual(suite.pack_archive(d), 0)     # nothing left to pack
        self.assertEqual(suite.pack_archive(d / "missing"), 0)

    def test_running_module_log_past_the_warn_size_is_flagged_once(self):
        saved = suite.LOGS
        suite.LOGS = Path(tempfile.mkdtemp())
        try:
            (suite.LOGS / "big.log").write_bytes(b"a" * 3000)
            (suite.LOGS / "small.log").write_bytes(b"a" * 10)
            self.assertEqual([n for n, _ in suite.oversized_logs(limit=1000)], ["big.log"])
            seen = []
            orig = suite.console_log.log
            suite.console_log.log = lambda *a, **k: seen.append(a)
            suite.LOG_WARN = 1000
            try:
                w = {}
                suite.log_watch(w)
                suite.log_watch(w)
                self.assertEqual(len(seen), 1)
                self.assertIn("big.log", seen[0][2])
            finally:
                suite.console_log.log = orig
                suite.LOG_WARN = 3 * suite.LOG_MAX
        finally:
            suite.LOGS = saved

    def test_console_logs_rotate_at_their_cap_and_stay_bounded(self):
        import consolelog
        d = Path(tempfile.mkdtemp())
        c = consolelog.Console(d / "console", d, max_bytes=500, keep=2)
        p = d / "console" / "m.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(4):
            p.write_bytes(b"x" * 600)
            c._maybe_rotate(p)
        self.assertFalse(p.exists())
        self.assertTrue((d / "console" / "m.jsonl.1").exists())
        self.assertTrue((d / "console" / "m.jsonl.2").exists())
        self.assertFalse((d / "console" / "m.jsonl.3").exists())    # keep=2: older ones fall off


class Assets(unittest.TestCase):
    def test_logo_served_and_traversal_refused(self):
        r = suite.shell_asset("logo.png")
        self.assertEqual(r.media_type, "image/png")
        for bad in ("..", "x/../../index.html", "nope.png", "index.html"):
            with self.assertRaises(suite.HTTPException):
                suite.shell_asset(bad)


if __name__ == "__main__":
    unittest.main()
