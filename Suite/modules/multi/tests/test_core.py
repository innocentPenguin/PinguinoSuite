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


def test_guard_origin_host_token(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    monkeypatch.setenv("PINGUINO_API_TOKEN", "tok")
    monkeypatch.setattr(server.secrets_store, "delete", lambda n: None)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    assert c.get("/api/status", headers={"host": "evil.com"}).status_code == 403
    assert c.post("/auth/disconnect", headers={"origin": "https://evil.com"}).status_code == 403
    assert c.post("/auth/disconnect").status_code == 401                       # no origin, no token
    assert c.post("/auth/disconnect", headers={"x-pinguino-token": "tok"}).status_code == 200
    assert c.post("/auth/disconnect", headers={"origin": "http://127.0.0.1:8766"}).status_code == 200  # embedded iframe
    assert c.post("/auth/disconnect", headers={"origin": "tauri://localhost"}).status_code == 401      # Tauri origin needs token
    assert c.post("/auth/disconnect", headers={"origin": "tauri://localhost", "authorization": "Bearer tok"}).status_code == 200
    assert "x-frame-options" not in {k.lower() for k in c.get("/").headers}


# learning -------------------------------------------------------------
def _ev(kind, rules, ts, **kw):
    return dict(kind=kind, rules=rules, ts=ts, **kw)


def test_learning_needs_evidence_and_is_bounded():
    import learning
    now = time.time()
    few = [_ev("answered", ["question"], now) for _ in range(3)]
    assert learning.compute(few, now)["question"]["delta"] == 0
    many = [_ev("answered", ["question"], now) for _ in range(200)]
    d = learning.compute(many, now)["question"]["delta"]
    assert 0 < d <= prio.DEFAULT_RULES["weights"]["question"] * learning.CAP_FRAC
    neg = [_ev("dismissed", ["link"], now) for _ in range(200)]
    assert learning.compute(neg, now)["link"]["delta"] < 0


def test_learning_decays_and_resets(tmp_path):
    import learning
    now = time.time()
    old = [_ev("answered", ["mention"], now - 200 * 86400) for _ in range(8)]
    assert learning.compute(old, now)["mention"]["delta"] == 0   # decayed below evidence floor
    st = Store(tmp_path / "l.db")
    for _ in range(8):
        st.log_event("answered", {"rules": ["mention"], "user_id": "u"})
    assert learning.refresh(st)["mention"]["delta"] > 0
    assert st.kv_get("learned")["mention"] > 0
    learning.reset(st)
    assert learning.refresh(st) == {} and not st.kv_get("learned")


# hotkeys + linked feed ---------------------------------------------
def test_hotkey_acts_on_top_card(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import server
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    monkeypatch.setattr(server, "store", Store(tmp_path / "h.db"))
    server.cards.store = server.store
    server.cards.cards.clear()
    base = dict(user_id="u", user="u", platform="twitch", text="x", reasons=[], context=[], tier="high", message_id="m",
                state="open", created=1, updated=1, answered_at=None, answered_via=None, snooze_until=None, faded=False)
    server.cards.cards["c:a"] = dict(base, id="c:a", score=40)
    server.cards.cards["c:b"] = dict(base, id="c:b", score=80)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    r = c.post("/api/hotkey/answer", headers={"origin": "http://127.0.0.1:8766"}).json()
    assert r["ok"] and r["card"] == "c:b" and server.cards.cards["c:b"]["answered_via"] == "hotkey"
    assert c.post("/api/hotkey/nope", headers={"origin": "http://127.0.0.1:8766"}).status_code == 400


# discord ----------------------------------------------------------
def test_discord_normalize_and_filter():
    from connectors.discord import normalize_message
    d = {"id": "9", "channel_id": "5", "content": "hey @me?", "author": {"id": "1", "username": "Fan", "global_name": "Fan!"},
         "message_reference": {"message_id": "7"}, "referenced_message": {"author": {"username": "Me"}}}
    m = normalize_message(d, ["5"], my_id="2")
    assert m.id == "discord:5:9" and m.reply_to == "discord:5:7" and m.reply_to_user == "me" and not m.is_self
    assert normalize_message(d, ["6"]) is None
    assert normalize_message(dict(d, author={"id": "2", "username": "me"}), ["5"], my_id="2").is_self


def test_discord_token_write_only(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    kept = {}
    monkeypatch.setattr(server.secrets_store, "put", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(server.secrets_store, "get", lambda k, d=None: kept.get(k, d))
    monkeypatch.setattr(server.config, "save_settings", lambda p: p)
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    r = c.post("/api/secrets/discord", json={"token": "x" * 30, "channels": ["12", "ab"]},
               headers={"origin": "http://127.0.0.1:8766"})
    assert r.json() == {"ok": True, "has_token": True} and "x" * 30 not in r.text


# ai assist ---------------------------------------------------------
def _advisor(tmp_path, monkeypatch, call, mode="auto"):
    import ai, config, secrets_store
    from store import Store
    monkeypatch.setattr(config, "settings", lambda: dict(config.DEFAULTS, priority_mode=mode))
    monkeypatch.setattr(secrets_store, "get", lambda k, d=None: "k" * 20)
    return ai.Advisor(Store(tmp_path / "a.db"), call=call)


def test_ai_refine_cache_and_fallback(tmp_path, monkeypatch):
    import asyncio
    n = {"c": 0}

    def ok(*a):
        n["c"] += 1
        return '{"need": 9}'

    a = _advisor(tmp_path, monkeypatch, ok)
    r1 = asyncio.run(a.refine("u", "what game is next?"))
    r2 = asyncio.run(a.refine("u", "What game is next"))
    assert r1["delta"] == 12.0 and r2 == r1 and n["c"] == 1 and a.stats["cache_hits"] == 1

    def bad(*a):
        raise TimeoutError()

    b = _advisor(tmp_path, monkeypatch, bad)
    assert asyncio.run(b.refine("u", "another long question?")) is None and b.stats["fallbacks"] == 1


def test_ai_gating_and_spend_cap(tmp_path, monkeypatch):
    import asyncio, config
    a = _advisor(tmp_path, monkeypatch, lambda *x: '{"need": 5}')
    rules = {"tiers": {"high": 50, "medium": 30, "low": 15}}
    assert a.wants(28, "is this a real question", rules) and not a.wants(5, "is this a real question", rules)
    assert not a.wants(28, "hi", rules)
    local = _advisor(tmp_path, monkeypatch, lambda *x: '{"need": 5}', mode="local")
    assert not local.wants(28, "is this a real question", rules)
    a.store.kv_set("ai_spend", {"day": a._day(), "usd": 99.0, "calls": 1})
    assert asyncio.run(a.refine("u", "capped question here?")) is None and a.stats["last_fallback"] == "daily spend cap"


def test_ai_rescore_creates_card_and_survives_failure(tmp_path, monkeypatch):
    import asyncio, config, secrets_store
    monkeypatch.setattr(config, "settings", lambda: dict(config.DEFAULTS, priority_mode="auto"))
    monkeypatch.setattr(secrets_store, "get", lambda k, d=None: "k" * 20)
    p, ev = make_pipeline(tmp_path)
    p.advisor.call = lambda *a: '{"need": 10}'
    m = ChatMessage(id="t:1", platform="twitch", channel="c", user_id="9", user="v", display="v",
                    text="interesting stream tonight friends", ts=time.time())
    out = p.ingest(m)
    assert out["tier"] == "low" and out.pop("_ai") and "c:t:1" not in p.cards.cards
    asyncio.run(p.refine(out))
    assert p.cards.cards["c:t:1"]["tier"] in ("medium", "high")
    assert p.store.get_message("t:1")["tier"] in ("medium", "high")
    assert any(e["type"] == "message.rescored" for e in ev)


def test_youtube_normalize():
    from connectors.youtube import normalize_item
    it = {"id": "x1", "snippet": {"type": "textMessageEvent", "textMessageDetails": {"messageText": "hello?"}},
          "authorDetails": {"channelId": "UC1", "displayName": "Fan", "isChatSponsor": True}}
    m = normalize_item(it, "chat9", "UC2")
    assert m.id == "youtube:chat9:x1" and m.badges == ["subscriber"] and not m.is_self and m.text == "hello?"
    assert normalize_item({"id": "y", "snippet": {"type": "superChatEvent"}}, "chat9") is None
    assert normalize_item(it, "chat9", "UC1").is_self


def test_voice_match_never_autocloses():
    import voice
    cards = [{"id": "c1", "state": "open", "user": "bob", "text": "which graphics card are you using for streaming?"},
             {"id": "c2", "state": "open", "user": "amy", "text": "lol nice"},
             {"id": "c3", "state": "answered", "user": "zed", "text": "which graphics card are you using"}]
    r = voice.match("so bob asked which graphics card I am using for streaming it's a 4070", cards)
    assert [x["card_id"] for x in r] == ["c1"] and r[0]["confidence"] >= 0.5
    assert voice.match("completely unrelated talk about cats", cards) == []


def test_claims_endpoint_lists_open_priority_cards(tmp_path):
    p, ev = make_pipeline(tmp_path)
    m = ChatMessage(id="t:c1", platform="twitch", channel="c", user_id="9", user="v", display="v",
                    text="@innocentpenguin when is the giveaway?", ts=time.time())
    p.ingest(m)
    assert any(c["tier"] in ("medium", "high") for c in p.cards.cards.values())


def test_listen_bridge_forwards_segments_to_suggestions(monkeypatch):
    import asyncio, json, config, websockets, listen_bridge
    monkeypatch.setattr(config, "settings", lambda: dict(config.DEFAULTS, voice_enabled=True))

    class C:
        cards = {"c1": {"id": "c1", "state": "open", "user": "bob", "text": "which graphics card are you using?"}}

    got = []

    async def go():
        async def handler(ws):
            await ws.send(json.dumps({"type": "segment", "segment": {"text": "bob asked which graphics card"}}))
            await ws.send(json.dumps({"type": "segment", "segment": {"text": "I am using a 4070"}}))
            await asyncio.sleep(0.3)
        async with websockets.serve(handler, "127.0.0.1", 18765):
            t = asyncio.create_task(listen_bridge.run(C, got.append, "ws://127.0.0.1:18765"))
            await asyncio.sleep(1)
            t.cancel()

    asyncio.run(go())
    assert any(e["type"] == "reply.suggested" and e["card_id"] == "c1" for e in got)


def test_tiktok_unofficial_readonly_normalize():
    from types import SimpleNamespace as N
    from connectors.tiktok import TikTok, normalize_comment
    m = normalize_comment(N(user=N(user_id=7, unique_id="Fan", nickname="Fan!"), comment="hi?", msg_id="m1"), "host")
    assert m.id == "tiktok:host:m1" and m.platform == "tiktok" and m.user == "fan" and m.text == "hi?"
    assert TikTok.official is False and TikTok.capabilities["send"] is False


def test_recap_lists_only_unanswered_best_first(tmp_path):
    cm, clk = mkcards(tmp_path)
    a = cm.maybe_create(mk("a?", id="twitch:c:a"), hi())
    b = cm.maybe_create(mk("b?", id="twitch:c:b"), prio.Decision(80, "high", hi().reasons))
    c = cm.maybe_create(mk("c?", id="twitch:c:c"), hi())
    cm.answer(c["id"], "typed")
    clk.t += 400
    cm.tick()
    assert [x["id"] for x in cm.recap()] == [b["id"], a["id"]]


def test_viewer_note_roundtrip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server
    from store import Store
    monkeypatch.setattr(server, "store", Store(tmp_path / "n.db"))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    h = {"origin": "http://127.0.0.1:8766"}
    assert c.post("/api/viewers/Bob/note", json={"note": "likes cats " * 100}, headers=h).json()["note"].startswith("likes cats")
    got = c.get("/api/viewers/bob/note").json()
    assert got["user"] == "bob" and len(got["note"]) == 500


def test_combined_chat_window_and_profile():
    import windows as w
    assert w.new_window(type="chat")["type"] == "chat"
    assert w.PROFILE_DEFAULTS["Combined Chat"][0]["type"] == "chat"


def test_console_log_format_and_scrub(tmp_path, monkeypatch):
    import json, console_log
    f = tmp_path / "x" / "multi.jsonl"
    monkeypatch.setenv("MULTI_CONSOLE_FILE", str(f))
    console_log.warn("twitch", "auth failed Bearer abc123def456 token=SECRETVALUE1234567890123456789012345")
    console_log.info("server", "hello")
    console_log.info("server", "dup", dedupe_s=60)
    console_log.info("server", "dup", dedupe_s=60)
    rows = [json.loads(x) for x in f.read_text("utf-8").splitlines()]
    assert [r["level"] for r in rows] == ["warn", "info", "info"]
    assert set(rows[0]) == {"ts", "module", "level", "source", "msg"} and rows[0]["module"] == "multi"
    assert isinstance(rows[0]["ts"], float)
    console_log.write_prestream([{"id": "a", "label": "A", "status": "pass", "detail": ""}])
    assert json.loads((f.parent / "prestream-multi.json").read_text("utf-8"))["items"][0]["id"] == "a"
    assert "abc123def456" not in rows[0]["msg"] and "SECRETVALUE" not in rows[0]["msg"]


def test_connector_status_changes_are_logged(tmp_path, monkeypatch):
    import json, console_log
    from connectors.base import Connector
    f = tmp_path / "m.jsonl"
    monkeypatch.setenv("MULTI_CONSOLE_FILE", str(f))
    c = Connector(None, lambda e: None)
    c.platform = "demo"
    c.set_status("reconnecting", "boom")
    c.set_status("connecting")
    c.set_status("connected", "ok")
    lv = [json.loads(x)["level"] for x in f.read_text("utf-8").splitlines()]
    assert lv == ["warn", "info"]


def test_prestream_endpoint_shape_and_no_token_needed():
    from fastapi.testclient import TestClient
    import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    r = c.get("/api/prestream")
    body = r.json()
    rows = body["items"]
    assert r.status_code == 200 and isinstance(body["ts"], float) and rows and all(set(x) == {"id", "label", "status", "detail", "help"} for x in rows)
    assert all(x["status"] in ("pass", "warn", "fail") for x in rows)
    assert {"store", "queue", "windows"} <= {x["id"] for x in rows}


def test_twitch_normalize_color_and_emotes():
    from connectors.twitch import normalize_event
    ev = {"broadcaster_user_login": "ch", "message_id": "m1", "chatter_user_id": "9", "chatter_user_login": "fan",
          "chatter_user_name": "Fan", "color": "#FF4500", "badges": [{"set_id": "moderator"}],
          "message": {"text": "hi Kappa", "fragments": [{"type": "text", "text": "hi "}, {"type": "emote", "text": "Kappa", "emote": {"id": "25"}}]}}
    m = normalize_event(ev)
    assert m.color == "#FF4500" and m.emotes == [{"id": "25", "text": "Kappa"}] and m.badges == ["moderator"]


def test_twitch_moderation_needs_scope_and_calls_helix(monkeypatch):
    import asyncio
    from connectors import twitch as tw
    t = tw.Twitch(None, lambda e: None)
    t.user, t.broadcaster_id = {"login": "me", "user_id": "1"}, "2"
    with __import__("pytest").raises(RuntimeError):
        asyncio.run(t.moderate("timeout", user_id="9"))
    t.capabilities = dict(t.capabilities, mod_timeout=True, mod_delete=True)
    calls = []

    class R:
        status_code = 200
        text = ""
    monkeypatch.setattr(t, "tokens", lambda: {"access_token": "x", "client_id": "c"})
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: calls.append(("post", url, k)) or R())
    monkeypatch.setattr(tw.requests, "delete", lambda url, **k: calls.append(("delete", url, k)) or R())
    assert asyncio.run(t.moderate("timeout", user_id="9", seconds=300))
    assert asyncio.run(t.moderate("delete", message_id="mm"))
    assert calls[0][2]["json"]["data"] == {"user_id": "9", "reason": "Multi quick action", "duration": 300}
    assert calls[1][2]["params"]["message_id"] == "mm"


def test_dashboard_pins_feed_and_popout_routes(tmp_path, monkeypatch):
    import time
    from fastapi.testclient import TestClient
    import server
    from store import Store
    from models import ChatMessage
    import priority.rules as prio
    st = Store(tmp_path / "d.db")
    monkeypatch.setattr(server, "store", st)
    monkeypatch.setattr(server.pipeline, "store", st)
    now = time.time()
    for i, u in enumerate(["a", "a", "b", "pinguinob0t"]):
        st.add_message(ChatMessage(id=f"twitch:c:{i}", platform="twitch", channel="c", user_id=u, user=u, display=u, text="hi", ts=now - 5), prio.Decision(0, "none", []) if hasattr(prio, "Decision") else __import__("models").Decision(0, "none", []))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    d = c.get("/api/dashboard").json()
    assert d["messages_last_hour"] == 4 and d["top_chatters"][0] == {"user": "a", "platform": "twitch", "messages": 2}
    assert all(t["user"] != "pinguinob0t" for t in d["top_chatters"]) and len(d["series_15m"]) == 15
    h = {"origin": "http://127.0.0.1:8766"}
    assert c.post("/api/pins", json={"message_id": "twitch:c:0"}, headers=h).json()["pins"][0]["user"] == "a"
    assert c.post("/api/pins", json={"message_id": "twitch:c:0", "pin": False}, headers=h).json()["pins"] == []
    assert len(c.get("/api/feed?since=0").json()["messages"]) == 4
    assert c.get("/popout").status_code == 200
    assert c.post("/api/mod/ban", json={"message_id": "twitch:c:0"}, headers=h).status_code == 400   # no Twitch connector in this unit test


def test_vault_fallback_order(monkeypatch):
    import secrets_store, vault
    monkeypatch.setattr(secrets_store, "_local", lambda n: None)
    monkeypatch.setattr(vault, "fetch", lambda name: {"MULTI_DISCORD_TOKEN": "vault-token", "MULTI_TWITCH_TOKENS": '{"access_token": "a"}'}.get(name))
    vault.clear_cache()
    assert secrets_store.get("discord_token") == "vault-token" and secrets_store.source("discord_token") == "vault"
    assert secrets_store.get("twitch_tokens") == {"access_token": "a"}
    assert secrets_store.get("nothing") is None
    monkeypatch.setattr(secrets_store, "_local", lambda n: "local-token")
    assert secrets_store.get("discord_token") == "local-token" and secrets_store.source("discord_token") == "local"


def test_vault_fetch_needs_token_and_never_raises(monkeypatch):
    import vault
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    assert vault.fetch("MULTI_AI_KEY") is None
    monkeypatch.setenv("PINGUINO_API_TOKEN", "t")
    monkeypatch.setenv("PINGUINO_CORE_URL", "http://127.0.0.1:1")
    assert vault.fetch("MULTI_AI_KEY") is None


def test_pages_link_shared_theme(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    monkeypatch.setenv("PINGUINO_CORE_URL", "http://127.0.0.1:8760")
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    for path in ("/", "/popout"):
        assert '<link rel="stylesheet" href="http://127.0.0.1:8760/theme.css">' in c.get(path).text


def test_every_prestream_item_has_help_and_integrations():
    from fastapi.testclient import TestClient
    import server, help_text
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    items = c.get("/api/prestream").json()["items"]
    assert items and all(i["help"] and i["help"]["steps"] and i["help"]["title"] for i in items)
    for h in list(help_text.HELP.values()) + [s["help"] for s in help_text.SECRETS]:
        assert len(h["steps"]) <= 14
        if h.get("link"):
            assert h["link"]["url"].startswith("https://")
    assert {s["name"] for s in help_text.SECRETS} == {"MULTI_TWITCH_TOKENS", "MULTI_DISCORD_TOKEN", "MULTI_YOUTUBE_TOKEN", "MULTI_AI_KEY"}
    ints = c.get("/api/integrations").json()["items"]
    assert {i["id"] for i in ints} == {"twitch", "discord", "youtube", "tiktok"} and all(i["help"] for i in ints)
    assert c.post("/api/test/nope", headers={"origin": "http://127.0.0.1:8766"}).status_code == 404
    assert "_module" in c.get("/api/help/all").json()["items"]


# new-chatter ding ---------------------------------------------------
class _Player:
    def __init__(self):
        self.played = []

    def play(self, path, vol):
        self.played.append((path, vol))


def _ding(tmp_path, monkeypatch, **cfg):
    import config, ding
    from store import Store
    snd = tmp_path / "d.wav"
    snd.write_bytes(b"x")
    s = dict(config.DEFAULTS, ding_platforms=["twitch", "youtube"], ding_sound=str(snd), **cfg)
    monkeypatch.setattr(config, "settings", lambda: s)
    clk = Clock()
    pl = _Player()
    d = ding.Ding(Store(tmp_path / "g.db"), player=pl, clock=clk, master=lambda: True, start_worker=False)
    return d, pl, clk, s


def _m(user, platform="twitch", n=0, **kw):
    return ChatMessage(id=f"{platform}:c:{user}{n}", platform=platform, channel="c", user_id=user, user=user, display=user,
                       text="hi", ts=time.time(), **kw)


def test_ding_once_per_user_per_stream_and_per_platform(tmp_path, monkeypatch):
    d, pl, clk, s = _ding(tmp_path, monkeypatch)
    assert d.observe(_m("amy")) and not d.observe(_m("amy", n=1))
    assert d.observe(_m("amy", platform="youtube"))               # same name, other platform = another chatter
    assert not d.observe(_m("kim", platform="discord"))            # discord is not enabled
    assert not d.observe(_m("pinguinob0t")) and not d.observe(_m("me", is_self=True))
    while not d.q.empty():
        d.play_one(d.q.get())
    assert len(pl.played) == 2 and pl.played[0][1] == 24


def test_ding_session_resets_after_gap_and_survives_restart(tmp_path, monkeypatch):
    import ding
    d, pl, clk, s = _ding(tmp_path, monkeypatch)
    d.observe(_m("amy"))
    again = ding.Ding(d.store, player=pl, clock=clk, master=lambda: True, start_worker=False)   # Multi restarted mid-stream
    assert not again.observe(_m("amy", n=1))
    clk.t += 7 * 3600                                              # long quiet gap = a new stream
    assert again.observe(_m("amy", n=2))


def test_ding_first_ever_sound_burst_limit_master_and_missing_file(tmp_path, monkeypatch):
    d, pl, clk, s = _ding(tmp_path, monkeypatch, ding_first_ever=True)
    other = tmp_path / "first.wav"
    other.write_bytes(b"y")
    s["ding_first_sound"] = str(other)
    d.observe(_m("new1", first_time=True))
    for i in range(10):
        d.observe(_m(f"raid{i}"))
    assert d.q.qsize() == 5 and d.stats["dropped"] >= 5            # a raid cannot flood the queue
    kinds = []
    while not d.q.empty():
        kinds.append(d.q.get())
    assert kinds[0] == "first" and d.sound_for("first") == str(other) and d.sound_for("new") == s["ding_sound"]
    d.master = lambda: False
    d._master = (0, True)
    assert not d.observe(_m("auxuser"))                            # auxiliary device stays silent
    s["ding_sound"] = str(tmp_path / "nope.mp3")
    assert d.play_one("new") is False and d.stats["errors"] == 1


def test_ding_settings_endpoint_validates(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import config, server
    saved = {}
    monkeypatch.setattr(config, "save_settings", lambda p: saved.update(p) or p)
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    h = {"origin": "http://127.0.0.1:8766"}
    assert c.post("/api/ding/settings", json={"sound": str(tmp_path / "missing.mp3")}, headers=h).status_code == 400
    r = c.post("/api/ding/settings", json={"platforms": ["twitch", "kick", "youtube"], "volume": 500, "cooldown_s": 0}, headers=h)
    assert r.status_code == 200 and saved["ding_platforms"] == ["twitch", "youtube"] and saved["ding_volume"] == 100 and saved["ding_cooldown_s"] == 0.2


def test_ding_ever_scope_survives_quiet_gap_and_streamer_never_dings(tmp_path, monkeypatch):
    d, pl, clk, s = _ding(tmp_path, monkeypatch, ding_scope="ever")
    assert d.observe(_m("amy"))
    clk.t += 30 * 3600
    assert not d.observe(_m("amy", n=1))                         # forever, not just this stream
    assert not d.observe(_m("innocentpenguin"))                  # the streamer's own name
    import config
    assert config.DEFAULTS["ding_volume"] == 24 and config.DEFAULTS["ding_sound"].endswith("new-chatter-bell.wav")


def test_ding_returning_sound_volumes_and_recent_list(tmp_path, monkeypatch):
    d, pl, clk, s = _ding(tmp_path, monkeypatch, ding_returning=True, ding_returning_volume=50, ding_master_volume=50, ding_volume=80)
    ret = tmp_path / "ret.wav"
    ret.write_bytes(b"r")
    s["ding_returning_sound"] = str(ret)
    assert d.observe(_m("amy")) == "new"
    d.new_stream("test")                                          # next stream: amy is now known
    assert d.observe(_m("amy", n=1)) == "returning" and d.observe(_m("zed")) == "new"
    assert d.sound_for("returning") == str(ret) and d.sound_for("new") == s["ding_sound"]
    assert d.volume_for("new") == 40 and d.volume_for("returning") == 25      # kind volume * master / 100
    assert [x["kind"] for x in d.recent] == ["new", "returning", "new"]
    s["ding_returning"] = False
    d.new_stream("again")
    assert d.observe(_m("amy", n=2)) == "new"                    # without the toggle, 'per stream' just dings normally
    s["ding_scope"] = "ever"
    d.new_stream("ever")
    assert d.observe(_m("amy", n=3)) is False                    # 'ever' + no returning toggle: known people stay quiet


def test_pop_per_platform_volume_master_rate_limit_and_bots(tmp_path, monkeypatch):
    import config, pop
    snd = tmp_path / "pop.mp3"
    snd.write_bytes(b"p")
    s = dict(config.DEFAULTS, pop_platforms=["twitch", "youtube"], pop_sound=str(snd), ding_master_volume=50)
    monkeypatch.setattr(config, "settings", lambda: s)
    pl = _Player()
    p = pop.Pop(player=pl, master=lambda: True, start_worker=False)
    assert p.observe(_m("amy")) and p.observe(_m("yy", platform="youtube"))
    assert not p.observe(_m("kim", platform="discord"))                       # discord not enabled
    assert not p.observe(_m("nightbot")) and not p.observe(_m("amy", is_bot=True))
    assert not p.observe(_m("me", is_self=True)) and not p.observe(_m("innocentpenguin"))   # own messages off by default
    s["pop_own"] = True
    assert p.observe(_m("innocentpenguin"))
    assert not p.observe(_m("x1")) and p.stats["dropped"] == 1                 # queue of 3: a burst cannot pile up
    assert p.volume_for("twitch") == 25 and p.volume_for("youtube") == 38      # 50/76 percent times master 50 percent
    while not p.q.empty():
        p.play_one(p.q.get())
    assert len(pl.played) == 3 and pl.played[1][1] == 38
    p.master = lambda: False
    p._master = (0, True)
    assert not p.observe(_m("auxuser"))
    assert config.DEFAULTS["pop_volume"] == {"twitch": 50, "youtube": 76, "discord": 50}
    assert config.DEFAULTS["ding_returning_volume"] == 50 and config.DEFAULTS["ding_returning"] is True


# chat look ----------------------------------------------------------
def test_chatstyle_sanitize_defaults_and_hostile_input():
    import chatstyle
    d = chatstyle.sanitize(None)
    assert set(d["platform"]) == set(chatstyle.PLATFORMS) and set(d["role"]) == set(chatstyle.ROLES) and set(d["event"]) == set(chatstyle.EVENTS)
    bad = chatstyle.sanitize({"base": {"size": 9999, "family": "Evil; } body{display:none", "bg": "red; x", "weight": 450},
                              "event": {"raid": {"bg": "#12ab34", "bgA": 500, "borderW": -3, "junk": "x", "size": "abc"}, "evil": {}},
                              "keywords": [{"word": " giveaway ", "rule": {"bg": "url(x)"}}, {"word": ""}, "nope"]})
    assert bad["base"]["size"] == 48 and bad["base"]["family"] == "system-ui" and bad["base"]["weight"] == 400
    assert bad["base"]["bg"] == "#09090a"                                             # invalid colour falls back
    r = bad["event"]["raid"]
    assert r["bg"] == "#12ab34" and r["bgA"] == 100 and r["borderW"] == 0 and r["size"] == 100 and "junk" not in r and "evil" not in bad["event"]
    assert [k["word"] for k in bad["keywords"]] == ["giveaway"] and bad["keywords"][0]["rule"]["bg"] == "#ff9900"


def test_chatstyle_api_roundtrip_and_reset(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import config, server
    saved = {}
    monkeypatch.setattr(config, "save_settings", lambda p: saved.update(p) or p)
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    h = {"origin": "http://127.0.0.1:8766"}
    r = c.post("/api/chatstyle", json={"style": {"event": {"sub": {"bg": "#112233"}}}}, headers=h).json()["style"]
    assert r["event"]["sub"]["bg"] == "#112233" and saved["chat_style"]["event"]["sub"]["bg"] == "#112233"
    assert c.post("/api/chatstyle/reset", json={}, headers=h).json()["style"]["event"]["sub"]["bg"] == "#ffc94d" and saved["chat_style"]["event"]["sub"]["bg"] == "#ffc94d"
    assert "defaults" in c.get("/api/chatstyle").json()


def test_twitch_notices_cheers_and_events_endpoint(tmp_path, monkeypatch):
    from connectors.twitch import normalize_notice, normalize_event
    n = normalize_notice({"broadcaster_user_login": "ch", "message_id": "n1", "notice_type": "raid", "chatter_user_login": "raider",
                          "chatter_user_name": "Raider", "system_message": "Raider is raiding with 120 viewers", "raid": {"viewer_count": 120}})
    assert n.event == "raid" and n.amount == 120 and n.text.startswith("Raider is raiding")
    g = normalize_notice({"broadcaster_user_login": "ch", "message_id": "n2", "notice_type": "community_sub_gift", "chatter_user_login": "g",
                          "community_sub_gift": {"total": 5}, "system_message": "g gifted 5"})
    assert g.event == "gift" and g.amount == 5
    c = normalize_event({"broadcaster_user_login": "ch", "message_id": "m", "chatter_user_id": "1", "chatter_user_login": "u",
                         "message": {"text": "cheer100 hi"}, "cheer": {"bits": 100}})
    assert c.event == "cheer" and c.amount == 100
    from fastapi.testclient import TestClient
    import server
    from store import Store
    st = Store(tmp_path / "e.db")
    monkeypatch.setattr(server, "store", st)
    monkeypatch.setattr(server.pipeline, "store", st)
    for fn in (n, g):
        out = server.pipeline.ingest(fn)
        assert out["tier"] == "none" and out["event"] == fn.event           # events are shown, never ranked
    assert not any(c["message_id"] in (n.id, g.id) for c in server.cards.cards.values())


def test_new_and_returning_flags_from_history(tmp_path, monkeypatch):
    import config, server
    from store import Store
    st = Store(tmp_path / "f.db")
    monkeypatch.setattr(server, "store", st)
    monkeypatch.setattr(server.pipeline, "store", st)
    now = time.time()
    first = server.pipeline.ingest(ChatMessage(id="twitch:c:f1", platform="twitch", channel="c", user_id="u1", user="u1", display="u1", text="hello there", ts=now - 20 * 3600))
    assert first["flags"] == ["new"]
    again = server.pipeline.ingest(ChatMessage(id="twitch:c:f2", platform="twitch", channel="c", user_id="u1", user="u1", display="u1", text="hello again", ts=now))
    assert again["flags"] == ["returning"]                                # >6 h since the last message = back after a break
    soon = server.pipeline.ingest(ChatMessage(id="twitch:c:f3", platform="twitch", channel="c", user_id="u1", user="u1", display="u1", text="still here", ts=now + 5))
    assert soon["flags"] == []


def test_platform_marker_setting_and_logo_validation():
    import chatstyle
    d = chatstyle.sanitize(None)
    assert d["base"]["marker"] == "text" and d["marker"]["twitch"] == {"size": 14, "color": ""}      # default stays words
    s = chatstyle.sanitize({"base": {"marker": "both"}, "marker": {"youtube": {"size": 999, "color": "#ff0000"}, "tiktok": {"size": 2, "color": "javascript:1"}, "evil": {}}})
    assert s["base"]["marker"] == "both" and s["marker"]["youtube"] == {"size": 40, "color": "#ff0000"}
    assert s["marker"]["tiktok"] == {"size": 10, "color": ""} and set(s["marker"]) == set(chatstyle.PLATFORMS)
    assert chatstyle.sanitize({"base": {"marker": "huge"}})["base"]["marker"] == "text"


# assisted chat --------------------------------------------------------
def _assist(tmp_path, monkeypatch, reply=None, key="k"):
    import config, ai, assist, secrets_store
    from store import Store
    st = Store(tmp_path / "a.db")
    adv = ai.Advisor(st)
    calls = []

    def fake(prov, model, k, prompt, timeout, max_tokens=30):
        calls.append(prompt)
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(secrets_store, "get", lambda n, d=None: key if n == "ai_key" else d)
    return assist.Assist(st, adv, call=fake), adv, calls


def test_assist_suggest_ai_cache_cap_and_cleaning(tmp_path, monkeypatch):
    import asyncio
    a, adv, calls = _assist(tmp_path, monkeypatch, reply='{"replies": ["Hey! check https://evil.example now @bob", "ok", "  love it  "]}')
    m = {"text": "what game is this?", "platform": "twitch", "display": "Al", "user": "al"}
    r = asyncio.run(a.suggest(m, [{"text": "hi"}]))
    assert r["source"] == "ai" and r["replies"][0] == "Hey! check now" and "http" not in " ".join(r["replies"]) and len(r["replies"]) == 3
    assert asyncio.run(a.suggest(m, []))["cached"] and len(calls) == 1               # second ask is free
    assert adv.spend()["usd"] > 0 and "DATA" in calls[0]
    monkeypatch.setattr("config.settings", lambda: dict(config_defaults(), ai_daily_cap_usd=0.0))
    r2 = asyncio.run(a.suggest(dict(m, text="another one?"), []))
    assert r2["source"] == "templates" and "cap" in r2["why"]                          # capped -> templates, no call


def config_defaults():
    import config
    return dict(config.DEFAULTS)


def test_assist_fallbacks_templates_translate_and_foreign_hint(tmp_path, monkeypatch):
    import asyncio, assist
    a, adv, calls = _assist(tmp_path, monkeypatch, reply=RuntimeError("boom"), key=None)
    r = asyncio.run(a.suggest({"text": "hello?", "platform": "twitch", "display": "Zed", "user": "zed"}, []))
    assert r["source"] == "templates" and r["replies"][0] == "Thanks Zed!" and not calls            # no key: nothing was sent
    assert asyncio.run(a.translate({"text": "hola amigos"}))["source"] == "none"
    assert a.set_templates(["a {name}", "", "b"]) == ["a {name}", "b"] and a.templates() == ["a {name}", "b"]
    assert assist.looks_foreign("こんにちは みなさん") and not assist.looks_foreign("hello there") and not assist.looks_foreign("lol")
    a2, _, c2 = _assist(tmp_path, monkeypatch, reply="Hello friends")
    assert asyncio.run(a2.translate({"text": "hola amigos"})) == {"source": "ai", "text": "Hello friends"}


def test_chatter_card_manual_mark_and_assist_routes(tmp_path, monkeypatch):
    import config, server
    from fastapi.testclient import TestClient
    from store import Store
    st = Store(tmp_path / "c.db")
    monkeypatch.setattr(server, "store", st)
    monkeypatch.setattr(server.pipeline, "store", st)
    monkeypatch.setattr(server.pipeline.assist, "store", st)
    monkeypatch.setattr(server.cards, "store", st)
    now = time.time()
    server.pipeline.ingest(ChatMessage(id="twitch:c:x1", platform="twitch", channel="c", user_id="u9", user="zed", display="Zed", text="nice", ts=now - 3600, badges=["subscriber"]))
    out = server.pipeline.ingest(ChatMessage(id="twitch:c:x2", platform="twitch", channel="c", user_id="u9", user="zed", display="Zed", text="lol ok", ts=now))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    h = {"origin": "http://127.0.0.1:8766"}
    ch = c.get("/api/chatter/twitch/u9").json()
    assert ch["messages"] == 2 and ch["badges"] == ["subscriber"] and ch["first_seen"] < ch["last_seen"] and not ch["muted"]
    assert c.get("/api/chatter/twitch/nobody").status_code == 404
    card = c.post("/api/cards/manual", json={"message_id": "twitch:c:x2"}, headers=h).json()
    assert card["state"] == "open" and card["reasons"][0]["rule"] == "marked" and card["id"] in server.cards.cards
    assert c.post("/api/cards/manual", json={"message_id": "twitch:c:none"}, headers=h).status_code == 404
    assert c.post("/api/templates", json={"templates": ["x {name}"]}, headers=h).json() == {"templates": ["x {name}"]}
    s = c.post("/api/assist/suggest", json={"message_id": "twitch:c:x2"}, headers=h).json()
    assert s["source"] == "templates" and s["replies"] == ["x Zed"]                                  # no AI key in tests


def test_presets_are_valid_and_look_overrides_are_clean():
    import chatstyle, presets
    for name in presets.PRESETS:
        st = presets.preset_style(name)
        assert st["base"]["marker"] in ("text", "logo", "both", "none") and 0 <= st["base"]["intensity"] <= 250
    assert presets.preset_style("Nope") is None
    assert chatstyle.sanitize_look({"size": 99, "bg": "#112233", "evil": 1, "anim": "explode", "family": "x;y"}) == {"size": 48, "bg": "#112233", "anim": "none", "family": "system-ui"}
    assert chatstyle.sanitize_look("junk") == {}


def test_panes_filters_and_split_modes():
    import panes
    a = panes.build_split("platform", ["twitch", "bogus"])
    assert a["split-a"]["filter"]["platforms"] == ["twitch"] and "twitch" not in a["split-b"]["filter"]["platforms"]
    f = panes.build_split("flow")
    assert f["split-a"]["flow"]["order"] == 1 and f["split-b"]["flow"]["order"] == 0 and f["split-b"]["flow"]["group"] == "chat-split"
    assert panes.build_split("events")["split-b"]["filter"]["kind"] == "events"
    p = panes.build_split("people")
    assert p["split-b"]["filter"]["invert_roles"] is True
    try:
        panes.build_split("zzz"); assert False
    except ValueError:
        pass
    s = panes.sanitize({"filter": {"platforms": ["twitch", "x"], "kind": "weird", "roles": ["mod", "god"]}, "look": {"size": 20, "x": 1}, "geom": {"x": "a"}})
    assert s["filter"] == {"platforms": ["twitch"], "kind": "all", "roles": ["mod"], "invert_roles": False} and s["look"] == {"size": 20} and s["geom"] is None


def test_look_presets_undo_import_and_panes_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import config, server
    state = {}
    monkeypatch.setattr(config, "save_settings", lambda p: state.update(p) or p)
    monkeypatch.setattr(config, "settings", lambda: dict(config.DEFAULTS, **state))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    h = {"origin": "http://127.0.0.1:8766"}
    lst = c.get("/api/chatstyle/presets").json()
    assert {"Pinguino", "Neon", "Compact"} <= {p["name"] for p in lst["builtin"]}
    assert c.post("/api/chatstyle/apply", json={"name": "Neon"}, headers=h).json()["style"]["base"]["bg"] == "#0b0014"
    assert c.post("/api/chatstyle/apply", json={"name": "nope"}, headers=h).status_code == 404
    assert c.post("/api/chatstyle/undo", json={}, headers=h).json()["style"]["base"]["bg"] == "#09090a"
    assert c.post("/api/chatstyle/save-preset", json={"name": ""}, headers=h).status_code == 400
    assert c.post("/api/chatstyle/save-preset", json={"name": "Mine"}, headers=h).json()["count"] >= 1
    assert "Mine" in [p["name"] for p in c.get("/api/chatstyle/presets").json()["mine"]]
    assert c.post("/api/chatstyle/import", json={"junk": 1}, headers=h).status_code == 400
    assert c.post("/api/chatstyle/import", json=c.get("/api/chatstyle/export").json(), headers=h).status_code == 200
    r = c.post("/api/splits/apply", json={"mode": "events"}, headers=h).json()
    assert r["panes"]["split-b"]["filter"]["kind"] == "events"
    assert c.post("/api/panes/split-b", json={"look": {"size": 22, "bg": "bad"}}, headers=h).json()["look"] == {"size": 22, "bg": "#09090a"}
    assert c.get("/api/panes/split-b").json()["look"]["size"] == 22
    assert c.post("/api/splits/apply", json={"mode": "zzz"}, headers=h).status_code == 400
    assert c.post("/api/geom/pane-split-a", json={"x": 1, "y": 2, "w": 300, "h": 200}, headers=h).status_code == 200
    assert c.post("/api/geom/pane-split-a", json={"x": "q"}, headers=h).status_code == 400
    assert c.get("/api/panes").json()["geom"]["pane-split-a"]["w"] == 300
    assert c.delete("/api/panes/split-b", headers=h).status_code == 200 and c.get("/api/panes/split-b").status_code == 404


def test_pop_roles_filter_and_sounds_reset(tmp_path, monkeypatch):
    import config, pop
    from models import ChatMessage
    state = dict(config.DEFAULTS, pop_platforms=["twitch"], pop_roles=["mod"], my_names=[], bot_accounts=[])
    monkeypatch.setattr(config, "settings", lambda: state)
    pp = pop.Pop(player=object(), master=lambda: True, start_worker=False)
    def msg(badges):
        return ChatMessage(id="x" + str(badges), platform="twitch", channel="c", user="u", user_id="1", display="U", text="hi", ts=1.0, badges=badges)
    assert pp.observe(msg(["moderator"])) is True
    assert pp.observe(msg([])) is False
    state["pop_roles"] = []
    assert pp.observe(msg([])) is True
    assert pop.role_of(msg(["broadcaster"])) == "mod" and pop.role_of(msg(["subscriber"])) == "sub"


def test_host_feed_maps_activity_items():
    import host_feed
    m = host_feed.to_message({"seq": 7, "ts": 100, "type": "redeem", "user": "Pat", "amount": 500, "detail": "Hydrate", "message": "cheers"}, "chan")
    assert m.id == "host:7" and m.event == "redeem" and m.amount == 500 and m.text == "Pat redeemed Hydrate: cheers"
    assert host_feed.to_message({"seq": 8, "type": "follow", "user": "Fin"}, "chan").text == "Fin followed"
    assert host_feed.to_message({"seq": 9, "type": "clip", "user": "x"}, "chan") is None


# ---- OBS widgets (Synchra compatible) ----------------------------------------------------
def test_obs_import_ivans_synchra_export():
    import json, pathlib
    import obs
    doc = json.loads(pathlib.Path(r"D:\PinguinoSuite\Docs\imports\synchra-chat-widget.json").read_text("utf-8"))
    st, err = obs.from_synchra(doc)
    assert not err and st["size"] == "xxl" and st["font_family_id"] == "nunito" and "synchrabot" in st["ignore_names"]
    assert "Unkempt" in st["custom_css"] and st["message_order"] == "bottom" and st["entrance_animation_type"] == "fade"
    back = obs.to_synchra("chat", st)
    assert back["kind"] == "synchra.widget" and back["settings"]["ignore_names"] == st["ignore_names"] and "max_messages" not in back["settings"]


def test_obs_sanitize_clamps_and_hidden():
    import obs
    st = obs.sanitize("chat", {"size": "huge", "canvas_scale": 99, "text_color": "red", "custom_css": "a{}</style><script>", "ignore_names": ["Bot", "bot", " "],
                               "providers": ["twitch", "nope"]})
    assert st["size"] == obs.CHAT_DEFAULT["size"] and st["canvas_scale"] == 4 and st["text_color"] == "#ffffff"
    assert "</style" not in st["custom_css"] and st["ignore_names"] == ["Bot"] and st["providers"] == ["twitch"]
    m = {"user": "bot", "display": "Bot", "platform": "twitch", "event": ""}
    assert obs.hidden("chat", st, m)
    assert obs.hidden("chat", st, {"user": "x", "platform": "youtube", "event": ""})
    assert not obs.hidden("chat", st, {"user": "x", "platform": "twitch", "event": "raid"})
    st2 = obs.sanitize("chat", {"notices": False})
    assert obs.hidden("chat", st2, {"user": "x", "platform": "twitch", "event": "raid"})
    act = obs.sanitize("activity", {"types": ["follow"]})
    assert not obs.hidden("activity", act, {"user": "x", "platform": "twitch", "event": "follow"}) and obs.hidden("activity", act, {"user": "x", "platform": "twitch", "event": "raid"})


def test_host_feed_moderation_notices():
    import host_feed
    m = host_feed.to_message({"seq": 5, "type": "ban", "user": "Troll", "detail": "timed out", "message": "spam", "ts": 1}, "chan")
    assert m.event == "timeout" and m.text == "Troll was timed out (spam)" and m.display == "Troll"
    m = host_feed.to_message({"seq": 6, "type": "ban", "user": "Troll", "detail": "banned", "moderator": "InnocentPenguin_"}, "chan")
    assert m.event == "ban" and m.text == "InnocentPenguin_ banned Troll" and m.display == "InnocentPenguin_"
    assert host_feed.to_message({"seq": 7, "type": "unmod", "user": "PotatBotat", "moderator": "InnocentPenguin_"}, "c").text == "InnocentPenguin_ unmodded PotatBotat"
    assert "ban" in host_feed.ALWAYS and "shoutout" in host_feed.ALWAYS


def test_follow_widget_and_refollow_flag():
    import obs, host_feed
    st = obs.sanitize("follow", {"duration_seconds": 999, "image_url": "javascript:alert(1)", "sound_url": "/sounds/a.mp3", "entrance_animation_type": "bounce", "follow_text": ""})
    assert st["duration_seconds"] == 60 and st["image_url"] == "" and st["sound_url"] == "/sounds/a.mp3" and st["entrance_animation_type"] == "bounce" and "{user}" in st["follow_text"]
    assert not obs.hidden("follow", st, {"user": "x", "platform": "twitch", "event": "follow", "flags": []})
    assert obs.hidden("follow", st, {"user": "x", "platform": "twitch", "event": "raid"})
    st2 = obs.sanitize("follow", {"show_refollow": False})
    assert obs.hidden("follow", st2, {"user": "x", "platform": "twitch", "event": "follow", "flags": ["refollow"]})
    assert host_feed.to_message({"seq": 1, "type": "follow", "user": "A", "refollow": True}, "c").flags == ["refollow"]
    assert host_feed.to_message({"seq": 2, "type": "follow", "user": "A"}, "c").flags == []


def test_dash_layout_keeps_text_size_and_split():
    import server
    lay = server._dash_layout({"panels": ["chat"], "fs": {"chat": 99}, "split": {"on": True, "dir": "col", "kind": "flow", "a": "nope"}})
    assert lay["fs"]["chat"] == 40 and lay["fs"]["activity"] == 14
    assert lay["split"] == {"on": True, "dir": "col", "a": "all", "b": "all", "kind": "flow"}


def test_host_feed_plan5_events():
    import host_feed
    m = host_feed.to_message({"seq": 1, "type": "raid_out", "user": "tgt", "target": "tgt", "amount": 12}, "me")
    assert m.event == "raid_out" and "12 viewers" in m.text
    m = host_feed.to_message({"seq": 2, "type": "poll", "state": "end", "what": "Game?", "data": {"choices": [{"title": "A", "votes": "3"}, {"title": "B", "votes": "9"}]}}, "me")
    assert "Poll ended" in m.text and "top: B" in m.text
    m = host_feed.to_message({"seq": 3, "type": "prediction", "state": "end", "what": "Win?", "data": {"winningOutcomeId": "x", "outcomes": [{"id": "x", "title": "Yes"}]}}, "me")
    assert "winner: Yes" in m.text
    m = host_feed.to_message({"seq": 4, "type": "hype", "state": "begin", "what": "level 1", "data": {}}, "me")
    assert m.event == "hype" and "started" in m.text


def test_follow_widget_gift_alerts():
    import obs
    s = obs.sanitize("follow", {})
    assert s["show_gifts"] and "{amount}" in s["gift_text"]
    assert obs.hidden("follow", s, {"event": "gift"}) is False
    s2 = obs.sanitize("follow", {"show_gifts": False})
    assert obs.hidden("follow", s2, {"event": "gift"}) is True
    assert obs.hidden("follow", s, {"event": "raid"}) is True


def test_send_drops_duplicates_and_allows_retry_after_failure(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server
    from store import Store
    monkeypatch.setattr(server, "store", Store(tmp_path / "s.db"))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    server._RECENT_SENDS.clear()
    calls = []

    class Fake:
        capabilities = {"send": True, "reply": False}
        user = None
        fail = True

        async def send(self, text, reply_to=None):
            calls.append(text)
            if Fake.fail:
                raise RuntimeError("nope")
            return "discord:x:1"
    monkeypatch.setitem(server.connectors, "discord", Fake())
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    h = {"origin": "http://127.0.0.1:8766"}
    assert c.post("/api/send", json={"platform": "discord", "text": "hi"}, headers=h).status_code == 502
    Fake.fail = False
    assert c.post("/api/send", json={"platform": "discord", "text": "hi"}, headers=h).json()["ok"] is True      # retry after a failure is allowed
    r = c.post("/api/send", json={"platform": "discord", "text": "  HI "}, headers=h).json()
    assert r["duplicate"] is True and len(calls) == 2                                                          # identical line within 30 s is not sent again


def test_live_overlay_routes_and_state(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server, host_feed

    async def fake():
        return {"poll": {"title": "x", "state": "progress", "choices": []}, "prediction": None}
    monkeypatch.setattr(host_feed, "live_state", fake)
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    for k in ("poll", "predict", "hype"):
        r = c.get("/obs/" + k)
        assert r.status_code == 200 and "api/live-state" in r.text and "no-store" in r.headers["cache-control"]
    j = c.get("/api/live-state").json()
    assert j["poll"]["title"] == "x" and j["prediction"] is None and j["hype"] is None
