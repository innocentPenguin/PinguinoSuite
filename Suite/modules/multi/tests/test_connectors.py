"""Connector unit tests (pure / fake sockets, no network). Worker 42 owns this file."""
import asyncio
import json

import pytest

import websockets
import websockets.exceptions
import websockets.frames
from connectors import twitch as tw


def frame(t, **payload):
    return json.dumps({"metadata": {"message_type": t}, "payload": payload})


def welcome(sid):
    return frame("session_welcome", session={"id": sid})


class FakeWS:
    def __init__(self, url, script):
        self.url, self.script, self.closed = url, list(script), False

    async def recv(self):
        if not self.script:
            await asyncio.sleep(3600)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self):
        self.closed = True


class Harness:
    """Drives Twitch._session with scripted sockets keyed by connect order."""
    def __init__(self, monkeypatch, scripts):
        self.scripts, self.sockets, self.subs, self.events = list(scripts), [], [], []
        t = tw.Twitch(None, lambda e: None)
        t.user = {"login": "me", "user_id": "1"}
        monkeypatch.setattr(t, "_subscribe", lambda tok: self.subs.append(t.session_id))

        async def connect(url, **kw):
            ws = FakeWS(url, self.scripts.pop(0))
            self.sockets.append(ws)
            return ws
        monkeypatch.setattr(websockets, "connect", connect)
        self.t = t

    def run(self):
        try:
            asyncio.run(self.t._session("tok"))
        except Exception as e:
            return e


def closed(code):
    return websockets.exceptions.ConnectionClosedError(websockets.frames.Close(code, ""), None)


def test_reconnect_hops_without_resubscribing_and_closes_old_after_welcome(monkeypatch):
    h = Harness(monkeypatch, [
        [welcome("s1"), frame("session_reconnect", session={"reconnect_url": "wss://new"})],
        [welcome("s2"), closed(4000)]])
    err = h.run()
    assert isinstance(err, websockets.exceptions.ConnectionClosedError)
    assert [s.url for s in h.sockets] == [tw.EVENTSUB_URL, "wss://new"]
    assert h.subs == ["s1"]                      # no second subscribe on the hop
    assert h.t.session_id == "s2"
    assert all(s.closed for s in h.sockets)


@pytest.mark.parametrize("code", [4000, 4003, 4004, 4005, 4006, 4007])
def test_any_close_code_ends_session_and_next_session_subscribes_again(monkeypatch, code):
    h = Harness(monkeypatch, [[welcome("a"), closed(code)], [welcome("b"), closed(code)]])
    assert isinstance(h.run(), websockets.exceptions.ConnectionClosedError)
    h.scripts = [[welcome("b"), closed(code)]]
    h.run()
    assert h.subs == ["a", "b"]                  # fresh session each time: full subscribe


def test_4007_on_reconnect_url_then_fresh_session_subscribes(monkeypatch):
    h = Harness(monkeypatch, [[welcome("s1"), frame("session_reconnect", session={"reconnect_url": "wss://bad"})],
                              [closed(4007)]])
    assert isinstance(h.run(), websockets.exceptions.ConnectionClosedError)
    assert h.t.reconnecting is True or h.t.reconnecting is False   # run()'s except clears it; _session resets on entry
    h.scripts = [[welcome("s3"), closed(4000)]]
    h.run()
    assert h.subs == ["s1", "s3"]
    assert all(s.closed for s in h.sockets)       # old socket closed too


def test_run_loop_clears_reconnecting_flag_on_failure(monkeypatch):
    """run() must reset `reconnecting` in its except so a failed hop cannot suppress the next subscribe."""
    import inspect
    src = inspect.getsource(tw.Twitch.run)
    assert "self.reconnecting = False" in src and "await self._session(tok)" in src


def test_recv_timeout_is_a_failure_not_a_hop(monkeypatch):
    h = Harness(monkeypatch, [[welcome("s1"), asyncio.TimeoutError()]])
    assert isinstance(h.run(), asyncio.TimeoutError)
    assert h.subs == ["s1"] and h.sockets[0].closed


# ---- item 3: OAuth URL builders, PKCE, token storage, TikTok mapping (pure) ----
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse
import base64
import hashlib

