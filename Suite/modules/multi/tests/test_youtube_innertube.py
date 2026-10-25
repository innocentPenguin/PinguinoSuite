"""YouTube InnerTube reader: parsers on hand-made payloads, the poll/fetch state machine on a fake requests, mode dispatch + fallback. No network."""
import asyncio
import json
import time

import pytest

import config
from connectors import youtube as yt
from connectors import youtube_innertube as it

NOW_US = lambda: str(int(time.time() * 1e6))


def text_item(i, msg="hello", uid="UCa", name="Amy", badge=None, usec=None):
    r = {"id": i, "authorExternalChannelId": uid, "authorName": {"simpleText": name}, "timestampUsec": usec or NOW_US(),
         "message": {"runs": [{"text": msg + " "}, {"emoji": {"emojiId": "UCx/abc", "shortcuts": [":wave_tux:"], "isCustomEmoji": True}},
                              {"emoji": {"emojiId": "😀"}}]}}
    if badge:
        r["authorBadges"] = [{"liveChatAuthorBadgeRenderer": {"icon": {"iconType": badge}}}]
    return {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": r}}}


def paid_item(i, amount="€2,50"):
    return {"addChatItemAction": {"item": {"liveChatPaidMessageRenderer": {
        "id": i, "authorExternalChannelId": "UCp", "authorName": {"simpleText": "Pay"}, "timestampUsec": NOW_US(),
        "purchaseAmountText": {"simpleText": amount}, "message": {"runs": [{"text": "thx"}]}}}}}


def member_item(i, head=None):
    r = {"id": i, "authorExternalChannelId": "UCm", "authorName": {"simpleText": "Mem"}, "timestampUsec": NOW_US()}
    if head:
        r["headerPrimaryText"] = {"runs": [{"text": head}]}
    return {"addChatItemAction": {"item": {"liveChatMembershipItemRenderer": r}}}


def gift_item(i):
    return {"addChatItemAction": {"item": {"liveChatSponsorshipsGiftPurchaseAnnouncementRenderer": {
        "id": i, "authorExternalChannelId": "UCg", "timestampUsec": NOW_US(), "header": {"liveChatSponsorshipsHeaderRenderer": {
            "authorName": {"simpleText": "Gifter"}, "primaryText": {"runs": [{"text": "Sent "}, {"text": "5"}, {"text": " Memberships"}]}}}}}}}


def lcc(actions, cont="C2", ms=1200, key="timedContinuationData"):
    return {"actions": actions, "continuations": [{key: {"continuation": cont, "timeoutMs": ms}}]}


def page_html(actions=(), cont="C1", ms=2000, chat=True):
    data = {"contents": {"liveChatRenderer": lcc(list(actions), cont, ms)}} if chat else {"contents": {}}
    return ('<html><script>ytcfg.set({"INNERTUBE_API_KEY":"KEY123","INNERTUBE_CONTEXT_CLIENT_VERSION":"2.2024"});</script>'
            '<script>window["ytInitialData"] = ' + json.dumps(data) + ';</script></html>')


class Resp:
    def __init__(self, body=None, text="", code=200):
        self.status_code, self._b, self.text = code, body, text or ""

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise it.requests.HTTPError(f"{self.status_code}")


# ---- parsers ---------------------------------------------------------------------------------------------------
def test_text_message_fields():
    msgs, cleared = it.parse_actions([text_item("m1", badge="MODERATOR")], "VID")
    m = msgs[0]
    assert m.id == "youtube:VID:m1" and m.platform == "youtube" and m.channel == "VID" and m.user_id == "UCa" and m.display == "Amy"
    assert m.text == "hello :wave_tux:😀" and m.badges == ["moderator"] and m.emotes and not m.is_self and cleared == []
    assert it.parse_actions([text_item("m2", badge="OWNER")], "V")[0][0].is_self
    assert it.parse_actions([text_item("m3", uid="UCme")], "V", my_channel="UCme")[0][0].is_self


def test_paid_member_gift_events():
    msgs, _ = it.parse_actions([paid_item("p1"), member_item("b1"), member_item("b2", "Member for 2 years"), gift_item("g1")], "V")
    p, new, old, g = msgs
    assert (p.event, p.amount, p.meta["currency"], p.meta["message"]) == ("cheer", 3, "€", "thx") or p.amount == 2
    assert new.event == "sub" and old.event == "resub" and old.amount == 24 and (g.event, g.amount) == ("gift", 5)
    assert all(x.meta["notice"] for x in msgs)


def test_parse_amount():
    assert it.parse_amount("$5.00") == (5, "$") and it.parse_amount("CA$1,000.00")[0] == 1000 and it.parse_amount("€2,50")[0] in (2, 3)
    assert it.parse_amount("") == (1, "") and it.parse_amount("¥500") == (500, "¥") and it.parse_amount(None)[0] == 1


def test_deletes_and_garbage_never_raise():
    acts = [{"markChatItemAsDeletedAction": {"targetItemId": "m9"}}, {"removeChatItemByAuthorAction": {"externalChannelId": "UCbad"}},
            {"markChatItemAsDeletedAction": {}}, None, 5, "x", {"addChatItemAction": None}, {"addChatItemAction": {"item": {"weird": 1}}},
            {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"id": "x"}}}},
            {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"id": "y", "authorExternalChannelId": "u", "authorName": 5, "message": 7,
                                                                           "timestampUsec": "junk", "authorBadges": [None, 3]}}}}]
    msgs, cleared = it.parse_actions(acts, "V")
    assert cleared == [("message", "youtube:V:m9"), ("user", "UCbad")] and [m.id for m in msgs] == ["youtube:V:y"]
    assert it.parse_actions(None, "V") == ([], []) and it.parse_actions("x", "V") == ([], [])


