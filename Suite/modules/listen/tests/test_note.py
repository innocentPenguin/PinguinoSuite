"""The review card's note: stored with the segment, returned by the API, kept when a correction carries none."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LISTEN_DATA_DIR"] = tempfile.mkdtemp()   # never the real ears.db


class Note(unittest.TestCase):
    def test_note_roundtrip(self):
        import db
        import server
        from fastapi.testclient import TestClient
        db.run("INSERT INTO sessions(id,kind,title,status,created) VALUES('s','vod','t','done',0)")
        w = [{"w": "hello", "s": 0.0, "e": 0.4, "p": 0.5}]
        sg = db.add_segment("s", 0, 0.0, 0.4, None, w, {"words": w, "text": "hello", "raw_text": "hello", "unsure": 0.5})
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        rr = c.post(f"/api/segments/{sg['id']}/note", json={"note": "  it said  hullo "})
        self.assertEqual(c.post(f"/api/segments/{sg['id']}/note", json={"note": "  it said  hullo "}).json()["note"], "it said hullo")
        r = c.get("/api/review/next?confident=true").json()["segment"]
        self.assertEqual(r["note"], "it said hullo")
        self.assertEqual(r["words"][0]["s"], 0.0)
        c.post(f"/api/segments/{sg['id']}/correct", json={"text": "hello"})
        self.assertEqual(db.one("SELECT note FROM segments WHERE id=?", (sg["id"],))["note"], "it said hullo")
        self.assertEqual(c.post("/api/segments/999/note", json={"note": "x"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
