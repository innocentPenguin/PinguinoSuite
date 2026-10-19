import asyncio
import time

import windows as win
from cards import CardManager
from connectors.twitch import normalize_event
from dedupe import Seen
from models import ChatMessage
from pipeline import Inbox, Pipeline
from priority import rules as prio
from store import Store

_n = [0]


def mk(text, user="viewer", id=None, **kw):
    _n[0] += 1
    return ChatMessage(id=id or f"twitch:c:auto{_n[0]}", platform="twitch", channel="c", user_id=user, user=user,
                       display=user, text=text, ts=kw.pop("ts", time.time()), **kw)


def rule_names(d):
    return {r["rule"] for r in d.reasons}


# priority -----------------------------------------------------------
def test_question_and_mention_score_high():
    d = prio.score(mk("@innocentpenguin what game is next?"), prio.Context(), prio.load_rules())
    assert {"mention", "question"} <= rule_names(d)
    assert d.tier in ("medium", "high")


def test_plain_chatter_is_none():
    assert prio.score(mk("lol"), prio.Context(user_count=3), prio.load_rules()).tier == "none"


def test_subscriber_not_automatically_important():
    d = prio.score(mk("nice one", badges=["subscriber"]), prio.Context(user_count=3), prio.load_rules())
    assert d.tier == "none"


def test_spam_repeat_penalised():
    now = time.time()
    hist = [(now - 5, "what is this?", False)] * 3
    d = prio.score(mk("what is this?", ts=now), prio.Context(recent_by_user=hist), prio.load_rules())
    assert "spam_repeat" in rule_names(d)


def test_repeated_mentions_decay():
    now = time.time()
    r = prio.load_rules()
    first = prio.score(mk("@innocentpenguin hi", ts=now), prio.Context(), r)
    third = prio.score(mk("@innocentpenguin hi again", ts=now),
                       prio.Context(recent_by_user=[(now - 3, "x", True), (now - 2, "y", True)]), r)
    assert third.score < first.score


def test_bot_and_self_ignored():
    r = prio.load_rules()
    assert prio.score(mk("@innocentpenguin?", user="nightbot"), prio.Context(), r).tier == "none"
    assert prio.score(mk("@innocentpenguin?", is_self=True), prio.Context(), r).tier == "none"


def test_muted_user_ignored():
    prio.save_rules({"muted": ["troll"]})
    assert prio.score(mk("@innocentpenguin why?", user="troll"), prio.Context(), prio.load_rules()).tier == "none"


def test_reasons_sum_to_score():
    d = prio.score(mk("@innocentpenguin how are you?"), prio.Context(), prio.load_rules())
    assert abs(sum(r["points"] for r in d.reasons) - d.score) < 0.5


def test_rules_reset():
    prio.save_rules({"weights": {"question": 99}})
    assert prio.load_rules()["weights"]["question"] == 99
    prio.reset_rules()
    assert prio.load_rules()["weights"]["question"] == prio.DEFAULT_RULES["weights"]["question"]


# dedupe / store ------------------------------------------------------
def test_seen_lru():
    s = Seen(cap=2)
    assert s.add("a") and not s.add("a")
    s.add("b")
    s.add("c")
    assert s.add("a")


def test_store_duplicate_and_prune(tmp_path):
    st = Store(tmp_path / "x.db")
    m = mk("hello", id="twitch:c:1")
    d = prio.Decision(0, "none", [])
    assert st.add_message(m, d) and not st.add_message(m, d)
    assert st.user_count("twitch", "viewer") == 1
    assert st.search("hell")
    st.add_message(mk("old", id="twitch:c:2", ts=time.time() - 40 * 86400), d)
    st.prune(30)
    assert st.get_message("twitch:c:2") is None and st.get_message("twitch:c:1")


# cards ----------------------------------------------------------------
class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def mkcards(tmp_path):
    clk = Clock()
    return CardManager(Store(tmp_path / "c.db"), clock=clk), clk


