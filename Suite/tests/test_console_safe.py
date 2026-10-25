"""Control characters (the terminal bell above all) never reach a console; log files keep the text, escaped."""
import filecmp
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SUITE / "suite"))
import safetext  # noqa: E402

BS = chr(92)
B = chr(7)   # the bell, built at run time so no script holds one


class Clean(unittest.TestCase):
    def test_bell_and_controls_escaped(self):
        out = safetext.clean(f"hi{B}there\x00\x08\x0b\x0c\x0e\x1f\x7f\x85 ok\tTab\r\n")
        self.assertNotIn(B, out)
        self.assertIn(BS + "x07", out)
        for c in "\x00\x08\x0b\x0c\x0e\x1f\x7f\x85":
            self.assertNotIn(c, out)
        self.assertTrue(out.endswith("ok\tTab\r\n"))

    def test_plain_text_and_colours_untouched(self):
        for s in ["hello world", "ünï ✓ 🐧", "a\tb\r\nc", "\x1b[31mred\x1b[0m"]:
            self.assertEqual(safetext.clean(s), s)
        self.assertNotIn("\x1b", safetext.clean("x\x1b]0;title" + B))

    def test_stream_wrapper(self):
        buf = io.StringIO()
        s = safetext.SafeStream(buf)
        print(f"chat: a{B}b", file=s)
        s.writelines([f"c{B}\n"])
        s.flush()
        self.assertNotIn(B, buf.getvalue())
        self.assertEqual(buf.getvalue().count(BS + "x07"), 2)

    def test_install_wraps_real_streams(self):
        code = ("import sys; sys.path.insert(0, %r); import safetext; safetext.install(); safetext.install(); "
                "print('a' + chr(7) + 'b'); print('e' + chr(7), file=sys.stderr); "
                "import logging; logging.basicConfig(); logging.warning('log' + chr(7))" % str(SUITE / "suite"))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(b"\x07", r.stdout + r.stderr)
        self.assertIn(b"a" + BS.encode() + b"x07b", r.stdout)

    def test_log_file_keeps_escape(self):
        line = json.dumps({"msg": f"x{B}y"})   # what the Listen/core JSON logs write
        self.assertNotIn(B, line)
        self.assertIn(BS + "u0007", line)

    def test_copies_identical(self):
        self.assertTrue(filecmp.cmp(SUITE / "suite" / "safetext.py", SUITE / "modules" / "listen" / "safetext.py", shallow=False))

    def test_entry_points_install_it(self):
        for rel in ("suite/suite.py", "modules/listen/server.py", "tools/wer_report.py", "tools/dupe_report.py"):
            self.assertIn("safetext.install()", (SUITE / rel).read_text("utf8"), rel)

    def test_wer_report_output_has_no_bell(self):
        import sqlite3
        d = tempfile.mkdtemp()
        db = os.path.join(d, "ears.db")
        c = sqlite3.connect(db)
        c.execute("create table utterances (id integer primary key, text text, ts real)")
        c.execute("insert into utterances(text,ts) values (?,1)", (f"bell{B}text",))
        c.commit(); c.close()
        r = subprocess.run([sys.executable, str(SUITE / "tools" / "wer_report.py"), d], capture_output=True)
        self.assertNotIn(b"\x07", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
