"""The three chatter-sound rows (first / new_stream / returning): priority, migration from old keys, endpoints."""
import time

from fastapi.testclient import TestClient

import config
import ding
import server
from models import ChatMessage
from store import Store


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class Player:
    def __init__(self):
        self.played = []

    def play(self, path, vol):
        self.played.append((path, vol))


def _ding(tmp_path, monkeypatch, **cfg):
    snd = tmp_path / "d.wav"
    snd.write_bytes(b"x")
    s = dict(config.DEFAULTS, ding_platforms=["twitch", "youtube"], ding_sound=str(snd), **cfg)
    monkeypatch.setattr(config, "settings", lambda: s)
    d = ding.Ding(Store(tmp_path / "g.db"), player=Player(), clock=Clock(), master=lambda: True, start_worker=False)
    return d, s


def _m(user, platform="twitch", n=0, **kw):
    return ChatMessage(id=f"{platform}:c:{user}{n}", platform=platform, channel="c", user_id=user, user=user, display=user,
                       text="hi", ts=time.time(), **kw)


def test_rows_priority_sounds_volumes_and_recent_list(tmp_path, monkeypatch):
    d, s = _ding(tmp_path, monkeypatch, ding_returning=True, ding_returning_volume=50, ding_master_volume=50, ding_volume=80)
    ret = tmp_path / "ret.wav"
    ret.write_bytes(b"r")
    s["ding_returning_sound"] = str(ret)
    assert d.observe(_m("amy")) == "first"
    d.new_stream("test")                                          # next stream: amy is now known
    assert d.observe(_m("amy", n=1)) == "new_stream" and d.observe(_m("zed")) == "first"
    assert d.sound_for("new_stream") == s["ding_sound"] and d.sound_for("returning") == str(ret)
    assert d.volume_for("first") == 45 and d.volume_for("new_stream") == 40 and d.volume_for("returning") == 25
    assert [x["kind"] for x in d.recent] == ["first", "new_stream", "first"]
    assert d.recent[0]["notify"] is True and d.recent[1]["notify"] is False
    s["ding_rows"] = {"new_stream": {"on": False}}
    d.new_stream("again")
    assert d.observe(_m("amy", n=2)) is False                    # new_stream row off: silent, never a lower row
    s["ding_rows"] = {}
    d.new_stream("third")
    assert d.observe(_m("amy", n=3)) == "new_stream"
    s["ding_scope"] = "ever"
    s["ding_rows"] = {"new_stream": {"on": False}}
    assert d.observe(_m("amy", n=4)) is False                    # 'ever' + row off: known people stay quiet


def test_exactly_one_row_fires_and_flagged_returning(tmp_path, monkeypatch):
    d, s = _ding(tmp_path, monkeypatch)
    assert d.observe(_m("amy", flags=["returning"])) == "first"             # not counted yet: row 1 wins over the flag
    assert d.q.qsize() == 1
    assert d.observe(_m("amy", n=1)) is False                                # counted, no flag: silent
    assert d.observe(_m("amy", n=2, flags=["returning"])) == "returning"     # counted + flag: row 3
    assert d.observe(_m("tw", first_time=True)) == "first"
    assert d.q.qsize() == 3
    d.new_stream("x")
    assert d.observe(_m("amy", n=3, flags=["returning"])) == "new_stream"   # known + flag, not yet counted this stream: row 2 only
    assert d.observe(_m("tw", n=1, first_time=True)) == "first"             # twitch first-message flag beats 'known'
    assert d.q.qsize() == 5
    s["ding_rows"] = {"returning": {"on": False, "notify": True}}
    assert d.observe(_m("amy", n=4, flags=["returning"])) is False
    assert d.recent[-1]["kind"] == "returning" and d.recent[-1]["notify"] is True    # off but notify: shown, silent


def test_rows_derive_from_old_keys_without_reset(tmp_path, monkeypatch):
    d, s = _ding(tmp_path, monkeypatch, ding_volume=24, ding_returning=True, ding_returning_volume=50, ding_first_ever=False, ding_first_sound="")
    s["ding_returning_sound"] = str(tmp_path / "today.mp3")
    harp = tmp_path / "harp.wav"
    monkeypatch.setattr(config, "HARP", harp)
    r = config.ding_rows(s)
    assert r["first"] == {"on": True, "sound": s["ding_sound"], "volume": 90, "notify": True}      # no harp file: falls back to ding_sound
    harp.write_bytes(b"h")
    r = config.ding_rows(s)
    assert r["first"] == {"on": True, "sound": str(harp), "volume": 90, "notify": True}            # first_ever / first_sound ignored
    assert r["new_stream"] == {"on": True, "sound": s["ding_sound"], "volume": 24, "notify": False}
    assert r["returning"] == {"on": True, "sound": s["ding_returning_sound"], "volume": 50, "notify": False}
    s["ding_returning"] = False
    s["ding_platforms"] = []
    assert config.ding_rows(s)["new_stream"]["on"] is True and config.ding_rows(s)["first"]["on"] is True
    s["ding_rows"] = {"first": {"volume": 7, "bogus": 1}, "new_stream": "junk"}
    r = config.ding_rows(s)
    assert r["first"]["volume"] == 7 and "bogus" not in r["first"] and r["new_stream"]["volume"] == 24
    info = d.info()
    assert set(info["rows"]) == {"first", "new_stream", "returning"} and info["gap_h"] == 6 and info["rows"]["first"]["sound_exists"]
    assert info["volume"] == 24 and "returning_sound" in info and "platforms" in info          # old keys unchanged