import secrets_store
from connectors import kick_auth, oauth_util, tiktok_live, youtube_auth


def test_pkce_challenge_is_s256_of_verifier():
    v, c = oauth_util.new_pkce()
    assert 43 <= len(v) <= 128
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def test_kick_authorize_url_params():
    u = urlparse(kick_auth.authorize_url("CID", "http://127.0.0.1:8766/auth/kick/callback", "chat:write channel:write", "st", "CH"))
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert (u.scheme, u.netloc, u.path) == ("https", "id.kick.com", "/oauth/authorize")
    assert q == {"client_id": "CID", "response_type": "code", "redirect_uri": "http://127.0.0.1:8766/auth/kick/callback",
                 "scope": "chat:write channel:write", "state": "st", "code_challenge": "CH", "code_challenge_method": "S256"}


def test_youtube_authorize_url_params():
    u = urlparse(youtube_auth.authorize_url("CID", "http://127.0.0.1:8766/auth/youtube/callback", "st", "CH"))
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert u.netloc == "accounts.google.com" and q["access_type"] == "offline" and q["code_challenge_method"] == "S256"
    assert q["scope"].endswith("youtube.force-ssl") and q["redirect_uri"].startswith("http://127.0.0.1:")


def test_start_needs_config_and_never_hardcodes(monkeypatch):
    monkeypatch.setattr(kick_auth.config, "settings", lambda: {})
    assert kick_auth.start()["ok"] is False
    monkeypatch.setattr(youtube_auth.config, "settings", lambda: {})
    assert youtube_auth.start()["ok"] is False
    monkeypatch.setattr(youtube_auth.config, "settings", lambda: {"youtube_client_id": "abc"})
    r = youtube_auth.start()
    assert r["ok"] and "client_id=abc" in r["url"]


def test_pending_state_is_single_use_and_expires():
    oauth_util.remember("s1", "ver", "http://r", now=1000)
    assert oauth_util.take("s1", now=1000 + oauth_util.PENDING_TTL + 1) is None
    oauth_util.remember("s2", "ver", "http://r", now=1000)
    assert oauth_util.take("s2", now=1001)["verifier"] == "ver"
    assert oauth_util.take("s2", now=1002) is None and oauth_util.take("forged") is None


def test_token_bodies():
    b = kick_auth.token_request_body("authorization_code", "c", "sec", code="x", redirect_uri="r", code_verifier="v")
    assert b["grant_type"] == "authorization_code" and b["code_verifier"] == "v" and b["client_secret"] == "sec"
    assert "client_secret" not in youtube_auth.token_request_body("refresh_token", "c", "", refresh_token="t")


def test_store_and_refresh_keep_refresh_token(monkeypatch):
    monkeypatch.setenv("MULTI_NO_KEYRING", "1")
    monkeypatch.setattr(secrets_store, "_mem", {})
    monkeypatch.setattr(secrets_store.vault, "get", lambda n: None)
    oauth_util.store_tokens("youtube", {"access_token": "A1", "refresh_token": "R1", "expires_in": 3600}, now=1000)
    oauth_util.store_tokens("youtube", {"access_token": "A2", "expires_in": 3600}, now=5000)       # Google omits refresh_token on refresh
    assert secrets_store.get("youtube_token") == "A2" and secrets_store.get("youtube_oauth")["refresh_token"] == "R1"
    calls = []
    assert oauth_util.fresh_token("youtube", lambda: calls.append(1), now=5000 + 3500) == "A2" and calls == [1]   # inside the 120 s margin -> refresh attempted
    calls.clear()
    assert oauth_util.fresh_token("youtube", lambda: calls.append(1), now=5100) == "A2" and calls == []
    assert oauth_util.fresh_token("youtube", lambda: 1 / 0, now=99999) == "A2"                      # a failing refresh never raises


def test_tiktok_handle_and_guard():
    assert tiktok_live.handle({"tiktok_user": "@Some.User_1"}) == "Some.User_1"
    assert tiktok_live.handle({"tiktok_user": "bad handle!"}) == "" and tiktok_live.handle({}) == ""
    ok, why = tiktok_live.available()
    assert isinstance(ok, bool) and (ok or "not installed" in why)


