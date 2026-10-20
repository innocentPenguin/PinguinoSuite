"""Regression: VOD ingestion must not load a whole VOD into RAM, and a restart must not strand jobs.
Run: cd Suite\\modules\\listen ; ..\\..\\.venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import queue
import sqlite3
import sys
import tempfile
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audioio import iter16k  # noqa: E402


def make_wav(path, seconds, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    pcm = (np.sin(2 * np.pi * 440 * t) * 12000).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return len(pcm)


class Iter16k(unittest.TestCase):
    def test_slices_are_bounded_and_complete(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.wav")
            n = make_wav(p, 25)
            parts = list(iter16k(p, chunk_s=10))
            self.assertEqual([round(o) for o, _ in parts], [0, 10, 20])
            self.assertTrue(all(len(a) <= 10 * 16000 for _, a in parts))  # never more than one slice
            self.assertEqual(sum(len(a) for _, a in parts), n)             # nothing lost
            self.assertTrue(all(a.dtype == np.float32 and abs(a).max() <= 1.0 for _, a in parts))

    def test_short_file_single_slice(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.wav")
            n = make_wav(p, 3)
            parts = list(iter16k(p, chunk_s=900))
            self.assertEqual(len(parts), 1)
            self.assertEqual(len(parts[0][1]), n)


class JobsRecovery(unittest.TestCase):
    def setUp(self):
        import db
        import ingest
        self.db, self.ingest = db, ingest
        self._orig = db._c
        c = sqlite3.connect(":memory:", check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.executescript(
            "CREATE TABLE sessions(id TEXT PRIMARY KEY, kind TEXT, title TEXT, source_id TEXT UNIQUE, url TEXT, audio TEXT,"
            " duration REAL DEFAULT 0, status TEXT, progress REAL DEFAULT 0, error TEXT, created REAL);"
            "CREATE TABLE segments(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT);")
        db._c = c
        self.j = ingest.Jobs.__new__(ingest.Jobs)  # no worker thread
        self.j.asr, self.j.emit, self.j.q, self.j.jobs = None, lambda *_: None, queue.Queue(), {}

    def tearDown(self):
        self.db._c = self._orig

    def add(self, sid, status, segs=0, kind="vod"):
        self.db.run("INSERT INTO sessions(id,kind,title,source_id,status,created) VALUES(?,?,?,?,?,0)", (sid, kind, sid, "src:" + sid, status))
        for _ in range(segs):
            self.db.run("INSERT INTO segments(session_id) VALUES(?)", (sid,))

    def test_restart_marks_dead_jobs_and_keeps_learned_lines(self):
        self.add("q", "queued")
        self.add("t", "transcribing", segs=3)
        self.add("l", "transcribing", kind="live")
        self.add("d", "done", segs=1)
        self.j.recover()
        st = {r["id"]: r["status"] for r in self.db.rows("SELECT id,status FROM sessions")}
        self.assertEqual(st, {"q": "interrupted", "t": "done", "l": "transcribing", "d": "done"})

    def test_interrupted_can_be_queued_again_but_done_cannot(self):
        self.add("q", "interrupted")
        self.add("d", "done", segs=2)
        self.add("e", "error", segs=1)
        self.assertIsNotNone(self.j.submit("vod", "again", "src:q"))   # re-queued
        self.assertIsNone(self.j.submit("vod", "again", "src:d"))      # already learned
        self.assertIsNone(self.j.submit("vod", "again", "src:e"))      # has lines: never discard
        self.assertEqual(self.j.q.qsize(), 1)


if __name__ == "__main__":
    unittest.main()