def _client(monkeypatch):
    store = {"v": dict(config.DEFAULTS)}
    monkeypatch.setattr(config, "settings", lambda: dict(store["v"]))
    monkeypatch.setattr(config, "save_settings", lambda p: store["v"].update(p) or p)
    monkeypatch.delenv("PINGUINO_API_TOKEN", raising=False)
    h = {"origin": "http://127.0.0.1:8766"}
    return TestClient(server.app, base_url="http://127.0.0.1:8766", raise_server_exceptions=False), store, h


def test_settings_endpoint_partial_patches_write_through_and_validation(tmp_path, monkeypatch):
    c, st, h = _client(monkeypatch)
    snd = tmp_path / "a.wav"
    snd.write_bytes(b"x")
    r = c.post("/api/ding/settings", json={"rows": {"first": {"volume": 150, "notify": False}}, "gap_h": 3}, headers=h)
    assert r.status_code == 200 and r.json()["rows"]["first"]["volume"] == 100 and r.json()["rows"]["first"]["notify"] is False
    assert st["v"]["ding_session_gap_h"] == 3 and r.json()["gap_h"] == 3
    assert st["v"]["ding_rows"] == {"first": {"volume": 100, "notify": False}}               # only patched fields saved
    r = c.post("/api/ding/settings", json={"rows": {"returning": {"sound": str(snd), "on": False}}}, headers=h)
    assert r.json()["rows"]["returning"]["sound"] == str(snd) and r.json()["rows"]["returning"]["on"] is False
    assert r.json()["rows"]["first"]["volume"] == 100                                        # other rows untouched
    c.post("/api/ding/settings", json={"rows": {"new_stream": {"on": False}}}, headers=h)
    r = c.post("/api/ding/settings", json={"volume": 20, "returning": True}, headers=h)     # old keys write through to saved fields
    assert r.json()["rows"]["first"]["volume"] == 20 and r.json()["rows"]["new_stream"]["on"] is True and r.json()["volume"] == 20
    for bad in ({"rows": []}, {"rows": {"nope": {}}}, {"rows": {"first": 5}}, {"rows": {"first": {"volume": "x"}}},
                {"rows": {"first": {"sound": str(tmp_path / "missing.mp3")}}}, {"gap_h": "x"}, {"gap_h": [1]}, [], "x"):
        assert c.post("/api/ding/settings", json=bad, headers=h).status_code == 400, bad
    hj = dict(h, **{"content-type": "application/json"})
    for raw in (b'{"gap_h": NaN}', b'{"gap_h": Infinity}', b'{"rows": {"first": {"volume": Infinity}}}', b"{"):
        assert c.post("/api/ding/settings", content=raw, headers=hj).status_code == 400, raw


def test_test_endpoint_kinds_and_newchatter_kinds(monkeypatch):
    c, st, h = _client(monkeypatch)
    sent = []
    monkeypatch.setattr(server.pipeline.ding, "test", lambda k: sent.append(k))
    for given, want in (("first", "first"), ("new_stream", "new_stream"), ("returning", "returning"), ("new", "first")):
        assert c.post("/api/ding/test", json={"kind": given}, headers=h).status_code == 200
        assert sent[-1] == want
    assert c.post("/api/ding/test", headers=h).status_code == 200 and sent[-1] == "first"
    for bad in ({"kind": "bogus"}, {"kind": []}, {"kind": 5}, [1]):
        assert c.post("/api/ding/test", json=bad, headers=h).status_code == 400, bad
    server.pipeline.ding.recent.append({"ts": time.time() + 1, "platform": "twitch", "user": "u", "display": "u", "kind": "new_stream", "notify": False})
    try:
        assert any(x["kind"] == "new_stream" for x in c.get("/api/newchatters?since=0").json()["items"])
    finally:
        server.pipeline.ding.recent.pop()


def test_sounds_files_lists_only_audio(monkeypatch, tmp_path):
    c, st, h = _client(monkeypatch)
    r = c.get("/api/sounds/files", headers=h)
    assert r.status_code == 200 and r.json()["dir"].endswith("Data/sounds")
    names = [f["name"] for f in r.json()["files"]]
    assert names == sorted(names, key=str.lower) and all(n.lower().endswith((".mp3", ".wav")) for n in names)


def test_heartbeat_line_reports_pops_and_source(tmp_path, monkeypatch):
    import pipeline as pl
    p = pl.Pipeline.__new__(pl.Pipeline)
    import pop as pop_mod
    p.pop = pop_mod.Pop(player=object(), start_worker=False)
    class D: stats = {"played": 3}
    p.ding, p.last_in = D(), 0.0
    line = p.heartbeat_line(True)
    assert line.startswith("pops: 0 played, last at never, source ") and "dings 3 played" in line
    assert "source down" in p.heartbeat_line(False)


def test_is_bot_covers_every_bot_name_and_flag():
    import ding

    class M:
        def __init__(self, user, is_bot=False): self.user, self.is_bot = user, is_bot
    st = {"bot_accounts": ["somebot2"]}
    for n in ("PinguinoB0t", "ChattyPinguino", "PinguinoHelper", "SoundAlerts", "sery_bot", "StreamElements", "Nightbot", "Moobot", "xyz_b0t", "somebot2"):
        assert ding.is_bot(M(n), st), n
    assert ding.is_bot(M("anyone", True), st)
    assert not ding.is_bot(M("viewer1"), st)


def test_ding_and_pop_skip_bots(monkeypatch):
    import ding, pop, config
    from models import ChatMessage
    st = dict(config.settings(), ding_platforms=["twitch"], pop_platforms=["twitch"])
    monkeypatch.setattr(config, "settings", lambda: st)
    m = _m("ChattyPinguino")
    p = pop.Pop(player=object(), start_worker=False)
    assert p.observe(m) is False
    assert p.q.qsize() == 0
