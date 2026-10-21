"""Tiny SQLite store: sessions (live runs / VODs / clips), segments, vocab, replacement rules."""
import json
import sqlite3
import threading
import time

import config as cfg

_lock = threading.RLock()
_c = sqlite3.connect(cfg.DATA / "ears.db", check_same_thread=False)
_c.row_factory = sqlite3.Row
_c.execute("PRAGMA journal_mode=WAL")
_c.executescript("""
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, source_id TEXT UNIQUE, url TEXT,
  audio TEXT, duration REAL DEFAULT 0, status TEXT, progress REAL DEFAULT 0, error TEXT, created REAL);
CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, t REAL, start REAL, end REAL, audio TEXT,
  raw_words TEXT, words TEXT, text TEXT, raw_text TEXT, unsure REAL DEFAULT 0,
  status TEXT DEFAULT 'new', corrected_text TEXT, created REAL);
CREATE INDEX IF NOT EXISTS seg_session ON segments(session_id, t);
CREATE INDEX IF NOT EXISTS seg_review ON segments(status, unsure);
CREATE TABLE IF NOT EXISTS vocab(term TEXT PRIMARY KEY, count INTEGER DEFAULT 1, source TEXT);
CREATE TABLE IF NOT EXISTS rules(wrong TEXT PRIMARY KEY, right TEXT, count INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS attempts(source_id TEXT PRIMARY KEY, n INTEGER DEFAULT 0, last REAL, err TEXT);
""")
_c.commit()


def run(sql, args=()):
    with _lock:
        cur = _c.execute(sql, args)
        _c.commit()
        return cur


def rows(sql, args=()):
    with _lock:
        return [dict(r) for r in _c.execute(sql, args).fetchall()]


class Busy(Exception):
    """The database is held by a long job (import, learn); the caller may show cached data instead of hanging."""


def rows_nowait(sql, args=(), wait=1.5):
    """Like rows(), but gives up after `wait` seconds instead of blocking behind a long write: the status poll must never hang the dashboard."""
    if not _lock.acquire(timeout=wait):
        raise Busy()
    try:
        return [dict(r) for r in _c.execute(sql, args).fetchall()]
    finally:
        _lock.release()


def one(sql, args=()):
    r = rows(sql, args)
    return r[0] if r else None


def add_segment(session_id, t, start, end, audio, raw_words, final, status="new") -> dict:
    cur = run(
        "INSERT INTO segments(session_id,t,start,end,audio,raw_words,words,text,raw_text,unsure,status,created)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (session_id, t, start, end, audio, json.dumps(raw_words), json.dumps(final["words"]),
         final["text"], final["raw_text"], final["unsure"], status, time.time()))
    return seg_json(one("SELECT * FROM segments WHERE id=?", (cur.lastrowid,)))


def seg_json(r: dict) -> dict:
    return {
        "id": r["id"], "session_id": r["session_id"], "t": r["t"], "start": r["start"], "end": r["end"],
        "text": r["corrected_text"] or r["text"], "raw_text": r["raw_text"],
        "words": json.loads(r["words"]), "unsure": r["unsure"], "status": r["status"],
        "audio": "/media/" + r["audio"] if r["audio"] else None,
    }
