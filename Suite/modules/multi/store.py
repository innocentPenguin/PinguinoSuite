"""SQLite WAL store: messages, cards, windows, profiles, learning events. Thread-safe via one lock."""
import json
import sqlite3
import threading
import time

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY, platform TEXT, channel TEXT, user_id TEXT, user TEXT, display TEXT,
  text TEXT, ts REAL, json TEXT, score REAL, tier TEXT);
CREATE INDEX IF NOT EXISTS ix_msg_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS ix_msg_user ON messages(platform, user_id, ts);
CREATE TABLE IF NOT EXISTS cards(
  id TEXT PRIMARY KEY, message_id TEXT, state TEXT, created REAL, updated REAL, json TEXT);
CREATE TABLE IF NOT EXISTS windows(id TEXT PRIMARY KEY, json TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS profiles(name TEXT PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""

_ORDER = ["none", "low", "medium", "high"]
_TIERS_FROM = {t: _ORDER[i:] for i, t in enumerate(_ORDER)}


def _msg(r):
    d = json.loads(r["json"])
    d["score"], d["tier"] = r["score"], r["tier"]
    return d


class Store:
    def __init__(self, path=None):
        self.path = str(path or config.DB_FILE)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)

    # messages -------------------------------------------------------
    def add_message(self, m, decision):
        """Returns False when the id already exists (reconnect replay)."""
        with self.lock:
            try:
                self.db.execute(
                    "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (m.id, m.platform, m.channel, m.user_id, m.user, m.display, m.text, m.ts,
                     json.dumps(m.to_dict()), decision.score, decision.tier))
                self.db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def update_score(self, mid, score, tier):
        with self.lock:
            self.db.execute("UPDATE messages SET score=?, tier=? WHERE id=?", (score, tier, mid))
            self.db.commit()

    def get_message(self, mid):
        with self.lock:
            r = self.db.execute("SELECT json,score,tier FROM messages WHERE id=?", (mid,)).fetchone()
        return _msg(r) if r else None

    def recent(self, limit=200, platform=None, min_tier=None, before=None):
        q, a = "SELECT json,score,tier FROM messages WHERE 1=1", []
        if platform:
            q += " AND platform=?"
            a.append(platform)
        if before:
            q += " AND ts<?"
            a.append(before)
        if min_tier:
            q += " AND tier IN (%s)" % ",".join("?" * len(_TIERS_FROM[min_tier]))
            a += _TIERS_FROM[min_tier]
        q += " ORDER BY ts DESC LIMIT ?"
        a.append(limit)
        with self.lock:
            rows = self.db.execute(q, a).fetchall()
        return [_msg(r) for r in reversed(rows)]

    def stats_since(self, since):
        """Per-minute counts and per-chatter counts of messages newer than `since` (epoch)."""
        with self.lock:
            per = self.db.execute("SELECT platform, user_id, user, display, COUNT(*) n FROM messages WHERE ts>? GROUP BY platform, user_id",
                                  (since,)).fetchall()
            mins = self.db.execute("SELECT CAST(ts/60 AS INTEGER) m, COUNT(*) n FROM messages WHERE ts>? GROUP BY m", (since,)).fetchall()
        return [dict(r) for r in per], {r["m"]: r["n"] for r in mins}

    def search(self, term, limit=100):
        with self.lock:
            rows = self.db.execute(
                "SELECT json,score,tier FROM messages WHERE text LIKE ? OR user LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{term}%", f"%{term}%", limit)).fetchall()
        return [_msg(r) for r in rows]

    def user_history(self, platform, user_id, limit=20):
        with self.lock:
            rows = self.db.execute(
                "SELECT json,score,tier FROM messages WHERE platform=? AND user_id=? ORDER BY ts DESC LIMIT ?",
                (platform, user_id, limit)).fetchall()
        return [_msg(r) for r in rows]

    def user_count(self, platform, user_id):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) c FROM messages WHERE platform=? AND user_id=?",
                                   (platform, user_id)).fetchone()["c"]

    def last_seen(self, platform):
        with self.lock:
            r = self.db.execute("SELECT MAX(ts) t FROM messages WHERE platform=?", (platform,)).fetchone()
        return r["t"] or 0

    def prune(self, days):
        cut = time.time() - days * 86400
        with self.lock:
            self.db.execute("DELETE FROM messages WHERE ts<?", (cut,))
            self.db.execute("DELETE FROM cards WHERE updated<? AND state IN ('answered','dismissed')", (cut,))
            self.db.commit()

    # cards ----------------------------------------------------------
    def save_card(self, c):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO cards VALUES(?,?,?,?,?,?)",
                            (c["id"], c["message_id"], c["state"], c["created"], c["updated"], json.dumps(c)))
            self.db.commit()

    def load_cards(self, states=("open", "snoozed", "missed")):
        with self.lock:
            rows = self.db.execute("SELECT json FROM cards WHERE state IN (%s)" % ",".join("?" * len(states)),
                                   list(states)).fetchall()
        return [json.loads(r["json"]) for r in rows]

    # windows / profiles ---------------------------------------------
    def save_window(self, w):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO windows VALUES(?,?,?)", (w["id"], json.dumps(w), time.time()))
            self.db.commit()

    def delete_window(self, wid):
        with self.lock:
            self.db.execute("DELETE FROM windows WHERE id=?", (wid,))
            self.db.commit()

    def load_windows(self):
        with self.lock:
            return [json.loads(r["json"]) for r in self.db.execute("SELECT json FROM windows").fetchall()]

    def save_profile(self, name, data):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO profiles VALUES(?,?)", (name, json.dumps(data)))
            self.db.commit()

    def load_profiles(self):
        with self.lock:
            return {r["name"]: json.loads(r["json"]) for r in self.db.execute("SELECT * FROM profiles").fetchall()}

    # events (learning log) ------------------------------------------
    def log_event(self, kind, data):
        with self.lock:
            self.db.execute("INSERT INTO events(ts,kind,json) VALUES(?,?,?)", (time.time(), kind, json.dumps(data)))
            self.db.commit()

    def events(self, limit=200):
        with self.lock:
            rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(json.loads(r["json"]), kind=r["kind"], ts=r["ts"]) for r in rows]

    # kv -------------------------------------------------------------
    def kv_get(self, k, default=None):
        with self.lock:
            r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(r["v"]) if r else default

    def kv_set(self, k, v):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v)))
            self.db.commit()
