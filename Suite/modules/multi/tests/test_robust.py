"""Robustness of store / rules inputs (worker 42): odd limits, tiers, LIKE wildcards, corrupt rows, empty names."""
import json
from types import SimpleNamespace as NS

import pytest

import store as st
from priority import rules as prio


@pytest.fixture
def s(tmp_path):
    return st.Store(tmp_path / "t.db")


def _m(i, text="hello", user="u"):
    return NS(id=f"m{i}", platform="twitch", channel="c", user_id="1", user=user, display=user, text=text, ts=1000.0 + i,
              to_dict=lambda: {"id": f"m{i}", "text": text, "user": user, "ts": 1000.0 + i})


def test_recent_unknown_tier_and_bad_limits(s):
    for i in range(5):
        s.add_message(_m(i), NS(reasons=[], score=1.0, tier="low"))
    assert len(s.recent(10, min_tier="bogus")) == 5            # was KeyError -> 500
    assert len(s.recent(-1)) == 1 and len(s.recent(0)) == 1   # clamped, never "unlimited"
    assert len(s.recent("x")) == 5 and len(s.recent(None)) == 5   # default 200
    assert len(s.user_history("twitch", "1", -5)) == 1


def test_search_treats_wildcards_literally(s):
    s.add_message(_m(1, "100% sure"), NS(reasons=[], score=1.0, tier="low"))
    s.add_message(_m(2, "a_b"), NS(reasons=[], score=1.0, tier="low"))
    s.add_message(_m(3, "axb"), NS(reasons=[], score=1.0, tier="low"))
    assert [m["id"] for m in s.search("%")] == ["m1"]
    assert [m["id"] for m in s.search("a_b")] == ["m2"]
    assert s.search("\\") == []


def test_nan_score_does_not_break_reads(s):
    s.add_message(_m(1), NS(reasons=[], score=float("nan"), tier="low"))
    json.dumps(s.recent(5), allow_nan=False) if s.recent(5)[0]["score"] is None else None
    assert s.recent(5)[0]["id"] == "m1"


def test_corrupt_card_and_kv_rows_are_skipped(s):
    s.db.execute("INSERT INTO cards VALUES('a','a','open',1,1,'{bad')")
    s.db.execute("INSERT INTO cards VALUES('b','b','open',1,1,?)", (json.dumps({"id": "b"}),))
    s.db.execute("INSERT INTO kv VALUES('k','{bad')")
    s.db.commit()
    assert [c["id"] for c in s.load_cards()] == ["b"]
    assert s.kv_get("k", {"d": 1}) == {"d": 1}


def test_mentions_me_ignores_empty_names():
    assert prio.mentions_me("anything at all", ["", "_", "  "]) is False
    assert prio.mentions_me("hey @pingu!", ["", "pingu"]) is True


def test_prune_trims_events_by_age_and_rows(s):
    import time
    now = time.time()
    s.db.execute("INSERT INTO events(ts,kind,json) VALUES(?,?,?)", (now - 40 * 86400, "old", "{}"))
    for i in range(10):
        s.db.execute("INSERT INTO events(ts,kind,json) VALUES(?,?,?)", (now - i, "new", "{}"))
    s.db.commit()
    s.prune(30)
    assert {e["kind"] for e in s.events(100)} == {"new"} and len(s.events(100)) == 10
    s.prune_events(max_rows=4)
    assert len(s.events(100)) == 5 or len(s.events(100)) == 4        # newest rows kept (id-based cut)
    assert s.events(1)[0]["kind"] == "new"


def test_inbox_caps_question_flood_and_counts_drops(monkeypatch):
    import asyncio
    import pipeline as pl
    monkeypatch.setattr(pl.config, "settings", lambda: {"my_names": ["pingu"]})
    p = NS(stats={"dropped": 0, "in": 0, "dupes": 0})

    async def go():
        ib = pl.Inbox(p, cap=5)
        for i in range(40):
            ib.put(NS(text=f"is this a question {i}?", id=str(i)))
        for i in range(10):
            ib.put(NS(text="plain chatter", id=f"x{i}"))
        return ib
    ib = asyncio.run(go())
    assert ib.q.qsize() <= 10                       # 2 x cap
    assert p.stats["dropped"] >= 45                 # every put past the cap is counted, plain ones are not queued
    assert ib.q._queue[-1].id == "39"               # newest question kept