def test_next_continuation_variants_and_clamp():
    assert it.next_continuation(lcc([], "A", 100, "invalidationContinuationData")) == ("A", it.MIN_WAIT)
    assert it.next_continuation(lcc([], "B", 99999)) == ("B", it.MAX_WAIT)
    assert it.next_continuation(lcc([], "R", "x", "reloadContinuationData")) == ("R", 1.5)
    assert it.next_continuation({"continuations": [{}, None]}) == (None, 0) and it.next_continuation(None) == (None, 0)


def test_parse_page_and_not_live():
    p = it.parse_page(page_html([text_item("a")]))
    assert p["key"] == "KEY123" and p["version"] == "2.2024" and p["continuation"] == "C1" and len(p["actions"]) == 1 and p["wait"] == 2.0
    for bad in (page_html(chat=False), "<html></html>", "", None, "ytInitialData = {broken"):
        with pytest.raises(it.NotLive):
            it.parse_page(bad)


def test_watch_target_and_live_page():
    assert it.watch_target("https://www.youtube.com/watch?v=abcdefghijk") == ("abcdefghijk", None)
    assert it.watch_target("https://youtu.be/abcdefghijk")[0] == "abcdefghijk"
    assert it.watch_target("@Pinguino") == (None, "https://www.youtube.com/@Pinguino/live")
    assert it.watch_target("Pinguino")[1] == "https://www.youtube.com/@Pinguino/live"
    uc = "UC" + "a" * 22
    assert it.watch_target(uc) == (None, f"https://www.youtube.com/channel/{uc}/live") and it.watch_target("") == (None, None)
    live = '<link rel="canonical" href="https://www.youtube.com/watch?v=abcdefghijk"><x>"isLiveNow":true</x>'
    assert it.live_video_from_page(live) == "abcdefghijk" and it.live_video_from_page("<x>nothing</x>") is None and it.live_video_from_page(None) is None


