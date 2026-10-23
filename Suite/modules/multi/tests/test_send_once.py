"""Hard rule: never send duplicate messages (worker 42). Every outbound chat path is driven with mocked HTTP only (no network, no real sends).
At most one request per user action even on timeout / 5xx / token refresh / double click / server retry, and nothing sends with MULTI_NO_SEND or from sim events."""
import asyncio
from types import SimpleNamespace as NS

import pytest
import requests

from connectors import base, discord, kick, twitch, youtube


class Net:
    """Scripted HTTP answers shared by all connector modules; counts every request that would leave the machine."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, **k):
        self.calls.append((url, k))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, BaseException):
            raise a
        return a


def R(code=200, js=None):
    return NS(status_code=code, headers={}, text="", json=lambda: js if js is not None else {})


OK = {"tw": R(200, {"data": [{"is_sent": True, "message_id": "m1"}]}), "kick": R(200, {"data": {"is_sent": True, "message_id": "k1"}}),
      "dc": R(200, {"id": "d1"}), "yt": R(200, {"id": "y1"})}


def make(kind, monkeypatch, net):
    """-> (connector, send coroutine factory). Auth/lookup helpers are stubbed; requests.post is the scripted Net."""
    if kind == "tw":
        c = twitch.Twitch(None, lambda e: None)
        c.user, c.broadcaster_id = {"login": "me", "user_id": "1"}, "2"
        c.capabilities = dict(c.capabilities, send=True, reply=True)
        monkeypatch.setattr(c, "tokens", lambda: {"access_token": "a", "client_id": "c", "refresh_token": "r"})
        monkeypatch.setattr(twitch.requests, "post", net)
    elif kind == "kick":
        c = kick.Kick(None, lambda e: None)
        monkeypatch.setattr(c, "refresh_caps", lambda: True)
        monkeypatch.setattr(c, "_my_id", lambda: 5)
        monkeypatch.setattr(c, "_headers", lambda: {})
        monkeypatch.setattr(kick.requests, "post", net)
    elif kind == "dc":
        c = discord.Discord(None, lambda e: None)
        c.user = {"login": "bot", "user_id": "9"}
        c.capabilities = dict(c.capabilities, send=True)
        monkeypatch.setattr(c, "channels", lambda: ["77"])
        monkeypatch.setattr(c, "token", lambda: "t")
        monkeypatch.setattr(discord.requests, "post", net)
    else:
        c = youtube.YouTube(None, lambda e: None)
        c.chat_id = "chat"
        monkeypatch.setattr(c, "_h", lambda: {})
        monkeypatch.setattr(youtube.requests, "post", net)
    return c


KINDS = ["tw", "kick", "dc", "yt"]


def send(c, text="hello", reply=None):
    return asyncio.run(c.send(text, reply))


@pytest.mark.parametrize("kind", KINDS)
def test_success_then_repeat_is_blocked(kind, monkeypatch):
    net = Net(OK[kind])
    c = make(kind, monkeypatch, net)
    send(c)
    with pytest.raises(base.DuplicateSend):
        send(c, "  HELLO ")                                # case/space variants are the same line
    assert len(net.calls) == 1


@pytest.mark.parametrize("exc", [requests.Timeout("read timed out"), requests.ConnectionError("reset"), ValueError("bad json")])
@pytest.mark.parametrize("kind", KINDS)
def test_timeout_or_garbage_answer_is_never_retried(kind, exc, monkeypatch):
    net = Net(exc)
    c = make(kind, monkeypatch, net)
    with pytest.raises(Exception) as first:
        send(c)
    assert not isinstance(first.value, base.DuplicateSend)
    for _ in range(3):                                      # impatient retries (UI, server, Host fallback)
        with pytest.raises(base.DuplicateSend):
            send(c)
    assert len(net.calls) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_5xx_may_have_been_processed_so_not_retried(kind, monkeypatch):
    net = Net(R(503))
    c = make(kind, monkeypatch, net)
    with pytest.raises(RuntimeError):
        send(c)
    with pytest.raises(base.DuplicateSend):
        send(c)
    assert len(net.calls) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_definite_refusal_4xx_frees_the_line(kind, monkeypatch):
    net = Net(R(403), OK[kind])
    c = make(kind, monkeypatch, net)
    with pytest.raises(base.SendRejected):
        send(c)
    send(c)                                                  # the platform said no before sending: trying again is safe
    with pytest.raises(base.DuplicateSend):
        send(c)
    assert len(net.calls) == 2


def test_twitch_dropped_message_and_429_free_the_line(monkeypatch):
    net = Net(R(200, {"data": [{"is_sent": False, "drop_reason": {"code": "x"}}]}), NS(status_code=429, headers={"Retry-After": "3"}, text="", json=dict), OK["tw"])
    c = make("tw", monkeypatch, net)
    with pytest.raises(base.SendRejected):
        send(c)
    with pytest.raises(twitch.TwitchBusy):
        send(c)
    send(c)
    assert len(net.calls) == 3


@pytest.mark.parametrize("kind", KINDS)
def test_concurrent_double_click_sends_once(kind, monkeypatch):
    net = Net(OK[kind])
    c = make(kind, monkeypatch, net)

    async def both():
        return await asyncio.gather(c.send("hi", None), c.send("hi", None), c.send("hi", None), return_exceptions=True)
    res = asyncio.run(both())
    assert sum(isinstance(r, str) for r in res) == 1 and sum(isinstance(r, base.DuplicateSend) for r in res) == 2
    assert len(net.calls) == 1


def test_different_line_or_reply_target_is_a_different_action(monkeypatch):
    net = Net(OK["dc"])
    c = make("dc", monkeypatch, net)
    send(c, "hi")
    send(c, "hi!")
    send(c, "hi", "discord:77:5")                            # same words as a reply to a message: its own action
    assert len(net.calls) == 3


@pytest.mark.parametrize("kind", KINDS)
def test_window_expires(kind, monkeypatch):
    net = Net(OK[kind])
    c = make(kind, monkeypatch, net)
    send(c)
    now = base.time.time()
    monkeypatch.setattr(base.time, "time", lambda: now + base.SEND_WINDOW_S + 1)
    send(c)
    assert len(net.calls) == 2


# ---- Twitch 401 -> refresh -> retry inside ONE action ------------------------------------------------------------
def test_twitch_401_refresh_retry_is_one_message(monkeypatch):
    net = Net(R(401), OK["tw"])
    c = make("tw", monkeypatch, net)
    monkeypatch.setattr(c, "refresh", lambda tk: dict(tk, access_token="new"))
    send(c)
    assert len(net.calls) == 2                               # first rejected (401 = not processed), second delivered
    with pytest.raises(base.DuplicateSend):
        send(c)
    assert len(net.calls) == 2


def test_twitch_401_then_timeout_on_the_retry_is_not_repeated(monkeypatch):
    net = Net(R(401), requests.Timeout("slow"))
    c = make("tw", monkeypatch, net)
    monkeypatch.setattr(c, "refresh", lambda tk: dict(tk, access_token="new"))
    with pytest.raises(requests.Timeout):
        send(c)
    with pytest.raises(base.DuplicateSend):
        send(c)
    assert len(net.calls) == 2


def test_twitch_401_with_dead_refresh_sends_nothing_and_allows_later_retry(monkeypatch):
    net = Net(R(401), OK["tw"])
    c = make("tw", monkeypatch, net)
    monkeypatch.setattr(c, "refresh", lambda tk: None)
    with pytest.raises(twitch.TwitchAuthError):
        send(c)
    monkeypatch.setattr(c, "refresh", lambda tk: dict(tk, access_token="new"))
    send(c)
    assert len(net.calls) == 2


# ---- sim / rehearsal switch ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", KINDS)
def test_no_send_switch_blocks_every_connector(kind, monkeypatch):
    monkeypatch.setenv("MULTI_NO_SEND", "1")
    net = Net(OK[kind])
    c = make(kind, monkeypatch, net)
    with pytest.raises(base.SendRejected, match="MULTI_NO_SEND"):
        send(c)
    assert net.calls == []


# ---- server /api/send on top of the connector guard ---------------------------------------------------------------
def server_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server
    from store import Store
    monkeypatch.setattr(server, "store", Store(tmp_path / "s.db"))
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    server._RECENT_SENDS.clear()
    return server, TestClient(server.app, base_url="http://127.0.0.1:8766"), {"origin": "http://127.0.0.1:8766"}


def test_server_retry_after_timeout_cannot_double_send(tmp_path, monkeypatch):
    """server.py forgets its own 30 s key when a send raises; the connector guard must still stop the second HTTP request."""
    server, c, h = server_client(tmp_path, monkeypatch)
    net = Net(requests.Timeout("slow"), OK["dc"])
    dc = make("dc", monkeypatch, net)
    monkeypatch.setitem(server.connectors, "discord", dc)
    assert c.post("/api/send", json={"platform": "discord", "text": "gg"}, headers=h).status_code == 502
    for _ in range(3):
        assert c.post("/api/send", json={"platform": "discord", "text": "gg"}, headers=h).json()["duplicate"] is True
    assert len(net.calls) == 1


def test_server_double_click_burst_sends_once(tmp_path, monkeypatch):
    server, c, h = server_client(tmp_path, monkeypatch)
    net = Net(OK["dc"])
    monkeypatch.setitem(server.connectors, "discord", make("dc", monkeypatch, net))
    rs = [c.post("/api/send", json={"platform": "discord", "text": "gg"}, headers=h).json() for _ in range(4)]
    assert [r.get("duplicate", False) for r in rs] == [False, True, True, True] and len(net.calls) == 1


def test_twitch_plain_line_uses_host_only_and_never_also_direct(tmp_path, monkeypatch):
    import host_feed
    server, c, h = server_client(tmp_path, monkeypatch)
    net = Net(OK["tw"])
    monkeypatch.setitem(server.connectors, "twitch", make("tw", monkeypatch, net))
    said = []

    async def say_ok(text):
        said.append(text)
        return {"ok": True, "via": "host"}
    monkeypatch.setattr(host_feed, "say", say_ok)
    assert c.post("/api/send", json={"platform": "twitch", "text": "yo"}, headers=h).json()["ok"] is True
    assert said == ["yo"] and net.calls == []                # Host answered: the direct route is NOT also used

    async def say_timeout(text):
        said.append(text)
        return {"ok": True, "via": "timed out (may have gone out, not repeated)"}
    monkeypatch.setattr(host_feed, "say", say_timeout)
    assert c.post("/api/send", json={"platform": "twitch", "text": "yo2"}, headers=h).json()["ok"] is True
    assert net.calls == []                                   # ambiguous Host answer: never retried directly


def test_twitch_host_down_falls_back_once_and_host_refusal_does_not_fall_back(tmp_path, monkeypatch):
    import host_feed
    server, c, h = server_client(tmp_path, monkeypatch)
    net = Net(OK["tw"])
    monkeypatch.setitem(server.connectors, "twitch", make("tw", monkeypatch, net))

    async def down(text):
        return None
    monkeypatch.setattr(host_feed, "say", down)
    assert c.post("/api/send", json={"platform": "twitch", "text": "a"}, headers=h).json()["ok"] is True
    assert c.post("/api/send", json={"platform": "twitch", "text": "a"}, headers=h).json()["duplicate"] is True
    assert len(net.calls) == 1

    async def refused(text):
        return {"ok": False, "via": "Host refused (403)"}
    monkeypatch.setattr(host_feed, "say", refused)
    assert c.post("/api/send", json={"platform": "twitch", "text": "b"}, headers=h).status_code == 502
    assert len(net.calls) == 1                               # refusal is reported, not silently re-sent another way


def test_sim_and_test_events_never_send(tmp_path, monkeypatch):
    """Injected chat, sim/test events and every ingest side effect (cards, intros, alerts) must not touch any send path."""
    import host_feed
    server, c, h = server_client(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise AssertionError("a send path was used by a sim/test event")

    async def aboom(*a, **k):
        boom()
    monkeypatch.setattr(host_feed, "say", aboom)
    monkeypatch.setattr(base.Connector, "send_once", aboom)
    for cls in (twitch.Twitch, kick.Kick, discord.Discord, youtube.YouTube):
        monkeypatch.setattr(cls, "send", aboom)
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setattr(twitch.requests, "post", boom)
    for i, body in enumerate([{"user": "a", "text": "hello @pingu?"}, {"user": "b", "event": "follow", "text": "b followed", "sim": True},
                              {"user": "c", "event": "sub", "amount": 1, "test": True, "text": "c subbed"}, {"user": "d", "event": "raid", "amount": 50, "text": "d raids"},
                              {"user": "e", "text": "first time here", "platform": "youtube"}]):
        r = c.post("/api/dev/inject", json=dict(body, id=f"sim:{i}"), headers=h)
        assert r.status_code == 200, r.text


# ---- Host fallback and server key (applied in host_feed.py / server.py) ----------------------------------------------
def test_host_say_maps_5xx_to_may_have_gone_out_and_honours_no_send(monkeypatch):
    import io
    import urllib.error
    import host_feed

    def raising(code):
        def f(req, timeout=0):
            raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
        return f
    monkeypatch.setattr(host_feed.urllib.request, "urlopen", raising(502))
    r = host_feed._say_sync("hi")
    assert r["ok"] is True and "may have gone out" in r["via"]                    # not freed -> never repeated
    monkeypatch.setattr(host_feed.urllib.request, "urlopen", raising(403))
    assert host_feed._say_sync("hi")["ok"] is False                               # definite refusal
    monkeypatch.setenv("MULTI_NO_SEND", "1")
    monkeypatch.setattr(host_feed.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent")))
    assert host_feed._say_sync("hi")["ok"] is False


def test_server_keeps_key_after_unknown_outcome_but_frees_it_after_refusal(tmp_path, monkeypatch):
    server, c, h = server_client(tmp_path, monkeypatch)
    calls = []

    class Fake:
        capabilities = {"send": True, "reply": False}
        user = None
        errs = [requests.Timeout("slow"), base.SendRejected("no"), None]

        async def send(self, text, reply_to=None):
            calls.append(text)
            e = Fake.errs.pop(0)
            if e:
                raise e
            return "discord:x:1"
    monkeypatch.setitem(server.connectors, "discord", Fake())
    post = lambda t: c.post("/api/send", json={"platform": "discord", "text": t}, headers=h)
    assert post("a").status_code == 502
    assert post("a").json()["duplicate"] is True and len(calls) == 1             # timeout: the server itself refuses the retry too
    assert post("b").status_code == 502 and post("b").json()["ok"] is True       # refusal: retry allowed
