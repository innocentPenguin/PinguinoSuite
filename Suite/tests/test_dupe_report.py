import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import dupe_report  # noqa: E402


class Dupes(unittest.TestCase):
    def test_finds_identical_files_ignores_same_size_different_content_and_deletes_nothing(self):
        d = Path(tempfile.mkdtemp())
        (d / "sub").mkdir()
        (d / "a.mp4").write_bytes(b"x" * 1000)
        (d / "sub" / "b.mp4").write_bytes(b"x" * 1000)
        (d / "c.mp4").write_bytes(b"y" * 1000)          # same size, different bytes
        (d / "d.mp4").write_bytes(b"z" * 5)             # unique size
        (d / "e.txt").write_bytes(b"x" * 1000)          # not a video
        before = sorted(p.name for p in d.rglob("*"))
        g = dupe_report.find_groups(d)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0][0], 1000)
        self.assertEqual([p.name for p in g[0][1]], ["a.mp4", "b.mp4"])
        self.assertIn("reclaimable: 0.00 GB", dupe_report.render(d, g))
        self.assertEqual(before, sorted(p.name for p in d.rglob("*")))

    def test_hashes_only_files_that_share_a_size(self):
        d = Path(tempfile.mkdtemp())
        (d / "a.mp4").write_bytes(b"1" * 10)
        (d / "b.mp4").write_bytes(b"2" * 20)
        seen = []
        dupe_report.find_groups(d, hasher=lambda p: seen.append(p) or "h")
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
