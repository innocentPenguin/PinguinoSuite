"""History never clears: kind=chat|events paging, `cleared` tag on mod delete/timeout/ban/clear, Twitch delete/clear subscriptions."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import server
import store as store_mod
from connectors import twitch as tw
from models import ChatMessage, Decision
from store import Store


def _add(s, i, ts, event="", user="amy", channel="c", notice=False, text="hi"):
    m = ChatMessage(id=f"twitch:{channel}:{i}", platform="twitch", channel=channel, user_id=user, user=user, display=user,
                    text=text, ts=ts, event=event, meta={"notice": True} if notice else {})
    assert s.add_message(m, Decision(0, "none", []))
    return m.id


def _filled(tmp_path):
    s = Store(tmp_path / "a.db")
    t0 = time.time() - 1000
    for i in range(30):
        _add(s, f"c{i}", t0 + i)                                  # chat
        if i % 5 == 0:
            _add(s, f"e{i}", t0 + i + 0.5, event=["sub", "raid", "follow", "redeem", "cheer", "gift"][i // 5 % 6], user="fan")
    _add(s, "n1", t0 + 40, notice=True, user="sys")               # a notice flagged only through meta
    _add(s, "h1", t0 + 41, event="highlighted")                   # highlighted message is still chat
    return s, t0


def test_kind_filters_and_older_paging(tmp_path):
    s, t0 = _filled(tmp_path)
    chat, ev = s.recent(1000, kind="chat"), s.recent(1000, kind="events")
    assert len(chat) == 31 and all(m["event"] in ("", "highlighted") for m in chat)
    assert len(ev) == 7 and {m["id"] for m in ev} >= {"twitch:c:e0", "twitch:c:n1"}
    assert len(s.recent(1000)) == 38 and [m["ts"] for m in ev] == sorted(m["ts"] for m in ev)     # oldest -> newest
    page = s.recent(3, kind="events")
    older = s.recent(3, kind="events", before=page[0]["ts"])
    assert [m["id"] for m in older] and max(m["ts"] for m in older) < page[0]["ts"]
    assert len(s.recent(5, platform="twitch", kind="chat", min_tier="none")) == 5


def test_event_index_is_used(tmp_path):
    s, _ = _filled(tmp_path)
    plan = " ".join(r[3] for r in s.db.execute(
        "EXPLAIN QUERY PLAN SELECT json FROM messages WHERE (%s) = 1 AND ts<? ORDER BY ts DESC LIMIT 5" % store_mod.EV_EXPR, (time.time(),)))
    assert "ix_msg_ev" in plan


def test_cleared_is_persisted_never_deleted(tmp_path):
    s, t0 = _filled(tmp_path)
    n = len(s.recent(1000))
    assert s.mark_cleared(["twitch:c:c3", "nope"], "delete") == ["twitch:c:c3"]
    assert s.mark_cleared([], "delete") == []
    s.db.close()
    s2 = Store(tmp_path / "a.db")                                   # a restart / page reload sees the tag
    m = s2.get_message("twitch:c:c3")
    assert m["cleared"] is True and m["cleared_reason"] == "delete" and len(s2.recent(1000)) == n
    assert "cleared" not in s2.get_message("twitch:c:c4")
    s2.mark_cleared(["twitch:c:c3"], "ban")
    assert s2.get_message("twitch:c:c3")["cleared_reason"] == "delete"        # the first reason stays


def test_cleared_user_and_all(tmp_path):
    s, t0 = _filled(tmp_path)
    _add(s, "x1", t0 + 50, user="bob")
    _add(s, "x2", t0 + 51, user="bob", channel="other")
    _add(s, "x3", time.time() - 99999, user="bob")                  # old line is left alone
    _add(s, "ev1", t0 + 52, user="bob", event="follow")             # an event of the same user stays untagged
    assert s.mark_cleared_user("twitch", "c", "bob", "timeout", since=t0) == ["twitch:c:x1"]
    assert not s.get_message("twitch:other:x2").get("cleared") and not s.get_message("twitch:c:ev1").get("cleared")
    ids = s.mark_cleared_all("twitch", "c", "clear", limit=4)
    assert len(ids) == 4 and not any(i.startswith("twitch:c:e") for i in ids)
    assert len(s.mark_cleared_all("twitch", "c", "clear", limit=500)) >= 31
    assert len(s.recent(1000)) == 42                                 # nothing was removed


# ---- API ---------------------------------------------------------------------------------------------------
@pytest.fixture()
def api(tmp_path, monkeypatch):
    s, t0 = _filled(tmp_path)
    monkeypatch.setattr(server, "store", s)
    emitted = []
    monkeypatch.setattr(server.hub, "emit", lambda e: emitted.append(e))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766", raise_server_exceptions=False)
    return c, s, emitted, {"origin": "http://127.0.0.1:8766"}


def test_messages_endpoint_kind(api):
    c, s, emitted, h = api
    assert len(c.get("/api/messages?limit=1000").json()) == 38
    assert len(c.get("/api/messages?limit=1000&kind=chat").json()) == 31
    ev = c.get("/api/messages?limit=1000&kind=events").json()
    assert len(ev) == 7
    older = c.get(f"/api/messages?kind=events&limit=3&before={ev[-1]['ts']}").json()
    assert len(older) == 3 and all(m["ts"] < ev[-1]["ts"] for m in older)
    assert len(c.get("/api/messages?kind=bogus&limit=1000").json()) == 38           # unknown kind = all (old behaviour)


def test_mod_buttons_tag_instead_of_remove(api, monkeypatch):
    c, s, emitted, h = api
    calls = []

    class Conn:
        async def moderate(self, action, **kw):
            calls.append((action, kw))
    monkeypatch.setitem(server.connectors, "twitch", Conn())
    assert c.post("/api/mod/delete", json={"message_id": "twitch:c:c1"}, headers=h).status_code == 200
    assert emitted[-1]["type"] == "message.cleared" and emitted[-1]["ids"] == ["twitch:c:c1"] and emitted[-1]["scope"] == "message"
    assert emitted[-1]["reason"] == "delete" and s.get_message("twitch:c:c1")["cleared"]
    assert c.post("/api/mod/timeout", json={"message_id": "twitch:c:c9", "seconds": 1}, headers=h).status_code == 200
    e = emitted[-1]
    assert e["scope"] == "user" and e["reason"] == "timeout" and e["user_id"] == "amy" and "twitch:c:c9" in e["ids"]
    assert s.get_message("twitch:c:c9")["cleared_reason"] == "timeout" and len(s.recent(1000)) == 38


# ---- Twitch frames -----------------------------------------------------------------------------------------
def _frame(typ, event, fid):
    return {"metadata": {"message_type": "notification", "subscription_type": typ, "message_id": fid, "message_timestamp": "2026-10-23T22:00:00Z"},
            "payload": {"event": event}}


def _twitch(monkeypatch):
    t = tw.Twitch(None, lambda e: None)
    t.user, t.broadcaster_id = {"login": "me", "user_id": "1"}, "2"
    got = []
    t.on_cleared = lambda scope, reason, **kw: got.append((scope, reason, kw))
    return t, got


def test_twitch_delete_clear_user_clear_frames(monkeypatch):
    t, got = _twitch(monkeypatch)
    run = lambda f: asyncio.run(t.handle_frame(f, "tok"))
    assert run(_frame("channel.chat.message_delete", {"broadcaster_user_login": "chan", "target_user_id": "9", "message_id": "m7"}, "f1")) is None
    assert got[-1] == ("message", "delete", {"platform": "twitch", "channel": "chan", "ids": ["twitch:chan:m7"]})
    run(_frame("channel.chat.clear_user_messages", {"broadcaster_user_login": "chan", "target_user_id": "9", "target_user_login": "x"}, "f2"))
    assert got[-1] == ("user", "timeout", {"platform": "twitch", "channel": "chan", "user_id": "9"})
    t.recent_bans["9"] = time.time()                                # we banned them a moment ago
    run(_frame("channel.chat.clear_user_messages", {"broadcaster_user_login": "chan", "target_user_id": "9"}, "f3"))
    assert got[-1][:2] == ("user", "ban")
    run(_frame("channel.chat.clear", {"broadcaster_user_login": "chan"}, "f4"))
    assert got[-1] == ("all", "clear", {"platform": "twitch", "channel": "chan"})
    run(_frame("channel.chat.clear", {"broadcaster_user_login": "chan"}, "f4"))        # redelivered frame: handled once
    assert len(got) == 4


def test_twitch_bad_frames_and_no_callback_do_not_break_the_session(monkeypatch):
    t, got = _twitch(monkeypatch)
    run = lambda f: asyncio.run(t.handle_frame(f, "tok"))
    run(_frame("channel.chat.message_delete", {"broadcaster_user_login": "chan"}, "b1"))      # no message_id
    run(_frame("channel.chat.clear_user_messages", {}, "b2"))
    assert got == []
    emitted = []
    t.emit, t.on_cleared = emitted.append, None
    run(_frame("channel.chat.message_delete", {"broadcaster_user_login": "chan", "message_id": "m1"}, "b3"))
    assert emitted[-1] == {"type": "message.cleared", "ids": ["twitch:chan:m1"], "scope": "message", "user_id": "", "reason": "delete"}


def test_optional_subscriptions_fail_softly_and_revocation_keeps_chat(monkeypatch):
    t, got = _twitch(monkeypatch)
    t.session_id = "s"
    tok = {"access_token": "a", "client_id": "c"}
    monkeypatch.setattr(t, "tokens", lambda: tok)
    posted = []

    class R:
        def __init__(self, code):
            self.status_code, self.headers, self.text = code, {}, ""
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: posted.append((k["json"]["type"], k["json"]["condition"])) or R(409 if len(posted) == 2 else (202 if len(posted) == 1 else 403)))
    t._subscribe(tok)
    assert [p[0] for p in posted] == ["channel.chat.message"] + list(tw.EXTRA_SUBS)
    assert all(p[1] == {"broadcaster_user_id": "2", "user_id": "1"} for p in posted)
    for typ in tw.EXTRA_SUBS:
        rev = {"metadata": {"message_type": "revocation", "message_id": "r" + typ}, "payload": {"subscription": {"type": typ, "status": "x"}}}
        assert asyncio.run(t.handle_frame(rev, tok)) is None
