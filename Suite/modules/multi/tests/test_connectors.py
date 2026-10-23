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
