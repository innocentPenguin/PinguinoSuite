"""POST /api/shell-log: webview errors into a redacted, capped, rotating shell.log."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
os.environ["PINGUINO_SHELL_LOG_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import shell_log  # noqa: E402


class ShellLogLib(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_line_format_and_levels(self):
        sl = shell_log.ShellLog(self.d)
        out = sl.add([{"level": "error", "msg": "boom", "n": 3, "src": "app.js:1"}, {"level": "warn", "msg": "hmm"}])
        self.assertRegex(out[0][1], r"^\d\d:\d\d:\d\d \[shell\] error: boom \(x3\) \[app\.js:1\]$")
        self.assertEqual(out[1][0], "warn")
        self.assertEqual(len((self.d / "shell.log").read_text("utf8").splitlines()), 2)

    def test_redaction(self):
        r = shell_log.redact("fetch http://127.0.0.1:8760/api/x?token=abc123secretvalue failed Authorization: Bear" + "er abcdefghijklmnop1234 key=sk_" + "live_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        for bad in ("abc123secretvalue", "abcdefghijklmnop1234", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"):
            self.assertNotIn(bad, r)
        self.assertIn("/api/x", r)

    def test_control_chars_and_newlines(self):
        r = shell_log.redact("a\x07b\nc\x1bd")
        self.assertNotIn("\x07", r)
        self.assertNotIn("\n", r)
        self.assertNotIn("\x1b", r)

    def test_truncation_and_request_cap(self):
        sl = shell_log.ShellLog(self.d)
        out = sl.add([{"level": "error", "msg": "x " * 2000}] * 80)
        self.assertEqual(len(out), shell_log.MAX_ENTRIES)
        self.assertLess(len(out[0][1]), 600)

    def test_rotation_keeps_three_files(self):
        sl = shell_log.ShellLog(self.d, max_bytes=300, keep=3)
        for i in range(40):
            sl.add([{"level": "error", "msg": f"entry {i} " + "z" * 60}])
        names = sorted(p.name for p in self.d.iterdir())
        self.assertEqual(names, ["shell.log", "shell.log.1", "shell.log.2"])
        for p in self.d.iterdir():
            self.assertLess(p.stat().st_size, 600)

    def test_junk_entries_ignored(self):
        sl = shell_log.ShellLog(self.d)
        self.assertEqual(sl.add(["str", 5, {"msg": ""}, None]), [])
        self.assertFalse((self.d / "shell.log").exists())


class ShellLogApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import suite
        from fastapi.testclient import TestClient
        cls.suite = suite
        suite.SHELL_LOG = shell_log.ShellLog(tempfile.mkdtemp())   # never the real Data\logs (suite may already be imported by another test)
        cls.c = TestClient(suite.app, base_url="http://127.0.0.1:8760")

    def test_rejects_without_token(self):
        r = self.c.post("/api/shell-log", json={"entries": [{"level": "error", "msg": "x"}]})
        self.assertEqual(r.status_code, 401)

    def test_accepts_with_token_and_logs_error(self):
        h = {"Authorization": "Bearer " + self.suite.TOKEN}
        r = self.c.post("/api/shell-log", json={"entries": [{"level": "error", "msg": "ReferenceError: foo is not defined"}, {"level": "warn", "msg": "w"}]}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["written"], 2)
        txt = (self.suite.SHELL_LOG.path).read_text("utf8")
        self.assertIn("ReferenceError", txt)


if __name__ == "__main__":
    unittest.main()
