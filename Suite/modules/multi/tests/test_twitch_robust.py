"""Twitch connector failure handling (worker 42): refresh on 401, 429 Retry-After, revocation, replayed frames, timestamps, card status per failure."""
import asyncio
import time
from types import SimpleNamespace as NS

import pytest

from connectors import twitch as tw


def R(code=200, headers=None, js=None, text=""):
    return NS(status_code=code, headers=headers or {}, text=text, json=lambda: js if js is not None else {})


def make(monkeypatch):
    t = tw.Twitch(None, lambda e: None)
    t.user, t.broadcaster_id = {"login": "me", "user_id": "1"}, "2"
    t.capabilities = dict(t.capabilities, send=True, mod_timeout=True)
    tok = {"access_token": "old", "client_id": "c", "refresh_token": "r"}
    monkeypatch.setattr(t, "tokens", lambda: tok)
    return t, tok


# ---- 401 mid-session -> refresh once -> retry ----------------------------------------------------------
def test_send_refreshes_token_on_401_and_retries(monkeypatch):
    t, tok = make(monkeypatch)
    seen = []

    def post(url, **k):
        seen.append(k["headers"]["Authorization"])
        return R(401) if k["headers"]["Authorization"].endswith("old") else R(200, js={"data": [{"is_sent": True, "message_id": "m1"}]})
    monkeypatch.setattr(tw.requests, "post", post)
    monkeypatch.setattr(t, "refresh", lambda tk: dict(tk, access_token="new"))
    assert asyncio.run(t.send("hi")).endswith(":m1")
    assert seen == ["Bearer old", "Bearer new"]


def test_send_with_dead_refresh_sets_needs_auth(monkeypatch):
    t, tok = make(monkeypatch)
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: R(401))
    monkeypatch.setattr(t, "refresh", lambda tk: None)
    with pytest.raises(tw.TwitchAuthError):
        asyncio.run(t.send("hi"))
    assert t.state["status"] == "needs_auth" and "reconnect Twitch" in t.state["detail"]


def test_second_401_after_refresh_is_auth_error_not_loop(monkeypatch):
    t, tok = make(monkeypatch)
    calls = []
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: calls.append(1) or R(401))
    monkeypatch.setattr(t, "refresh", lambda tk: dict(tk, access_token="new"))
    with pytest.raises(tw.TwitchAuthError):
        t._send_sync("x", None)
    assert len(calls) == 2


def test_refresh_site_failures(monkeypatch):
    t, tok = make(monkeypatch)
    monkeypatch.setattr(tw.secrets_store, "get", lambda k, *a: None)
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: R(401))
    assert t.refresh(dict(tok)) is None                           # refresh token rejected -> needs_auth
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: R(503))
    with pytest.raises(RuntimeError, match="503"):                # site deploying -> transient, retried (card: reconnecting)
        t.refresh(dict(tok))


def test_validate_only_401_means_invalid(monkeypatch):
    t, tok = make(monkeypatch)
    monkeypatch.setattr(tw.requests, "get", lambda url, **k: R(401))
    assert t.validate(dict(tok)) is None
    monkeypatch.setattr(tw.requests, "get", lambda url, **k: R(502))
    with pytest.raises(RuntimeError):
        t.validate(dict(tok))                                     # must not trigger a refresh (would burn the refresh token)


# ---- 429 ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("h,want", [({"Retry-After": "7"}, 7), ({"Retry-After": "0"}, 1), ({"Retry-After": "99999"}, 300),
                                    ({"Retry-After": "junk"}, 30), ({}, 30), ({"Retry-After": "nan"}, 30)])
def test_retry_after(h, want):
    assert tw.retry_after(R(429, h)) == want


def test_ratelimit_reset_epoch():
    assert tw.retry_after(R(429, {"Ratelimit-Reset": "1060"}), now=1000) == 60


def test_429_on_send_raises_busy_with_wait(monkeypatch):
    t, tok = make(monkeypatch)
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: R(429, {"Retry-After": "12"}))
    with pytest.raises(tw.TwitchBusy) as e:
        asyncio.run(t.send("hi"))
    assert e.value.wait == 12 and "12 s" in str(e.value)


def test_run_loop_statuses_for_each_failure(monkeypatch):
    """What the card shows: auth problems -> needs_auth, 429 -> reconnecting with the wait, anything else -> reconnecting + readable detail."""
    t, tok = make(monkeypatch)
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= 4:
            t.stop = True
    monkeypatch.setattr(tw.asyncio, "sleep", fake_sleep)
    errs = iter([tw.TwitchAuthError("token expired; reconnect Twitch"), tw.TwitchBusy(12), RuntimeError(""), RuntimeError("boom")])

    async def ensure():
        return tok

    async def session(tk):
        raise next(errs)
    monkeypatch.setattr(t, "ensure_auth", ensure)
    monkeypatch.setattr(t, "_session", session)
    monkeypatch.setattr(tw.config, "settings", lambda: {"channel": "ch"})
    t.broadcaster_id = "2"
    statuses = []
    orig = t.set_status
    monkeypatch.setattr(t, "set_status", lambda s, d="": (statuses.append((s, d)), orig(s, d)))
    asyncio.run(t.run())
    assert ("needs_auth", "token expired; reconnect Twitch") in statuses
    assert ("reconnecting", "Twitch rate limit: try again in 12 s") in statuses
    assert ("reconnecting", "RuntimeError") in statuses and ("reconnecting", "boom") in statuses
    assert sleeps[:2] == [30, 12]


