import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import dupe_move  # noqa: E402


class DupeMove(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.data = self.root / "data"
        (self.data / "sources").mkdir(parents=True)
        self.dest = self.root / "to-delete"
        old = time.time() - 3600
        for name, body in (("vod-a.mp4", b"same" * 100), ("vod-b.mp4", b"same" * 100), ("vod-c.mp4", b"same" * 100), ("vod-u.mp4", b"unique" * 100)):
            p = self.data / "sources" / name
            p.write_bytes(body)
            os.utime(p, (old, old))

    def test_plan_keeps_oldest_and_moves_rest(self):
        keep, move, skipped = dupe_move.plan(self.data)
        self.assertEqual(len(keep), 1)
        self.assertEqual(len(move), 2)
        self.assertNotIn("vod-u", " ".join(str(m[0]) for m in move))

    def test_referenced_copy_is_kept_and_not_moved(self):
        keep, move, skipped = dupe_move.plan(self.data, refs=["vod-c"])
        self.assertEqual(keep[0][0].stem, "vod-c")
        self.assertEqual(len(move), 2)
        keep, move, skipped = dupe_move.plan(self.data, refs=["vod-a", "vod-b"])
        self.assertEqual(len(skipped), 1)

    def test_recent_file_is_busy(self):
        os.utime(self.data / "sources" / "vod-b.mp4", None)
        keep, move, skipped = dupe_move.plan(self.data)
        self.assertEqual([s[0].name for s in skipped], ["vod-b.mp4"])

    def test_move_and_restore_round_trip(self):
        keep, move, _ = dupe_move.plan(self.data)
        done = dupe_move.apply(self.data, self.dest, move)
        self.assertEqual(len(done), 2)
        self.assertEqual(len(list((self.data / "sources").glob("*.mp4"))), 2)   # keeper + unique
        self.assertTrue((self.dest / "MANIFEST.txt").read_text("utf8").count("\n") == 2)
        r = subprocess.run([sys.executable, str(self.dest / "restore.py")], capture_output=True, text=True)
        self.assertIn("restored 2", r.stdout, r.stderr)
        self.assertEqual(len(list((self.data / "sources").glob("*.mp4"))), 4)

    def test_restore_never_overwrites(self):
        keep, move, _ = dupe_move.plan(self.data)
        done = dupe_move.apply(self.data, self.dest, move)
        Path(done[0]["original"]).write_bytes(b"new")
        r = subprocess.run([sys.executable, str(self.dest / "restore.py")], capture_output=True, text=True)
        self.assertIn("restored 1", r.stdout)
        self.assertEqual(Path(done[0]["original"]).read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()


class RelativePaths(unittest.TestCase):
    def test_relative_data_dir_still_gives_absolute_manifest(self):
        root = Path(tempfile.mkdtemp())
        (root / "d").mkdir()
        for n in ("a.mp4", "b.mp4"):
            (root / "d" / n).write_bytes(b"x" * 50)
            os.utime(root / "d" / n, (time.time() - 3600,) * 2)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            keep, move, _ = dupe_move.plan("d")
            done = dupe_move.apply("d", "out", move)
        finally:
            os.chdir(cwd)
        self.assertTrue(Path(done[0]["original"]).is_absolute())
        self.assertTrue(Path(done[0]["moved"]).is_absolute())
        r = subprocess.run([sys.executable, str(root / "out" / "restore.py")], capture_output=True, text=True, cwd=str(cwd))
        self.assertIn("restored 1", r.stdout, r.stderr)