def hi():
    return prio.Decision(60, "high", [{"rule": "question", "points": 25, "detail": ""}])


def test_card_missed_after_timer(tmp_path):
    cm, clk = mkcards(tmp_path)
    c = cm.maybe_create(mk("q?", id="twitch:c:a"), hi())
    clk.t += 299
    cm.tick()
    assert c["state"] == "open"
    clk.t += 2
    cm.tick()
    assert c["state"] == "missed"
    cm.reopen(c["id"])
    assert c["state"] == "open"


def test_answered_fades_after_15s(tmp_path):
    cm, clk = mkcards(tmp_path)
    c = cm.maybe_create(mk("q?", id="twitch:c:a"), hi())
    cm.answer(c["id"], "typed")
    assert cm.view()["answered"]
    clk.t += 16
    cm.tick()
    assert not cm.view()["answered"]


def test_snooze_returns(tmp_path):
    cm, clk = mkcards(tmp_path)
    c = cm.maybe_create(mk("q?", id="twitch:c:a"), hi())
    cm.snooze(c["id"], 60)
    assert not cm.view()["open"]
    clk.t += 61
    cm.tick()
    assert cm.view()["open"]


def test_low_tier_no_card(tmp_path):
    cm, _ = mkcards(tmp_path)
    assert cm.maybe_create(mk("hi", id="twitch:c:z"), prio.Decision(5, "low", [])) is None


def test_platform_reply_and_mention_close(tmp_path):
    cm, _ = mkcards(tmp_path)
    a = cm.maybe_create(mk("q1?", user="ann", id="twitch:c:a"), hi())
    b = cm.maybe_create(mk("q2?", user="bob", id="twitch:c:b"), hi())
    cm.on_own_message(mk("answer", user="me", id="twitch:c:m1", reply_to="twitch:c:a", is_self=True))
    assert a["state"] == "answered" and a["answered_via"] == "platform_reply" and b["state"] == "open"
    cm.on_own_message(mk("@bob sure", user="me", id="twitch:c:m2", is_self=True))
    assert b["state"] == "answered"


def test_other_platform_does_not_close(tmp_path):
    cm, _ = mkcards(tmp_path)
    a = cm.maybe_create(mk("q?", user="ann", id="twitch:c:a"), hi())
    own = mk("@ann hi", user="me", id="yt:c:m", is_self=True)
    own.platform = "youtube"
    cm.on_own_message(own)
    assert a["state"] == "open"


def test_cards_survive_restart(tmp_path):
    st = Store(tmp_path / "r.db")
    CardManager(st).maybe_create(mk("q?", id="twitch:c:a"), hi())
    assert len(CardManager(st).view()["open"]) == 1


# pipeline ---------------------------------------------------------------
def make_pipeline(tmp_path):
    st = Store(tmp_path / "p.db")
    events = []
    return Pipeline(st, CardManager(st, events.append), events.append), events


def test_pipeline_reconnect_replay_no_duplicates(tmp_path):
    p, ev = make_pipeline(tmp_path)
    m = mk("@innocentpenguin what is this?", id="twitch:c:same")
    assert p.ingest(m) and p.ingest(m) is None
    assert sum(1 for e in ev if e["type"] == "message") == 1
    p.seen = type(p.seen)()
    assert p.ingest(m) is None


def test_pipeline_creates_card_for_question(tmp_path):
    p, _ = make_pipeline(tmp_path)
    p.ingest(mk("@innocentpenguin how do you do that?", id="twitch:c:q"))
    assert p.cards.view()["open"]


def test_burst_keeps_priority(tmp_path):
    p, _ = make_pipeline(tmp_path)
    ib = Inbox(p, cap=100)
    for i in range(1000):
        ib.put(mk(f"spam {i}", user=f"u{i}", id=f"twitch:c:s{i}"))
    ib.put(mk("@innocentpenguin real question?", id="twitch:c:keep"))
    assert ib.q.qsize() <= 101 and p.stats["dropped"] > 800

    async def drain():
        t = asyncio.create_task(ib.run())
        await asyncio.sleep(0.5)
        t.cancel()

    asyncio.run(drain())
    assert p.store.get_message("twitch:c:keep")


