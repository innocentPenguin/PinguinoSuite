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


class Safety(unittest.TestCase):
    def setUp(self):
        import config as cfg
        import db
        import learn
        self._common = learn._common
        learn._common = {"the", "a", "cat", "and"}      # do not depend on the word-list file
        cfg.save_settings({"learn_from_notes": True})
        for t in ("rules", "vocab", "note_learned", "rule_pending"):
            db.run("DELETE FROM " + t)

    def tearDown(self):
        import config as cfg
        import learn
        learn._common = self._common
        cfg.save_settings({"learn_from_notes": False})

    def test_common_word_rule_never_created_and_trivial_edits_do_not_count(self):
        import db
        import learn
        s1 = seg(db, "the cat", sid="sf")
        learn.learn_from_note(s1, "the -> a")
        learn.learn_from_note(s1, "the -> a.")
        self.assertEqual(db.rows("SELECT * FROM rules"), [])
        learn.learn_from_note(s1, "pingwin -> Pinguino")
        learn.learn_from_note(s1, "  pingwin   ->  Pinguino. ")     # same parsed result
        learn.learn_from_note(s1, '"pingwin" -> "Pinguino"')
        self.assertEqual(db.one("SELECT count FROM rules WHERE wrong='pingwin'")["count"], 1)
        s2 = seg(db, "pingwin again", sid="sf")
        learn.learn_from_note(s2, "pingwin -> Pinguino")
        self.assertEqual(db.one("SELECT count FROM rules WHERE wrong='pingwin'")["count"], 2)   # a second segment does count

    def test_editing_or_deleting_a_note_takes_back_what_it_taught(self):
        import db
        import learn
        s = seg(db, "hullo Pingwin", sid="ed")
        learn.learn_from_note(s, "pingwin -> Pinguino; vocab: Zorbax")
        self.assertTrue(db.one("SELECT 1 x FROM rules WHERE wrong='pingwin'"))
        self.assertTrue(db.one("SELECT 1 x FROM vocab WHERE term='Zorbax'"))
        learn.learn_from_note(s, "vocab: Zorbax")
        self.assertIsNone(db.one("SELECT 1 x FROM rules WHERE wrong='pingwin'"))
        self.assertTrue(db.one("SELECT 1 x FROM vocab WHERE term='Zorbax'"))
        self.assertIsNone(db.one("SELECT 1 x FROM vocab WHERE term='Pinguino'"))
        learn.learn_from_note(s, "")
        self.assertEqual(db.rows("SELECT * FROM vocab"), [])

    def test_setting_off_still_takes_back_an_edited_note(self):
        import config as cfg
        import db
        import learn
        s = seg(db, "x", sid="off2")
        learn.learn_from_note(s, "pingwin -> Pinguino")
        cfg.save_settings({"learn_from_notes": False})
        learn.learn_from_note(s, "something else")
        self.assertEqual(db.rows("SELECT * FROM rules"), [])

    def test_conflicting_note_does_not_flip_until_a_second_segment_agrees(self):
        import db
        import learn
        a, b, c = (seg(db, "x", sid="cf") for _ in range(3))
        learn.learn_from_note(a, "pingwin -> Pinguino")
        r = learn.learn_from_note(b, "pingwin -> Penguin")
        self.assertEqual(db.one("SELECT right,count FROM rules WHERE wrong='pingwin'"), {"right": "Pinguino", "count": 1})
        self.assertEqual(r["conflicts"], [["pingwin", "Pinguino", "Penguin"]])
        self.assertEqual(learn.note_conflicts(), [{"wrong": "pingwin", "kept": "Pinguino", "proposed": "Penguin", "votes": 1}])
        learn.learn_from_note(c, "pingwin -> Penguin")
        self.assertEqual(db.one("SELECT right FROM rules WHERE wrong='pingwin'")["right"], "Penguin")
        self.assertEqual(learn.note_conflicts(), [])

    def test_caps(self):
        import db
        import learn
        old = learn.MAX_NOTE_RULES
        learn.MAX_NOTE_RULES = 2
        try:
            for i in range(4):
                learn.learn_from_note(seg(db, "x", sid="cap"), f"zzword{i} -> Right{i}")
            self.assertEqual(db.one("SELECT COUNT(*) n FROM rules")["n"], 2)
        finally:
            learn.MAX_NOTE_RULES = old

    def test_conflicts_endpoint(self):
        import server
        from fastapi.testclient import TestClient
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        self.assertEqual(c.get("/api/note-conflicts").json(), {"conflicts": []})


if __name__ == "__main__":
    unittest.main()