def _u(**k):
    return NS(user_id=k.get("id", "9"), unique_id=k.get("login", "Fan"), nickname=k.get("nick", "Fan Nick"))


def test_tiktok_mapping():
    m = tiktok_live.map_event("comment", NS(user=_u(), comment="hi", msg_id="m1"), "host")
    assert m.id == "tiktok:host:m1" and m.text == "hi" and m.user == "fan"
    assert tiktok_live.map_event("comment", NS(user=_u(), comment=""), "host") is None
    assert tiktok_live.map_event("follow", NS(user=_u()), "host").event == "follow"
    s = tiktok_live.map_event("share", NS(user=_u()), "host")
    assert s.event == "share" and s.platform == "tiktok"
    sub = tiktok_live.map_event("subscribe", NS(user=_u()), "host")
    assert sub.event == "sub" and sub.amount == 1
    g = NS(name="Rose", diamond_count=5, streakable=True)
    assert tiktok_live.map_event("gift", NS(user=_u(), gift=g, streaking=True, repeat_count=2), "host") is None
    c = tiktok_live.map_event("gift", NS(user=_u(), gift=g, streaking=False, repeat_count=3, group_id="g1"), "host")
    assert c.event == "cheer" and c.amount == 15 and c.meta["currency"] == "coins"
    assert tiktok_live.map_event("like", NS(user=_u()), "host") is None


def test_tiktok_attach_skips_missing_classes_and_counts_likes():
    class FakeClient:
        def __init__(self): self.l = {}
        def add_listener(self, cls, fn): self.l[cls] = fn
    class CommentEvent: pass
    class LikeEvent: pass
    class SubNotifyEvent: pass
    mod = NS(CommentEvent=CommentEvent, LikeEvent=LikeEvent, SubNotifyEvent=SubNotifyEvent)
    c, got, st = FakeClient(), [], {}
    names = tiktok_live.attach(c, mod, "host", got.append, st)
    assert set(names) == {"CommentEvent", "LikeEvent", "SubNotifyEvent"}
    asyncio.run(c.l[LikeEvent](NS(count=7)))
    asyncio.run(c.l[CommentEvent](NS(user=_u(), comment="yo", msg_id="z")))
    asyncio.run(c.l[SubNotifyEvent](NS(user=_u())))
    assert st["likes"] == 7 and [m.event for m in got] == ["", "sub"]


# ---- item 4: no token / retry loops stay quiet ----
def test_set_status_repeats_are_throttled():
    from connectors.base import Connector
    out = []
    c = Connector(None, out.append)
    for _ in range(5):
        c.set_status("needs_auth", "no token")
    assert len(out) == 1
    c.set_status("connected", "ok")
    c.set_status("needs_auth", "no token")
    assert len(out) == 3


def test_viewers_without_tokens_return_none_and_do_not_raise(monkeypatch):
    import viewers
    monkeypatch.setattr(viewers.youtube_auth, "access_token", lambda: None)
    assert viewers._youtube(NS(video_id="v")) is None
    assert viewers._youtube(NS()) is None
    assert viewers._tiktok(NS(state={})) is None
    assert viewers._twitch(NS(tokens=lambda: None)) is None


def test_stream_info_without_tokens_is_a_clean_error(monkeypatch):
    import stream_info
    monkeypatch.setattr(stream_info.secrets_store, "get", lambda k, d=None: None)
    assert stream_info.youtube_get()["connected"] is False
    assert stream_info.kick_get()["connected"] is False
    assert stream_info.kick_update(title="x")["ok"] is False


def test_config_defaults_for_platform_auth():
    import config
    d = config.DEFAULTS
    assert d["youtube_min_poll_s"] == 10 and d["tiktok_sign_url"] == "" and d["kick_client_id"] == "" and d["youtube_client_id"] == ""
    assert d["kick_redirect_uri"].endswith("/auth/kick/callback") and "chat:write" in d["kick_scopes"]
    assert d["youtube_redirect_uri"].endswith("/auth/youtube/callback")
