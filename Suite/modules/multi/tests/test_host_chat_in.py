"""YouTube + TikTok chat -> Host (POST /api/chat-in): body, role, ownBot, back-off, drop-oldest, dedupe, age, switch (worker 41). Fake Host, no network."""
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


def test_not_other_platforms_events_empty_or_switched_off(monkeypatch):
    c, sent, clock = mk()
    assert not offer(c, clock, i=1, platform="kick")
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


@pytest.mark.parametrize("code", [0, 401, 403, 404])
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
    assert [b["msgId"] for b in sent] == ["youtube:1", "youtube:3"] and c.stats["sent"] == 2 and c.stats["ok"] == 1 and c.stats["last_code"] == 200


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


def test_tiktok_body_roles_and_bot_filter(monkeypatch):
    c, sent, clock = mk()
    assert offer(c, clock, i=1, platform="tiktok", user="Fan_One")
    assert offer(c, clock, i=2, platform="tiktok", badges=["super_fan"])
    assert offer(c, clock, i=3, platform="tiktok", badges=["subscriber"])
    assert offer(c, clock, i=4, platform="tiktok", is_self=True)
    assert offer(c, clock, i=5, platform="tiktok", user="Nightbot")
    assert not offer(c, clock, i=6, platform="tiktok", event="gift")
    while c.step():
        pass
    assert sent[0] == {"platform": "tiktok", "user": "Fan_One", "userId": "uid1", "text": "hi", "msgId": "tiktok:1", "role": "viewer", "isSub": False, "ownBot": False, "isBot": False}
    assert [(b["role"], b["isSub"]) for b in sent[1:3]] == [("sub", True), ("sub", True)]
    assert [b["ownBot"] for b in sent[3:]] == [True, True]
    monkeypatch.setattr(hf.config, "settings", lambda: {"host_chat_in": False, "bot_accounts": []})
    assert not offer(c, clock, i=7, platform="tiktok")


def test_tiktok_has_no_reply_path(monkeypatch):
    import server
    from connectors.tiktok import TikTok
    from fastapi.testclient import TestClient
    assert TikTok.capabilities["send"] is False and TikTok.capabilities["reply"] is False

    class Fake:
        capabilities = TikTok.capabilities

        async def send(self, text, reply_to=None):
            raise AssertionError("TikTok must never be sent to")
    monkeypatch.setitem(server.connectors, "tiktok", Fake())
    c = TestClient(server.app, base_url="http://127.0.0.1:8766")
    r = c.post("/api/send", json={"platform": "tiktok", "text": "hi"}, headers={"origin": "http://127.0.0.1:8766"})
    assert r.status_code == 400 and "read-only" in r.text


# ---- recovery, auth, heartbeat, status (worker 41) ---------------------------------------------------------------------------------------
@pytest.fixture
def logged(monkeypatch):
    out = []
    monkeypatch.setattr(hf.console_log, "log", lambda level, src, msg, dedupe_s=0: out.append((level, src, msg)))
    monkeypatch.setattr(hf.console_log, "info", lambda s, m, **k: out.append(("info", s, m)))
    monkeypatch.setattr(hf.console_log, "warn", lambda s, m, **k: out.append(("warn", s, m)))
    return out


def test_401_is_an_auth_failure_with_backoff_and_a_probe_after_it(logged):
    c, sent, clock = mk([401, 200, 200])
    offer(c, clock, i=1)
    c.step()
    assert c.stats["auth_failed"] == 1 and c.stats["last_code"] == 401
    assert any("REFUSED" in m and "401" in m for _, _, m in logged)
    offer(c, clock, i=2)
    c.step()                                               # inside the back-off: dropped, never sent
    assert [b["msgId"] for b in sent] == ["youtube:1"]
    clock[0] += 61
    offer(c, clock, i=3)
    c.step()                                               # the probe goes out; message 1 is never sent again
    offer(c, clock, i=4)
    c.step()
    assert [b["msgId"] for b in sent] == ["youtube:1", "youtube:3", "youtube:4"] and c.stats["ok"] == 2 and c.backoff_until < clock[0]


