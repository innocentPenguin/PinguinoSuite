import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import wer_report as w  # noqa: E402

DAY1, DAY2 = time.mktime((2026, 10, 1, 12, 0, 0, 0, 0, -1)), time.mktime((2026, 10, 2, 12, 0, 0, 0, 0, -1))


def make_db(d):
    c = sqlite3.connect(Path(d) / "ears.db")
    c.execute("CREATE TABLE segments(id INTEGER PRIMARY KEY, created REAL, raw_text TEXT, text TEXT, corrected_text TEXT, status TEXT, note TEXT)")
    rows = [
        (1, DAY1, "hello wurld", "hello wurld", "hello world", "corrected", "it heard wurld"),   # first fix wurld -> world
        (2, DAY1, "good morning", "good morning", None, "approved", None),
        (3, DAY2, "big wurld", "big world", None, "approved", None),                              # rule prevented the repeat
        (4, DAY2, "my wurld", "my wurld", "my world", "corrected", None),                         # rule failed: repeat
        (5, DAY2, "unreviewed", "unreviewed", None, "new", None),
    ]
    c.executemany("INSERT INTO segments VALUES(?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()


class Wer(unittest.TestCase):
    def test_edit_distance_and_fixes(self):
        self.assertEqual(w.edit_distance(["a", "b", "c"], ["a", "x", "c", "d"]), 2)
        self.assertEqual(w.fixes(["hello", "wurld"], ["hello", "world"]), [("wurld", "world")])
        self.assertEqual(w.words("Hello, World's!"), ["hello", "world's"])

    def test_report_numbers_from_a_tiny_db_and_the_real_file_is_untouched(self):
        d = tempfile.mkdtemp()
        make_db(d)
        before = (Path(d) / "ears.db").read_bytes()
        conn, tmp = w.open_copy(d)
        rows = w.load(conn)
        conn.close()
        a = w.analyse(rows, [{"status": "corrected", "raw": "a b", "text": "a c"}, {"status": "new", "raw": "x", "text": "y"}])
        self.assertEqual((a["all_lines"], a["reviewed"], a["corrected"], a["approved"]), (5, 4, 2, 2))
        # human words: 2 + 2 + 2 + 2 = 8; raw errors: line1 1, line2 0, line3 1 (wurld vs world), line4 1 => 3
        self.assertEqual(a["words"], 8)
        self.assertAlmostEqual(a["wer_raw"], 3 / 8)
        self.assertAlmostEqual(a["wer_shown"], 2 / 8)      # the rule already fixed line 3
        self.assertEqual(a["notes"], 1)
        self.assertEqual(a["top"][0], (("wurld", "world"), 2))
        self.assertEqual((a["fix_pairs"], a["recurring_fixes"], a["prevented"], a["repeats"]), (1, 1, 1, 1))
        self.assertAlmostEqual(a["repeat_rate"], 0.5)
        self.assertEqual(sorted(a["per_day"]), ["2026-10-01", "2026-10-02"])
        self.assertEqual(a["gold"]["lines"], 1)
        text = w.render(a, "tmp")
        self.assertIn("Key numbers", text)
        self.assertIn("wurld", text)
        self.assertEqual(before, (Path(d) / "ears.db").read_bytes())    # the original was only copied

    def test_empty_db(self):
        a = w.analyse([])
        self.assertIsNone(a["wer_raw"])
        self.assertIn("n/a", w.render(a))


if __name__ == "__main__":
    unittest.main()