# ---- subscribe failures ------------------------------------------------------------------------------------
def test_subscribe_errors(monkeypatch):
    t, tok = make(monkeypatch)
    t.session_id = "s"
    for code, exc in ((403, tw.TwitchAuthError), (400, tw.TwitchAuthError), (500, RuntimeError)):
        monkeypatch.setattr(tw.requests, "post", lambda url, code=code, **k: R(code, text="x"))
        with pytest.raises(exc):
            t._subscribe(tok)
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: R(429, {"Retry-After": "5"}))
    with pytest.raises(tw.TwitchBusy):
        t._subscribe(tok)
    posted = []
    monkeypatch.setattr(tw.requests, "post", lambda url, **k: posted.append(k["json"]["type"]) or (R(202) if len(posted) == 1 else R(403)))
    t._subscribe(tok)                                             # stream-event feed refused: chat still works
    assert posted == ["channel.chat.message", "channel.chat.notification"]


# ---- revocation --------------------------------------------------------------------------------------------
def rev(typ, status="authorization_revoked", fid="r1"):
    return {"metadata": {"message_type": "revocation", "message_id": fid}, "payload": {"subscription": {"type": typ, "status": status}}}


def test_chat_revocation_ends_session_but_notice_revocation_does_not(monkeypatch):
    t, tok = make(monkeypatch)
    with pytest.raises(tw.TwitchAuthError, match="authorization_revoked"):
        asyncio.run(t.handle_frame(rev("channel.chat.message"), tok))
    assert asyncio.run(t.handle_frame(rev("channel.chat.notification", fid="r2"), tok)) is None


# ---- replays, timestamps -----------------------------------------------------------------------------------
class Inbox(list):
    put = list.append


def ev(mid="m1"):
    return {"broadcaster_user_login": "ch", "message_id": mid, "chatter_user_id": "9", "chatter_user_login": "bob",
            "message": {"text": "hello", "fragments": []}}


def note(fid, mid="m1", stamp=None):
    return {"metadata": {"message_type": "notification", "subscription_type": "channel.chat.message", "message_id": fid, "message_timestamp": stamp},
            "payload": {"event": ev(mid)}}


def test_redelivered_frame_is_processed_once(monkeypatch):
    t, tok = make(monkeypatch)
    t.inbox = Inbox()
    for _ in range(3):
        asyncio.run(t.handle_frame(note("F1"), tok))
    asyncio.run(t.handle_frame(note("F2", mid="m2"), tok))
    assert [m.id for m in t.inbox] == ["twitch:ch:m1", "twitch:ch:m2"]


def test_frame_memory_is_bounded(monkeypatch):
    t, tok = make(monkeypatch)
    t.inbox = Inbox()
    for i in range(700):
        asyncio.run(t.handle_frame(note(f"F{i}", mid=f"m{i}"), tok))
    assert len(t._frames) == 500 and len(t.inbox) == 700


def test_event_ts_skew_and_junk():
    now = 1_800_000_000.0
    past = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - 30))
    assert tw.event_ts(f"{past}.123456789Z", now) == pytest.approx(now - 30, abs=1)      # nanoseconds accepted
    future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 600))
    assert tw.event_ts(future, now) == now                                                # local clock behind Twitch: never in the future
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3 * 86400))
    assert tw.event_ts(old, now) == now
    for junk in (None, "", "garbage", 12, "2026-13-45T99:00:00Z", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59.999999999Z"):
        assert tw.event_ts(junk, now) <= now


def test_normalized_message_uses_event_timestamp(monkeypatch):
    t, tok = make(monkeypatch)
    t.inbox = Inbox()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z", time.gmtime(time.time() - 45))
    asyncio.run(t.handle_frame(note("F9", stamp=stamp), tok))
    assert 40 < time.time() - t.inbox[0].ts < 50


# ---- hourly token check ------------------------------------------------------------------------------------
def test_keep_token_renews_or_ends_session(monkeypatch):
    t, tok = make(monkeypatch)
    state = {"valid": False}
    monkeypatch.setattr(t, "validate", lambda tk: {"login": "me"} if tk.get("access_token") == "new" else None)
    monkeypatch.setattr(t, "refresh", lambda tk: dict(tk, access_token="new") if state["valid"] else None)
    with pytest.raises(tw.TwitchAuthError):
        asyncio.run(t._keep_token(tok))
    state["valid"] = True
    asyncio.run(t._keep_token(tok))                               # renewed: no exception
    monkeypatch.setattr(t, "validate", lambda tk: (_ for _ in ()).throw(ConnectionError("net down")))
    asyncio.run(t._keep_token(tok))                               # blip: ignored, chat stays up