# twitch normalize -------------------------------------------------------
def test_normalize_event():
    ev = {"broadcaster_user_login": "chan", "message_id": "abc", "chatter_user_id": "9", "chatter_user_login": "bob",
          "chatter_user_name": "Bob", "message": {"text": "hi"}, "badges": [{"set_id": "subscriber"}],
          "message_type": "user_intro", "reply": {"parent_message_id": "p1", "parent_user_login": "me"}}
    m = normalize_event(ev)
    assert m.id == "twitch:chan:abc" and m.first_time and m.reply_to == "twitch:chan:p1" and m.badges == ["subscriber"]


# windows ----------------------------------------------------------------
M1 = {"id": "A", "x": 0, "y": 0, "w": 1920, "h": 1080, "scale": 1.0, "primary": True}
M2 = {"id": "B", "x": 1920, "y": 0, "w": 2560, "h": 1440, "scale": 1.5, "primary": False}


def test_monitor_disconnect_snaps_and_restores():
    w = win.describe_geometry(win.new_window(type="priority", x=2200, y=100, w=400, h=500), [M1, M2])
    assert w["monitor"] == "B"
    g = win.place(w, [M1])
    assert 0 <= g["x"] <= 1920 - g["w"]
    assert w["x"] == 2200
    assert win.place(w, [M1, M2])["x"] == 2200


def test_dpi_change_scales_size():
    w = win.describe_geometry(win.new_window(x=2000, y=50, w=400, h=500), [M1, M2])
    assert win.place(w, [M1, dict(M2, scale=3.0)])["w"] > 400


def test_oversized_window_clamped():
    g = win.place(win.new_window(x=-500, y=-500, w=5000, h=5000), [M1])
    assert g["w"] == 1920 and g["x"] == 0


def test_no_monitors_passthrough():
    assert win.place(win.new_window(x=5, y=6), [])["x"] == 5


def test_profiles_defined():
    assert {"Streaming", "Gaming", "Editing", "IRL", "Minimal", "Full Monitoring"} <= set(win.PROFILE_DEFAULTS)


def test_checks_report_without_tokens(monkeypatch):
    import checks
    import secrets_store

    class R:
        status_code = 302
        headers = {"location": "https://id.twitch.tv/x?scope=user%3Aread%3Achat+user%3Awrite%3Achat"}

    monkeypatch.setattr(checks.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(checks.requests, "post", lambda *a, **k: type("P", (), {"status_code": 400})())
    monkeypatch.setattr(secrets_store, "get", lambda n, d=None: None)

    class TW:
        state = {"status": "needs_auth", "detail": "x"}
    res = {c["id"]: c for c in checks.run(TW())}
    assert res["connect"]["ok"] and res["refresh"]["ok"]
    assert not res["token"]["ok"] and res["token"]["fix"]
    assert not res["connector"]["ok"]
    assert "access_token" not in str(res)


def test_checks_scope_missing(monkeypatch):
    import checks
    import secrets_store

    class R:
        status_code = 200
        headers = {"location": "x"}

    monkeypatch.setattr(checks.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(checks.requests, "post", lambda *a, **k: type("P", (), {"status_code": 400})())
    monkeypatch.setattr(secrets_store, "get", lambda n, d=None: {"access_token": "SECRET"} if n == "twitch_tokens" else None)

    class TW:
        state = {"status": "connected", "detail": ""}
        def validate(self, t): return {"login": "me", "scopes": ["user:read:chat"]}
    res = {c["id"]: c for c in checks.run(TW())}
    assert res["valid"]["ok"] and not res["scopes"]["ok"]
    assert "user:write:chat" in res["scopes"]["detail"]
    assert "SECRET" not in str(res)
