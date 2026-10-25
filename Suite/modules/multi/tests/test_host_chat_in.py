"""YouTube chat -> Host (POST /api/chat-in): body, role, ownBot, back-off, drop-oldest, dedupe, age, switch (worker 41). Fake Host, no network."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import host_feed as hf
from models import ChatMessage


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("MULTI_NO_SEND", raising=False)
    monkeypatch.setattr(hf.config, "settings", lambda: {"host_chat_in": True, "bot_accounts": []})


def msg(i=1, platform="youtube", badges=(), user="Ann", text="hi", ts=None, **kw):
    import time
    return ChatMessage(id=f"{platform}:{i}", platform=platform, channel="c", user_id=f"uid{i}", user=user.lower(), display=user, text=text,
                       ts=time.time() if ts is None else ts, badges=list(badges), **kw)


def mk(codes=None):
    sent, clock = [], [1000.0]
    seq = iter(codes or [])

    def post(body):
        sent.append(body)
        return next(seq, 200)
    c = hf.ChatIn(post=post, now=lambda: clock[0])
    c.thread = object()                                  # no worker thread: tests drive step() themselves
    return c, sent, clock


def offer(c, clock, **kw):
    return c.offer(msg(ts=clock[0], **kw))


def test_body_exact_and_roles():
    c, sent, clock = mk()
    assert offer(c, clock, i=1, badges=["owner"], user="Boss")
    assert offer(c, clock, i=2, badges=["moderator", "member"])
    assert offer(c, clock, i=3, badges=["member"])
    assert offer(c, clock, i=4, badges=["sponsor"])
    assert offer(c, clock, i=5)
    while c.step():
        pass
    assert sent[0] == {"platform": "youtube", "user": "Boss", "userId": "uid1", "text": "hi", "msgId": "youtube:1", "role": "broadcaster", "isSub": False, "ownBot": False, "isBot": False}
    assert [(b["role"], b["isSub"]) for b in sent[1:]] == [("mod", True), ("sub", True), ("sub", True), ("viewer", False)]


def test_own_bot_flags():
    c, sent, clock = mk()
    offer(c, clock, i=1, is_self=True)
    offer(c, clock, i=2, user="PinguinoB0t")
    offer(c, clock, i=3, user="Nightbot")
    offer(c, clock, i=4, user="human")
    while c.step():
        pass
    assert [b["ownBot"] for b in sent] == [True, True, True, False]
    assert [b["isBot"] for b in sent] == [b["ownBot"] for b in sent]


def test_not_youtube_events_empty_or_switched_off(monkeypatch):
    c, sent, clock = mk()
    assert not offer(c, clock, i=1, platform="tiktok")
    assert not offer(c, clock, i=2, platform="twitch")
    assert not offer(c, clock, i=3, event="cheer")
    assert not offer(c, clock, i=4, text="  ")
    assert not c.q
    monkeypatch.setattr(hf.config, "settings", lambda: {"host_chat_in": False, "bot_accounts": []})
    assert not offer(c, clock, i=5)
    monkeypatch.setenv("MULTI_NO_SEND", "1")
    monkeypatch.setattr(hf.config, "settings", lambda: {"bot_accounts": []})
    assert not offer(c, clock, i=6)


def test_dedupe_and_age():
    c, sent, clock = mk()
    assert offer(c, clock, i=1)
    assert not offer(c, clock, i=1)                       # same msgId never twice
    assert not c.offer(msg(i=2, ts=clock[0] - 31))        # history backfill
    assert c.offer(msg(i=3, ts=clock[0] - 5))
    c.step()
    clock[0] += 40                                        # went stale while queued: dropped, not sent
    c.step()
    assert len(sent) == 1 and c.stats["dropped"] == 1


def test_drop_oldest_when_full():
    c, sent, clock = mk()
    c.q = type(c.q)(maxlen=3)
    for i in range(1, 6):
        offer(c, clock, i=i)
    while c.step():
        pass
    assert [b["msgId"] for b in sent] == ["youtube:3", "youtube:4", "youtube:5"] and c.stats["dropped"] == 2


@pytest.mark.parametrize("code", [0, 404])
def test_backoff_60s_then_continue(code):
    c, sent, clock = mk([code])
    offer(c, clock, i=1)
    c.step()                                              # fails: back off, never retried
    offer(c, clock, i=2)
    c.step()                                              # inside the back-off: dropped, not even tried
    assert len(sent) == 1 and c.stats["failed"] == 1
    clock[0] += 61
    offer(c, clock, i=3)
    c.step()
    assert [b["msgId"] for b in sent] == ["youtube:1", "youtube:3"] and c.stats["sent"] == 1


def test_server_error_not_retried_no_backoff():
    c, sent, clock = mk([500])
    offer(c, clock, i=1)
    offer(c, clock, i=2)
    c.step()
    c.step()
    assert [b["msgId"] for b in sent] == ["youtube:1", "youtube:2"]


def test_real_post_to_loopback_fake_host(monkeypatch):
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got["path"], got["auth"] = self.path, self.headers.get("Authorization")
            got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(hf, "HOST", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("PINGUINO_MODULE_TOKEN", "tok123")
    try:
        assert hf._chat_in_post({"a": 1}) == 200
    finally:
        srv.shutdown()
    assert got == {"path": "/api/chat-in", "auth": "Bearer tok123", "body": {"a": 1}}


def test_non_loopback_url_refused(monkeypatch):
    monkeypatch.setattr(hf.config, "settings", lambda: {"host_url": "http://127.0.0.1.evil.com"})
    assert hf._chat_in_post({"a": 1}) == 0


def test_worker_thread_sends_in_background(monkeypatch):
    sent, ev = [], threading.Event()
    c = hf.ChatIn(post=lambda b: (sent.append(b), ev.set())[1] or 200)
    assert c.offer(msg(i=9))
    assert ev.wait(3) and sent[0]["msgId"] == "youtube:9"
