"""Regression: a failing VOD must not be re-downloaded forever (24 x 876 MB copies piled up in data\sources).
Run: cd Suite\modules\listen ; ..\..\.venv\Scripts\python.exe -m unittest discover -s tests
"""
import os
import queue
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SourceLoop(unittest.TestCase):
    def setUp(self):
        import config
        import db
        import ingest
        self.cfg, self.db, self.ingest = config, db, ingest
        self._orig_c, self._orig_src = db._c, config.SOURCES
        c = sqlite3.connect(":memory:", check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.executescript(
            "CREATE TABLE sessions(id TEXT PRIMARY KEY, kind TEXT, title TEXT, source_id TEXT UNIQUE, url TEXT, audio TEXT,"
            " duration REAL DEFAULT 0, status TEXT, progress REAL DEFAULT 0, error TEXT, created REAL);"
            "CREATE TABLE segments(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT);"
            "CREATE TABLE attempts(source_id TEXT PRIMARY KEY, n INTEGER DEFAULT 0, last REAL, err TEXT);")
        db._c = c
        self.tmp = tempfile.TemporaryDirectory()
        config.SOURCES = Path(self.tmp.name)
        self.j = ingest.Jobs.__new__(ingest.Jobs)
        self.j.asr, self.j.emit, self.j.q, self.j.jobs = None, lambda *_: None, queue.Queue(), {}

    def tearDown(self):
        self.db._c, self.cfg.SOURCES = self._orig_c, self._orig_src
        self.tmp.cleanup()

    def fail_once(self, source_id="vod:1"):
        """One automatic cycle: the sync submits, the worker runs it, it fails after the download finished."""
        sid = self.j.submit("vod", "t", source_id, url="http://x")
        if sid is None:
            return None
        self.j.q.get_nowait()
        stem = self.ingest.src_stem(source_id)
        self.j._ingest = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("convert failed"))
        # the download is already on disk when the failure happens
        (Path(self.tmp.name) / (stem + ".mp4")).write_bytes(b"x" * 10)
        with self.assertRaises(RuntimeError):
            self.j._run(sid, "http://x", None)
        self.j._push(sid, status="error", error="convert failed")
        return sid

    def test_automatic_retries_stop_after_max_and_leave_no_file(self):
        for _ in range(self.ingest.MAX_ATTEMPTS):
            self.assertIsNotNone(self.fail_once())
        self.assertIsNone(self.j.submit("vod", "t", "vod:1", url="http://x"))     # the 30-min sync gives up
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])               # the original was removed on the last failure

    def test_failure_before_the_limit_keeps_one_reusable_copy(self):
        self.fail_once()
        self.fail_once()
        files = list(Path(self.tmp.name).iterdir())
        self.assertEqual(len(files), 1)                                          # same stable name every time, never a pile
        self.assertIsNotNone(self.ingest.finished_source(self.ingest.src_stem("vod:1")))

    def test_person_pressing_learn_again_resets_the_count(self):
        for _ in range(self.ingest.MAX_ATTEMPTS):
            self.fail_once()
        self.assertIsNone(self.j.submit("vod", "t", "vod:1", url="x"))
        self.assertIsNotNone(self.j.submit("vod", "t", "vod:1", url="x", force=True))

    def test_unfinished_parts_are_not_a_finished_download(self):
        stem = self.ingest.src_stem("vod:2")
        (Path(self.tmp.name) / (stem + ".mp4.part")).write_bytes(b"x")
        (Path(self.tmp.name) / (stem + ".mp4.part-Frag3.part")).write_bytes(b"x")
        self.assertIsNone(self.ingest.finished_source(stem))
        (Path(self.tmp.name) / (stem + ".mp4")).write_bytes(b"x")
        self.assertEqual(self.ingest.finished_source(stem).name, stem + ".mp4")

    def test_download_reuses_finished_copy_and_respects_size_cap(self):
        stem = self.ingest.src_stem("vod:3")
        have = Path(self.tmp.name) / (stem + ".mp4")
        have.write_bytes(b"x")
        self.assertEqual(self.j._download("s", "http://x", stem), have)          # no network involved
        have.unlink()
        old = self.ingest.MAX_SOURCES_BYTES
        self.ingest.MAX_SOURCES_BYTES = 5
        try:
            (Path(self.tmp.name) / "other.mp4").write_bytes(b"x" * 10)
            with self.assertRaises(RuntimeError):
                self.j._download("s", "http://x", stem)
        finally:
            self.ingest.MAX_SOURCES_BYTES = old


if __name__ == "__main__":
    unittest.main()
