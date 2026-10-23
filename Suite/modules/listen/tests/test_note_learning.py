"""Saved review notes feed learning (setting learn_from_notes, default OFF). Temp data only."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LISTEN_DATA_DIR"] = tempfile.mkdtemp()   # never the real ears.db


def seg(db, text, unsure=0.5, sid="nl"):
    if not db.one("SELECT id FROM sessions WHERE id=?", (sid,)):
        db.run("INSERT INTO sessions(id,kind,title,status,created) VALUES(?,'vod','t','done',0)", (sid,))
    w = [{"w": x, "s": i * 0.3, "e": i * 0.3 + 0.3, "p": 0.9} for i, x in enumerate(text.split())]
    return db.add_segment(sid, 0, 0.0, len(w) * 0.3, None, w, {"words": w, "text": text, "raw_text": text, "unsure": unsure})["id"]


class Parse(unittest.TestCase):
    def test_markers(self):
        import learn
        p = learn.parse_note('"hullo" -> "hello"; vocab: Pinguino, Twitch Prime ; wrong: kat, dog')
        self.assertEqual(p["rules"], [("hullo", "hello")])
        self.assertEqual(p["vocab"], ["Pinguino", "Twitch Prime"])
        self.assertEqual(p["wrong"], ["kat", "dog"])
        self.assertEqual(learn.parse_note("the audio was cut off and it sounded like a cat"), {"rules": [], "vocab": [], "wrong": []})
        self.assertEqual(learn.parse_note("a -> a")["rules"], [])
        self.assertEqual(learn.parse_note("one two three four five -> x")["rules"], [])


class Off(unittest.TestCase):
    def test_default_off_learns_nothing(self):
        import config as cfg
        import db
        import learn
        import server
        from fastapi.testclient import TestClient
        self.assertFalse(cfg.settings()["learn_from_notes"])
        sid = seg(db, "hullo there")
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        r = c.post(f"/api/segments/{sid}/note", json={"note": "hullo -> hello"}).json()
        self.assertIsNone(r["learned"])
        self.assertEqual(db.rows("SELECT * FROM rules"), [])
        self.assertEqual(db.one("SELECT note FROM segments WHERE id=?", (sid,))["note"], "hullo -> hello")   # the note itself always saves


class On(unittest.TestCase):
    def setUp(self):
        import config as cfg
        cfg.save_settings({"learn_from_notes": True})

    def tearDown(self):
        import config as cfg
        cfg.save_settings({"learn_from_notes": False})

    def test_note_makes_rule_vocab_once(self):
        import db
        import server
        from fastapi.testclient import TestClient
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        sid = seg(db, "hullo Pingwin")
        r = c.post(f"/api/segments/{sid}/note", json={"note": "pingwin -> Pinguino; vocab: Innocent Penguin"}).json()["learned"]
        self.assertEqual(r["rules"], [["pingwin", "Pinguino"]])
        self.assertEqual(db.one("SELECT right,count FROM rules WHERE wrong='pingwin'")["count"], 1)
        terms = {x["term"] for x in db.rows("SELECT term FROM vocab")}
        self.assertTrue({"Pinguino", "Innocent Penguin"} <= terms)
        self.assertIsNone(c.post(f"/api/segments/{sid}/note", json={"note": "pingwin -> Pinguino; vocab: Innocent Penguin"}).json()["learned"])   # same note again: not counted twice
        self.assertEqual(db.one("SELECT count FROM rules WHERE wrong='pingwin'")["count"], 1)

    def test_regrade_goes_noted_first_and_boosts_wrong_word(self):
        import db
        import learn
        a = seg(db, "nothing odd here", sid="rg")
        b = seg(db, "that was a kat video", sid="rg")
        c = seg(db, "an unrelated line", sid="rg")
        db.run("UPDATE segments SET note=? WHERE id=?", ("wrong: kat", b))
        db.run("UPDATE segments SET note=? WHERE id=?", ("wrong: dog", c))     # word is not in the line: no boost
        n = learn.regrade_unreviewed()
        self.assertGreaterEqual(n, 3)
        ub = db.one("SELECT unsure FROM segments WHERE id=?", (b,))["unsure"]
        uc = db.one("SELECT unsure FROM segments WHERE id=?", (c,))["unsure"]
        ua = db.one("SELECT unsure FROM segments WHERE id=?", (a,))["unsure"]
        self.assertGreaterEqual(ub, learn.NOTE_BOOST)
        self.assertLess(uc, learn.NOTE_BOOST)
        self.assertLess(ua, learn.NOTE_BOOST)

    def test_regrade_applies_note_rule_in_same_pass(self):
        import db
        import learn
        s = seg(db, "say hullo please", sid="rg2")
        db.run("UPDATE segments SET note=? WHERE id=?", ("hullo -> hello", s))
        learn.regrade_unreviewed()
        self.assertEqual(db.one("SELECT text FROM segments WHERE id=?", (s,))["text"], "say hello please")


if __name__ == "__main__":
    unittest.main()