# ---- reader state machine --------------------------------------------------------------------------------------
def test_reader_fetch_poll_dedupe_backlog_and_expiry(monkeypatch):
    old = text_item("old", usec=str(int((time.time() - 600) * 1e6)))
    seq = [Resp(text=page_html([old, text_item("new1")]))]
    posts = []
    monkeypatch.setattr(it.requests, "get", lambda *a, **k: seq[0])
    answers = iter([Resp({"continuationContents": {"liveChatContinuation": lcc([text_item("new1"), text_item("n2"),
                                                                                {"markChatItemAsDeletedAction": {"targetItemId": "n2"}}], "C3", 800)}}),
                    Resp({"continuationContents": {"liveChatContinuation": {"actions": []}}}),
                    Resp({}, code=404)])
    monkeypatch.setattr(it.requests, "post", lambda url, **k: posts.append(k) or next(answers))
    r = it.Reader("VID")
    first, _ = r.fetch()
    assert [m.id for m in first] == ["youtube:VID:new1"]                      # 10-minute-old backlog is remembered, not emitted
    msgs, cleared = r.poll()
    assert [m.id for m in msgs] == ["youtube:VID:n2"] and cleared == [("message", "youtube:VID:n2")]    # new1 not repeated
    assert posts[0]["json"]["continuation"] == "C1" and posts[0]["params"]["key"] == "KEY123" and r.cont == "C3" and r.wait == 0.8
    with pytest.raises(it.Expired):
        r.poll()                                                               # no continuation in the answer
    with pytest.raises(it.Expired):
        r.poll()                                                               # 404


def test_reader_bad_json_and_http_errors(monkeypatch):
    r = it.Reader("V")
    r.key, r.version, r.cont = "k", "v", "c"
    monkeypatch.setattr(it.requests, "post", lambda *a, **k: Resp(None))
    with pytest.raises(ValueError):
        r.poll()
    monkeypatch.setattr(it.requests, "post", lambda *a, **k: Resp({}, code=500))
    with pytest.raises(it.requests.HTTPError):
        r.poll()
    monkeypatch.setattr(it.requests, "post", lambda *a, **k: Resp([1, 2]))
    with pytest.raises(it.Expired):
        r.poll()