def test_host_down_then_back_next_line_after_a_minute_is_tried(logged):
    c, sent, clock = mk([0, 200])
    offer(c, clock, i=1, platform="tiktok")
    c.step()
    clock[0] += 59
    offer(c, clock, i=2)
    c.step()
    assert len(sent) == 1                                   # 59 s: still backing off
    clock[0] += 2
    offer(c, clock, i=3)
    c.step()
    assert [b["msgId"] for b in sent] == ["tiktok:1", "youtube:3"] and c.stats["last_code"] == 200
    assert c.snapshot()["backoff_until"] == 0.0


def test_heartbeat_once_a_minute_only_with_activity(logged):
    c, sent, clock = mk([200, 500])
    c.step()
    clock[0] += 61
    c.step()                                                # idle: nothing to say
    assert not [m for _, _, m in logged if m.startswith("chat-in:")]
    c.beat_at = clock[0]                                    # a heartbeat was just due; the minute starts now
    offer(c, clock, i=1)
    offer(c, clock, i=2)
    c.step()
    c.step()                                                # inside one minute: no line yet
    assert not [m for _, _, m in logged if m.startswith("chat-in:")]
    clock[0] += 61
    c._beat()
    beats = [(lv, m) for lv, _, m in logged if m.startswith("chat-in:")]
    assert len(beats) == 1 and "sent 2, ok 1, failed 1 (last: 500)" in beats[0][1] and beats[0][0] == "warn" and "backoff until none" in beats[0][1]
    clock[0] += 61
    c._beat()
    assert len([1 for _, _, m in logged if m.startswith("chat-in:")]) == 1      # nothing new since: silent


def test_host_bearer_uses_the_hosts_token_not_multis_own(monkeypatch, tmp_path):
    import alerts
    (tmp_path / "module_secret").write_text("k" * 64)
    monkeypatch.delenv("PINGUINO_MODULE_TOKEN", raising=False)
    monkeypatch.setenv("PINGUINO_API_TOKEN", "multi-own-token")
    monkeypatch.setenv("PINGUINO_DATA_DIR", str(tmp_path))
    assert hf.host_bearer() == alerts.host_token(str(tmp_path), "host") and hf.host_bearer() != "multi-own-token"
    monkeypatch.setenv("PINGUINO_DATA_DIR", str(tmp_path / "none"))
    assert hf.host_bearer() == "multi-own-token"            # no shared key: standalone fallback
    monkeypatch.setenv("PINGUINO_MODULE_TOKEN", "explicit")
    assert hf.host_bearer() == "explicit"


def test_fake_host_status_codes_end_to_end(monkeypatch):
    codes = iter([401, 404, 200])
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(self.headers.get("Authorization"))
            self.send_response(next(codes))
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(hf, "HOST", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("PINGUINO_MODULE_TOKEN", "t")
    try:
        assert [hf._chat_in_post({}) for _ in range(3)] == [401, 404, 200]
    finally:
        srv.shutdown()


def test_timeout_counts_as_unreachable(monkeypatch):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)                                            # accepts the connection, never answers: the 2 s timeout
    monkeypatch.setattr(hf, "HOST", f"http://127.0.0.1:{s.getsockname()[1]}")
    monkeypatch.setenv("PINGUINO_MODULE_TOKEN", "t")
    try:
        assert hf._chat_in_post({}) == 0
    finally:
        s.close()


def test_host_status_endpoint_carries_the_counters():
    import server
    from fastapi.testclient import TestClient
    r = TestClient(server.app, base_url="http://127.0.0.1:8766").get("/api/host-status", headers={"origin": "http://127.0.0.1:8766"}).json()
    assert {"up", "chat_in"} <= set(r) and {"sent", "ok", "failed", "dropped", "auth_failed", "last_code", "queued", "backoff_until"} <= set(r["chat_in"])
