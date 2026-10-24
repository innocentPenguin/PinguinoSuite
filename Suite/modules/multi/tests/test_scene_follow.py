"""scene_follow: loopback-only token, bad JSON, missing scene, engine errors retried, rapid changes, back-off (worker 42)."""
import asyncio

import pytest

import scene_follow as sf


def test_local_only_hosts():
    for ok in ("http://127.0.0.1:7777", "http://localhost:7777", "http://[::1]:7777/"):
        assert sf._local(ok)
    for bad in ("http://127.0.0.1.evil.com", "http://localhost.evil.com:7777", "https://127.0.0.1", "http://evil.com/http://127.0.0.1",
                "", "http://", "ftp://127.0.0.1", "http://127.0.0.1@evil.com"):
        assert not sf._local(bad), bad


class _R:
    def __init__(self, j, code=200):
        self.j, self.code = j, code

    def raise_for_status(self):
        if self.code >= 400:
            raise RuntimeError(f"HTTP {self.code}")

    def json(self):
        if isinstance(self.j, Exception):
            raise self.j
        return self.j


@pytest.mark.parametrize("payload,want", [({"scene": "Game"}, "Game"), ({"scene": None}, ""), ({}, ""), (["x"], ""), (None, ""),
                                          ({"scene": "x" * 500}, "x" * 200), ({"scene": 7}, "7")])
def test_fetch_shapes(monkeypatch, payload, want):
    monkeypatch.setattr(sf.requests, "get", lambda *a, **k: _R(payload))
    assert sf._fetch("http://127.0.0.1:1", "t") == want


def test_fetch_bad_json_and_http_errors_raise(monkeypatch):
    monkeypatch.setattr(sf.requests, "get", lambda *a, **k: _R(ValueError("bad json")))
    with pytest.raises(ValueError):
        sf._fetch("http://127.0.0.1:1", "")
    monkeypatch.setattr(sf.requests, "get", lambda *a, **k: _R({}, 401))
    with pytest.raises(RuntimeError):
        sf._fetch("http://127.0.0.1:1", "")


def _drive(monkeypatch, scenes, cfg=None, engine_fail=0, polls=None):
    """Run the loop over a scripted list of poll results (str scene or Exception); returns (engine calls, sleeps)."""
    cfg = cfg or {}
    it = iter(scenes)
    calls, sleeps = [], []

    class Eng:
        n = engine_fail

        def on_scene(self, s):
            if Eng.n > 0:
                Eng.n -= 1
                raise RuntimeError("alert config broken")
            calls.append(s)

    def fetch(url, token):
        v = next(it)
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(sf, "_fetch", fetch)
    monkeypatch.setattr(sf.config, "settings", lambda: cfg)
    monkeypatch.setattr(sf.alerts, "host_token", lambda *a: "tok")

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= (polls or len(scenes)):
            raise asyncio.CancelledError
    monkeypatch.setattr(sf.asyncio, "sleep", fake_sleep)
    try:
        asyncio.run(sf.run(Eng()))
    except asyncio.CancelledError:
        pass
    return calls, sleeps


def test_rapid_changes_and_repeats(monkeypatch):
    calls, _ = _drive(monkeypatch, ["A", "A", "B", "", "B", "A", "A"])
    assert calls == ["A", "B", "A"]                 # repeats and the empty "no scene" poll never re-fire


def test_link_down_then_up_and_backoff(monkeypatch):
    calls, sleeps = _drive(monkeypatch, [ConnectionError("down")] * 25 + ["Live"])
    assert calls == ["Live"] and sleeps[0] == 3 and max(sleeps) > 3 and max(sleeps) <= 30 and sleeps[-1] == 3


def test_engine_failure_is_retried_next_poll(monkeypatch):
    calls, _ = _drive(monkeypatch, ["A", "A", "A"], engine_fail=1)
    assert calls == ["A"]                           # first attempt raised, the retry worked, the third poll is a quiet repeat


def test_non_local_link_url_never_fetches(monkeypatch):
    def boom(*a):
        raise AssertionError("must not fetch")
    monkeypatch.setattr(sf, "_fetch", boom)
    monkeypatch.setattr(sf.config, "settings", lambda: {"link_url": "http://127.0.0.1.evil.com"})
    monkeypatch.setattr(sf.alerts, "host_token", lambda *a: "tok")
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
        raise asyncio.CancelledError
    monkeypatch.setattr(sf.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sf.run(object()))
    assert sleeps


def test_bad_config_values(monkeypatch):
    calls, _ = _drive(monkeypatch, ["A"], cfg={"link_url": None})          # None -> default loopback url
    assert calls == ["A"]
    calls, _ = _drive(monkeypatch, ["A"], cfg={"link_url": 12345})         # nonsense -> not loopback -> off
    assert calls == []


def test_no_token_never_polls_link(monkeypatch):
    fetched = []
    monkeypatch.setattr(sf, "_fetch", lambda url, token: fetched.append(token) or "A")
    monkeypatch.setattr(sf.config, "settings", lambda: {"link_url": "http://127.0.0.1:7777"})
    monkeypatch.setattr(sf.alerts, "host_token", lambda *a: "")
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError
    monkeypatch.setattr(sf.asyncio, "sleep", fake_sleep)
    try:
        asyncio.run(sf.run(object()))
    except asyncio.CancelledError:
        pass
    assert fetched == [] and sleeps == [30, 30, 30]
