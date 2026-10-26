"""TikTok connector vs the real TikTokLive 7.x event classes (built in memory) and a fake client. No network, never connects to TikTok."""
import asyncio

import pytest

import config
import ding
from connectors import tiktok as tk
from connectors import tiktok_live as tl
from models import ChatMessage

tev = pytest.importorskip("TikTokLive.events")
from TikTokLive.proto import CommonMessageData, ExtendedGift, ExtendedUser   # noqa: E402

U = ExtendedUser(id=4242, display_id="Amy_T", nickname="Amy")


def _fire(c, evs):
    async def go():
        for e in evs:
            c.emit(e.get_type(), e)
        await asyncio.sleep(0.05)
    asyncio.run(go())


def test_real_event_classes_map_to_suite_objects():
    from TikTokLive import TikTokLiveClient
    c, got, st = TikTokLiveClient(unique_id="@host"), [], {}
    names = tl.attach(c, tev, "host", got.append, st)
    assert {"CommentEvent", "GiftEvent", "FollowEvent", "ShareEvent", "LikeEvent"} <= set(names)
    rose = ExtendedGift(name="Rose", diamond_count=1)
    tt = lambda **k: ExtendedGift(name="Galaxy", diamond_count=100, type=1, **k)
    _fire(c, [tev.CommentEvent(content="hello tiktok", user=U, common=CommonMessageData(msg_id=777)),
              tev.GiftEvent(user=U, gift=rose, repeat_count=1, repeat_end=1),
              tev.GiftEvent(user=U, gift=tt(), repeat_count=2, repeat_end=0, group_id=9),      # mid-streak frame: ignored
              tev.GiftEvent(user=U, gift=tt(), repeat_count=5, repeat_end=1, group_id=9),      # streak end: counted once
              tev.FollowEvent(user=U), tev.ShareEvent(user=U), tev.LikeEvent(user=U, count=3), tev.JoinEvent(user=U)])
    chat, gift1, gift2, follow, share = got
    assert (chat.id, chat.user_id, chat.user, chat.display, chat.text, chat.event) == ("tiktok:host:777", "4242", "amy_t", "Amy", "hello tiktok", "")
    assert chat.platform == "tiktok" and chat.channel == "host" and not chat.is_self
    assert (gift1.event, gift1.amount, gift1.meta["gift_name"], gift1.meta["currency"]) == ("cheer", 1, "Rose", "coins")
    assert (gift2.event, gift2.amount, gift2.meta["count"], gift2.id) == ("cheer", 500, 5, "tiktok:host:gift:9")
    assert follow.event == "follow" and follow.user_id == "4242" and share.event == "share"
    assert st["likes"] == 3                                                  # likes only counted; joins ignored


def test_malformed_events_never_raise():
    from TikTokLive import TikTokLiveClient
    c, got = TikTokLiveClient(unique_id="@host"), []
    tl.attach(c, tev, "host", got.append, {})
    _fire(c, [tev.CommentEvent(), tev.CommentEvent(content="   ", user=U), tev.GiftEvent(), tev.FollowEvent(), tev.LikeEvent(), tev.ShareEvent()])
    assert got == []
    assert tl.map_event("comment", object(), "h") is None and tl.map_event("gift", None, "h") is None and tl.map_event("bogus", object(), "h") is None
    assert tl.map_event("comment", tev.CommentEvent(content="x" * 900, user=U), "host").text == "x" * 500
    assert tl.map_event("comment", tev.CommentEvent(content="hi", user=ExtendedUser(id=1, display_id="host")), "host").is_self


def test_backoff_and_classify():
    assert [tk.backoff(n) for n in range(7)] == [10, 20, 40, 80, 160, 300, 300]
    assert tk.backoff(0, True) == 30 and tk.backoff(100, True) == 60
    from TikTokLive.client.errors import UserNotFoundError, UserOfflineError
    assert tk.classify(UserOfflineError())[0] == "offline" and tk.classify(UserNotFoundError("x"))[0] == "notfound"
    assert tk.classify(RuntimeError("[RATE_LIMIT] slow"))[0] == "ratelimit" and tk.classify(OSError("boom"))[0] == "error"


# ---- connector loop with a fake client -------------------------------------------------------------------------
class Inbox:
    def __init__(self): self.items = []
    def put(self, m): self.items.append(m)


class FakeClient:
    script = []                                         # per connect(): exception to raise, or a callable(client) run while "connected"

    def __init__(self):
        self.listeners = {}
        self.closed = 0

    def add_listener(self, cls, fn):
        self.listeners[cls.__name__] = fn

    async def connect(self):
        step = FakeClient.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        await step(self)

    async def disconnect(self):
        self.closed += 1


def _conn(monkeypatch, **cfg):
    s = dict(config.DEFAULTS, **{"tiktok_enabled": True, "tiktok_user": "@Host", **cfg})
    monkeypatch.setattr(tk.config, "settings", lambda: s)
    monkeypatch.setattr(tk, "make_client", lambda user, st: FakeClient())
    monkeypatch.setattr(tk.secrets_store, "get", lambda k, *a: None)
    ev = []
    return tk.TikTok(Inbox(), ev.append), ev