def test_resolve_prefers_video_then_channel(monkeypatch):
    assert it.Reader.resolve("", "https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert it.Reader.resolve("@x", "abcdefghijk") == "abcdefghijk"
    html = '<link rel="canonical" href="https://www.youtube.com/watch?v=zzzzzzzzzzz">"isLiveNow":true'
    got = []
    monkeypatch.setattr(it.requests, "get", lambda url, **k: got.append(url) or Resp(text=html))
    assert it.Reader.resolve("@x") == "zzzzzzzzzzz" and got == ["https://www.youtube.com/@x/live"]
    monkeypatch.setattr(it.requests, "get", lambda url, **k: Resp(text="<html>offline</html>"))
    assert it.Reader.resolve("@x") is None and it.Reader.resolve("") is None


# ---- connector ------------------------------------------------------------------------------------------------
class Inbox:
    def __init__(self): self.items = []
    def put(self, m): self.items.append(m)


def _conn(monkeypatch, **cfg):
    s = dict(config.DEFAULTS, **cfg)
    monkeypatch.setattr(yt.config, "settings", lambda: s)
    monkeypatch.setattr(yt.secrets_store, "get", lambda k, *a: cfg.get("_" + k))
    ev = []
    c = yt.YouTube(Inbox(), ev.append)
    return c, ev


def _run_steps(c, n):
    async def go():
        for _ in range(n):
            await c._innertube_step()
    sleeps = []

    async def fake(s): sleeps.append(s)
    real = asyncio.sleep
    asyncio.sleep = fake
    try:
        asyncio.run(go())
    finally:
        asyncio.sleep = real
    return sleeps


def test_default_mode_is_innertube_and_keys_exist():
    d = config.DEFAULTS
    assert d["youtube_read_mode"] == "innertube" and d["youtube_channel"] == "" and d["youtube_video_id"] == "" and d["youtube_innertube_fallback_min"] == 5


def test_connector_innertube_flow_and_clear_callback(monkeypatch):
    c, ev = _conn(monkeypatch, youtube_video_id="abcdefghijk")
    cl = []
    c.on_cleared = lambda scope, reason, **kw: cl.append((scope, reason, kw))
    html = page_html([text_item("a")])
    monkeypatch.setattr(it.requests, "get", lambda *a, **k: Resp(text=html))
    monkeypatch.setattr(it.requests, "post", lambda *a, **k: Resp({"continuationContents": {"liveChatContinuation": lcc(
        [text_item("b"), {"markChatItemAsDeletedAction": {"targetItemId": "b"}}, {"removeChatItemByAuthorAction": {"externalChannelId": "UCz"}}], "C9", 1000)}}))
    sl = _run_steps(c, 2)
    assert [m.id for m in c.inbox.items] == ["youtube:abcdefghijk:a", "youtube:abcdefghijk:b"] and c.state["status"] == "connected"
    assert sl == [2.0, 1.0]
    assert cl == [("message", "delete", {"platform": "youtube", "channel": "abcdefghijk", "ids": ["youtube:abcdefghijk:b"]}),
                  ("user", "ban", {"platform": "youtube", "channel": "abcdefghijk", "user_id": "UCz"})]


def test_connector_not_live_setup_and_expired(monkeypatch):
    c, ev = _conn(monkeypatch)                                                  # nothing configured, no token
    _run_steps(c, 1)
    assert c.state["status"] == "needs_setup"
    c, ev = _conn(monkeypatch, youtube_channel="@x")
    monkeypatch.setattr(it.requests, "get", lambda *a, **k: Resp(text="<html>offline</html>"))
    _run_steps(c, 1)
    assert c.state["status"] == "waiting"
    c, ev = _conn(monkeypatch, youtube_video_id="abcdefghijk")
    monkeypatch.setattr(it.requests, "get", lambda *a, **k: Resp(text=page_html(chat=False)))
    _run_steps(c, 1)
    assert c.state["status"] == "waiting" and c.reader is None
    monkeypatch.setattr(it.requests, "get", lambda *a, **k: Resp(text=page_html()))
    monkeypatch.setattr(it.requests, "post", lambda *a, **k: Resp({}, code=404))
    _run_steps(c, 2)
    assert c.reader is None                                                      # expired -> will refetch


def test_connector_survives_garbage_and_falls_back_to_api(monkeypatch):
    c, ev = _conn(monkeypatch, youtube_video_id="abcdefghijk", _youtube_token="tok", youtube_innertube_fallback_min=5)
    def boom(*a, **k): raise OSError("net down")
    monkeypatch.setattr(it.requests, "get", boom)
    api = []

    async def fake_api():
        api.append(1)
    monkeypatch.setattr(c, "_api_step", fake_api)
    _run_steps(c, 2)
    assert c.state["status"] == "reconnecting" and not api and c.state["reconnects"] == 2          # not yet 5 minutes
    c.fail_since = time.time() - 400
    _run_steps(c, 1)
    assert api == [1] and "official API" in c.state["detail"]
    c, ev = _conn(monkeypatch, youtube_video_id="abcdefghijk")                                       # no token: never falls back
    c.fail_since = time.time() - 4000
    monkeypatch.setattr(c, "_api_step", fake_api)
    _run_steps(c, 1)
    assert api == [1]


def test_run_dispatches_on_read_mode(monkeypatch):
    for mode, want in (("api", "_api_step"), ("innertube", "_innertube_step"), ("", "_innertube_step")):
        c, ev = _conn(monkeypatch, youtube_read_mode=mode)
        called = []

        async def mark(name=want):
            called.append(name)
            c.stop = True
        monkeypatch.setattr(c, "_api_step", mark if want == "_api_step" else (lambda: None))
        monkeypatch.setattr(c, "_innertube_step", mark if want == "_innertube_step" else (lambda: None))
        asyncio.run(c.run())
        assert called == [want]


def test_send_without_token_is_a_clear_error(monkeypatch):
    c, ev = _conn(monkeypatch)
    with pytest.raises(yt.SendRejected, match="YouTube send account not signed in"):
        asyncio.run(c.send("hi"))


class _R:
    def __init__(self, js, code=200): self.js, self.status_code, self.text = js, code, ""
    def json(self): return self.js
    def raise_for_status(self): pass


def test_send_uses_read_videos_chat_with_send_token_and_no_own_broadcast(monkeypatch):
    c, ev = _conn(monkeypatch, _youtube_token="tok", youtube_video_id="abcdefghijk")
    monkeypatch.setattr(c, "_h", lambda: {})
    calls = []

    def get(url, params=None, **k):
        calls.append((url.rsplit("/", 1)[-1], dict(params or {})))
        if url.endswith("/videos"):
            return _R({"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT1"}}]})
        raise AssertionError("own-broadcast lookup must not happen: " + url)

    def post(url, json=None, **k):
        calls.append(("post", json))
        return _R({"id": "m1"})
    monkeypatch.setattr(yt.requests, "get", get)
    monkeypatch.setattr(yt.requests, "post", post)
    assert asyncio.run(c.send("hi")) == "youtube:CHAT1:m1"
    assert calls[0] == ("videos", {"part": "liveStreamingDetails", "id": "abcdefghijk"})
    assert calls[1][1]["snippet"]["liveChatId"] == "CHAT1"


