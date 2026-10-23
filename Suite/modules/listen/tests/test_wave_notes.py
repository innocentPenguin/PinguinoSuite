"""Review card: waveform peaks from the decoded audio, and 'noted lines first' ordering."""
import math
import os
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LISTEN_DATA_DIR"] = tempfile.mkdtemp()   # never the real ears.db


def tone_wav(path, quiet_s=1.0, loud_s=1.0, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * quiet_s)
        w.writeframes(b"".join(struct.pack("<h", int(300 * math.sin(i / 5))) for i in range(n)))
        n = int(rate * loud_s)
        w.writeframes(b"".join(struct.pack("<h", int(20000 * math.sin(i / 5))) for i in range(n)))


class Wave(unittest.TestCase):
    def test_peaks_quiet_then_loud(self):
        import audioio
        p = Path(tempfile.mkdtemp()) / "t.wav"
        tone_wav(p)
        pk = audioio.peaks(p, 0.0, 2.0, 40)
        self.assertEqual(len(pk), 40)
        self.assertEqual(max(pk), 1.0)
        self.assertLess(max(pk[:15]), 0.1)
        self.assertGreater(min(pk[25:]), 0.5)

    def test_endpoint(self):
        import config as cfg
        import db
        import server
        from fastapi.testclient import TestClient
        (cfg.DATA / "audio").mkdir(parents=True, exist_ok=True)
        tone_wav(cfg.DATA / "audio" / "t.wav")
        db.run("INSERT INTO sessions(id,kind,title,status,created) VALUES('w','vod','t','done',0)")
        w = [{"w": "hi", "s": 0.0, "e": 0.4, "p": 0.5}]
        a = db.add_segment("w", 0, 0.5, 1.9, "audio/t.wav", w, {"words": w, "text": "hi", "raw_text": "hi", "unsure": 0.5})
        b = db.add_segment("w", 1, 0.5, 1.9, None, w, {"words": w, "text": "hi", "raw_text": "hi", "unsure": 0.5})
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        pk = c.get(f"/api/segments/{a['id']}/peaks?n=30").json()["peaks"]
        self.assertEqual(len(pk), 30)
        self.assertEqual(c.get(f"/api/segments/{b['id']}/peaks").json()["peaks"], [])
        self.assertEqual(c.get("/api/segments/99999/peaks").status_code, 404)


class NotesFirst(unittest.TestCase):
    def test_noted_line_comes_first(self):
        import db
        import server
        from fastapi.testclient import TestClient
        db.run("INSERT INTO sessions(id,kind,title,status,created) VALUES('n','vod','t','done',0)")
        w = [{"w": "hello", "s": 0.0, "e": 0.4, "p": 0.5}]
        ids = [db.add_segment("n", i, 0.0, 0.4, None, w, {"words": w, "text": "hello", "raw_text": "hello", "unsure": u})["id"] for i, u in enumerate((5.0, 1.0, 0.0))]
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        first = lambda q: c.get("/api/review/next?session=n" + q).json()["segment"]["id"]
        self.assertEqual(first(""), ids[0])                  # worst confidence
        self.assertEqual(first("&notes_first=true"), ids[0])  # no notes yet: unchanged
        c.post(f"/api/segments/{ids[1]}/note", json={"note": "said hullo"})
        self.assertEqual(first("&notes_first=true"), ids[1])  # noted line jumps the queue
        self.assertEqual(first(""), ids[0])                  # off: old order
        c.post(f"/api/segments/{ids[2]}/note", json={"note": "cut off"})
        self.assertEqual(c.get("/api/review/next?session=n&notes_first=true").json()["left"], 3)   # a confident (unsure 0) line with a note is offered
        self.assertEqual(c.get("/api/review/next?session=n").json()["left"], 2)


if __name__ == "__main__":
    unittest.main()