def _run(c, cycles):
    sleeps = []

    async def fake(sec):
        sleeps.append(sec)
        if len(sleeps) >= cycles:
            c.stop = True
    real = asyncio.sleep
    asyncio.sleep = fake
    try:
        asyncio.run(c.run())
    finally:
        asyncio.sleep = real
    return sleeps


def test_not_set_disabled_and_offline_states(monkeypatch):
    c, _ = _conn(monkeypatch, tiktok_user="")
    _run(c, 1)
    assert c.state["status"] == "needs_setup" and "Set the TikTok @handle" in c.state["detail"]
    c, _ = _conn(monkeypatch, tiktok_enabled=False)
    _run(c, 1)
    assert c.state["status"] == "disabled"
    from TikTokLive.client.errors import UserOfflineError
    c, _ = _conn(monkeypatch)
    FakeClient.script = [UserOfflineError(), UserOfflineError(), UserOfflineError()]
    sl = _run(c, 3)
    assert c.state["status"] == "waiting" and "not live yet" in c.state["detail"] and sl == [30, 35, 40] and c.state["reconnects"] == 0


def test_connect_events_flow_then_end_and_errors_back_off(monkeypatch):
    c, ev = _conn(monkeypatch)

    async def live(cl):
        await cl.listeners["ConnectEvent"](tev.ConnectEvent(unique_id="host", room_id=1))
        assert c.state["status"] == "connected" and c.state["detail"] == "@Host (unofficial)"
        await cl.listeners["CommentEvent"](tev.CommentEvent(content="yo", user=U))
        await cl.listeners["RoomUserSeqEvent"](tev.RoomUserSeqEvent(total=37))
        await cl.listeners["LiveEndEvent"](tev.LiveEndEvent())
    FakeClient.script = [live, RuntimeError("[RATE_LIMIT] sign"), OSError("net"), OSError("net")]
    sl = _run(c, 4)
    assert [m.text for m in c.inbox.items] == ["yo"] and c.state["viewers"] == 37
    assert sl[0] == 30 and sl[1:] == [10, 20, 40]                          # live ended -> waiting 30 s; then errors double
    assert c.state["status"] == "reconnecting" and c.state["reconnects"] == 3
    c, ev = _conn(monkeypatch)
    async def drop(cl):
        return None
    FakeClient.script = [drop]                       # plain disconnect: reconnect soon, not tight
    sl = _run(c, 1)
    assert c.state["status"] == "reconnecting" and sl == [10]


def test_tiktok_joins_dings_and_pops_automatically():
    st = dict(config.DEFAULTS, tiktok_enabled=True, ding_platforms=["twitch"], pop_platforms=[])
    assert config.platforms_for(st, "ding_platforms") == ["twitch", "tiktok"] and config.platforms_for(st, "pop_platforms") == ["tiktok"]
    assert config.platforms_for(dict(st, tiktok_enabled=False), "ding_platforms") == ["twitch"]
    assert config.platforms_for(dict(st, ding_platforms=["tiktok"]), "ding_platforms") == ["tiktok"]


def test_tiktok_chat_reaches_first_chatter_ding(tmp_path, monkeypatch):
    from store import Store
    snd = tmp_path / "d.wav"
    snd.write_bytes(b"x")
    st = dict(config.DEFAULTS, tiktok_enabled=True, ding_platforms=[], ding_sound=str(snd))
    monkeypatch.setattr(config, "settings", lambda: st)

    class Player:
        def play(self, p, v): pass
    d = ding.Ding(Store(tmp_path / "g.db"), player=Player(), clock=lambda: 1e6, master=lambda: True, start_worker=False)
    m = tl.map_event("comment", tev.CommentEvent(content="hi", user=U), "host")
    assert d.observe(m) == "first"
    st["tiktok_enabled"] = False
    assert d.observe(tl.map_event("comment", tev.CommentEvent(content="hi", user=ExtendedUser(id=9, display_id="zed")), "host")) is False


def test_non_json_answer_backs_off_from_60s_and_logs_body_once(monkeypatch):
    import json
    try:
        json.loads("<html>Access denied token=SECRET</html>")
    except json.JSONDecodeError as je:
        err = je
    assert tk.classify(err)[0] == "badjson" and tk.body_of(err).startswith("<html>Access denied")
    c, ev = _conn(monkeypatch)
    FakeClient.script = [err, err, err, err, err]
    sl = _run(c, 5)
    assert sl == [60, 120, 240, 480, 600] and c.state["status"] == "reconnecting" and c.state["reconnects"] == 5
    assert "not data" in c.state["detail"] and "<html>" not in c.state["detail"]       # body shown only the first time
    assert "tiktok_sign_key" in c.state["detail"]
    assert tk.backoff_badjson(0) == 60 and tk.backoff_badjson(20) == 600


def test_comment_badges_from_user_identity():
    from TikTokLive.proto import UserIdentity
    sub = tev.CommentEvent(content="hi", user=U, user_identity=UserIdentity(is_subscriber_of_anchor=True, is_moderator_of_anchor=True))
    assert tl.map_event("comment", sub, "host").badges == ["subscriber", "moderator"]
    assert tl.map_event("comment", tev.CommentEvent(content="hi", user=U), "host").badges == []
