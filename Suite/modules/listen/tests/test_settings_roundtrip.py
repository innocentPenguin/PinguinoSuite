"""Listen settings round-trip over HTTP: learn_from_notes and bot_speech (temp data only)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LISTEN_DATA_DIR"] = tempfile.mkdtemp()   # never the real ears.db / settings


class Settings(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import server
        self.c = TestClient(server.app, base_url="http://127.0.0.1:8765")

    def test_defaults(self):
        st = self.c.get("/api/status").json()["settings"]
        self.assertIs(st["learn_from_notes"], False)
        self.assertEqual(st["bot_speech"], "drop")

    def test_round_trip(self):
        r = self.c.post("/api/settings", json={"learn_from_notes": True, "bot_speech": "tag"})
        self.assertEqual(r.status_code, 200)
        st = self.c.get("/api/status").json()["settings"]
        self.assertIs(st["learn_from_notes"], True)
        self.assertEqual(st["bot_speech"], "tag")
        self.c.post("/api/settings", json={"learn_from_notes": False, "bot_speech": "drop"})
        st = self.c.get("/api/status").json()["settings"]
        self.assertEqual((st["learn_from_notes"], st["bot_speech"]), (False, "drop"))

    def test_bad_bot_speech_rejected_and_unchanged(self):
        self.assertEqual(self.c.post("/api/settings", json={"bot_speech": "shout"}).status_code, 400)
        self.assertEqual(self.c.get("/api/status").json()["settings"]["bot_speech"], "drop")

    def test_page_has_the_controls(self):
        html = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text("utf8")
        for i in ('id="s-notes"', 'id="s-bot"', "learn_from_notes", "bot_speech"):
            self.assertIn(i, html)


if __name__ == "__main__":
    unittest.main()