def test_send_not_live_is_a_clear_error(monkeypatch):
    c, ev = _conn(monkeypatch, _youtube_token="tok", youtube_video_id="abcdefghijk")
    monkeypatch.setattr(c, "_h", lambda: {})
    monkeypatch.setattr(yt.requests, "get", lambda *a, **k: _R({"items": [{"liveStreamingDetails": {}}]}))
    with pytest.raises(yt.SendRejected, match="no live chat"):
        asyncio.run(c.send("hi"))


def test_identity_sets_sending_as_and_clears_with_token(monkeypatch):
    c, ev = _conn(monkeypatch, _youtube_token="tok")
    monkeypatch.setattr(c, "_h", lambda: {})
    monkeypatch.setattr(yt.requests, "get", lambda *a, **k: _R({"items": [{"id": "UCbot", "snippet": {"title": "PinguinoB0t"}}]}))
    asyncio.run(c._identity())
    assert c.state["send_as"] == "PinguinoB0t" and c.send_id == "UCbot"
    assert c._mine() == {"read": [], "send": ["UCbot"], "send_names": ["pinguinob0t"]}
    monkeypatch.setattr(yt.secrets_store, "get", lambda k, *a: None)
    asyncio.run(c._identity())
    assert c.state["send_as"] == "" and c.send_id == ""


def test_reading_never_uses_the_signed_in_account(monkeypatch):
    c, ev = _conn(monkeypatch, _youtube_token="tok")
    monkeypatch.setattr(c, "_find_chat", lambda: (_ for _ in ()).throw(AssertionError("no")))
    with pytest.raises(LookupError):
        c._video_source()


def test_bot_lines_read_back_are_marked_self_and_bot():
    mine = {"read": [], "send": ["UCbot"], "send_names": ["pinguinob0t"]}
    r = {"id": "1", "authorExternalChannelId": "UCbot", "authorName": {"simpleText": "PinguinoB0t"}, "message": {"runs": [{"text": "yo"}]}, "timestampUsec": "1"}
    m = it.parse_item({"liveChatTextMessageRenderer": r}, "V", mine)
    assert m.is_self and m.is_bot
    r2 = dict(r, authorExternalChannelId="UCx", authorName={"simpleText": "Amy"})
    m2 = it.parse_item({"liveChatTextMessageRenderer": r2}, "V", mine)
    assert not m2.is_self and not m2.is_bot
