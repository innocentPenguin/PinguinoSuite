"""FTS5 trigram search (worker 42): same results as LIKE, special characters, backfill, fallback, 100k-row timing."""
import time
from types import SimpleNamespace as NS

import pytest

import store as st

D = NS(reasons=[], score=1.0, tier="low")


def _m(i, text="hello", user="u"):
    return NS(id=f"m{i}", platform="twitch", channel="c", user_id="1", user=user, display=user, text=text, ts=1000.0 + i,
              to_dict=lambda: {"id": f"m{i}", "text": text, "user": user, "ts": 1000.0 + i})


@pytest.fixture
def s(tmp_path):
    x = st.Store(tmp_path / "t.db")
    assert x.fts, "FTS5 trigram not available in this SQLite"
    return x


def ids(rows):
    return [r["id"] for r in rows]


def test_substring_case_user_and_order(s):
    s.add_message(_m(1, "Hello World", "alice"), D)
    s.add_message(_m(2, "say HELLO again", "bob"), D)
    s.add_message(_m(3, "nothing", "helloFan"), D)
    assert ids(s.search("hello")) == ["m3", "m2", "m1"]          # newest first, text OR user, case-insensitive
    assert ids(s.search("ello wor")) == ["m1"]                    # substring, not word match
    assert s.search("zzz") == []


@pytest.mark.parametrize("q", ['"', "'", "a OR b", "NEAR(a b)", "col:val", "*", "a*", "-x", "(", ")", "\\", "%%%", "___", "x" * 5000, "\x00ab", "ünï", "日本語", "🔥🔥🔥"])
def test_special_query_characters_never_raise(s, q):
    s.add_message(_m(1, 'he said "hi" a OR b 100%%% ___ ünï 日本語 🔥🔥🔥'), D)
    assert isinstance(s.search(q), list)


def test_special_chars_match_literally(s):
    s.add_message(_m(1, 'say "quoted" now'), D)
    s.add_message(_m(2, "a OR b"), D)
    s.add_message(_m(3, "plain"), D)
    assert ids(s.search('"quoted"')) == ["m1"]
    assert ids(s.search("a OR b")) == ["m2"]
    assert ids(s.search("100%")) == []
    assert ids(s.search("日本語")) == [] and len(s.search("pla")) == 1


def test_short_terms_use_like(s):
    s.add_message(_m(1, "go go"), D)
    s.add_message(_m(2, "xyz"), D)
    assert ids(s.search("go")) == ["m1"] and ids(s.search("z")) == ["m2"]


def test_prune_and_reopen_keep_index_in_sync(tmp_path):
    p = tmp_path / "t.db"
    a = st.Store(p)
    a.add_message(_m(1, "findme old"), NS(reasons=[], score=1.0, tier="low"))
    a.add_message(_m(2, "findme new"), D)
    a.prune(0.0)                                                   # cut = now: everything older goes
    assert a.search("findme") == []
    b = st.Store(p)
    b.add_message(_m(3, "findme again"), D)
    assert ids(b.search("findme")) == ["m3"]


def test_backfill_on_first_start(tmp_path):
    p = tmp_path / "t.db"
    a = st.Store(p)
    for i in range(50):
        a.add_message(_m(i, f"legacy text {i}"), D)
    with a.lock:                                                   # simulate an old DB: no index, no marker
        a.db.executescript("DROP TRIGGER msg_fts_ai; DROP TRIGGER msg_fts_ad; DROP TRIGGER msg_fts_au; DROP TABLE msg_fts;")
        a.db.execute("DELETE FROM kv WHERE k='fts_built'")
        a.db.commit()
    a.add_message(_m(99, "added while unindexed"), D)
    b = st.Store(p)
    assert len(b.search("legacy text")) == 50 and ids(b.search("while unindexed")) == ["m99"]


def test_falls_back_to_like_when_fts_missing(s):
    s.add_message(_m(1, "plain words"), D)
    s.fts = False
    assert ids(s.search("plain")) == ["m1"]
    with s.lock:                                                   # broken index table mid-run -> LIKE, no exception
        s.db.execute("DROP TABLE msg_fts")
    s.fts = True
    assert ids(s.search("plain")) == ["m1"]


def test_100k_rows_timing(tmp_path):
    s = st.Store(tmp_path / "big.db")
    words = "hello chat nice play lol gg wow song music game boss run clip raid sub hype".split()
    with s.lock:
        s.db.executemany("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         [(f"b{i}", "twitch", "c", "1", f"user{i % 500}", "x", f"{words[i % 16]} {words[(i * 7) % 16]} msg{i}", 1000.0 + i, "{\"id\":\"b%d\"}" % i, 1.0, "low")
                          for i in range(100_000)])
        s.db.commit()
    t = time.perf_counter()
    r = s.search("msg99999")
    fts_ms = (time.perf_counter() - t) * 1000
    assert ids(r) == ["b99999"]
    t = time.perf_counter(); many = s.search("hello"); many_ms = (time.perf_counter() - t) * 1000
    assert len(many) == 100
    t = time.perf_counter()
    with s.lock:
        s.db.execute("SELECT json FROM messages WHERE text LIKE '%msg99999%' ESCAPE '!' ORDER BY ts DESC LIMIT 100").fetchall()
    like_ms = (time.perf_counter() - t) * 1000
    print(f"100k rows: fts rare={fts_ms:.1f} ms, fts common={many_ms:.1f} ms, like rare={like_ms:.1f} ms")
    assert fts_ms < 200 and many_ms < 500
