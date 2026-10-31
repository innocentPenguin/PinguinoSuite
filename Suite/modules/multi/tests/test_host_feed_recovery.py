"""Host activity feed outage tracking: one warning, reminders, one recovery line, cursor kept, missed/replayed counters (worker 41). Fake Host, no network."""
import asyncio
import queue

import pytest

import host_feed as hf


@pytest.fixture
def logs(monkeypatch):
    out = []
    monkeypatch.setattr(hf.console_log, "info", lambda s, m, **k: out.append(("info", m)))
    monkeypatch.setattr(hf.console_log, "warn", lambda s, m, **k: out.append(("warn", m)))
    return out


def mk():
    clock = [1000.0]
    return hf.FeedWatch(now=lambda: clock[0]), clock


def items(*seqs):
    return [{"seq": n, "type": "follow"} for n in seqs]


def test_one_warning_then_reminder_every_5_min_then_recovery(logs):
    w, clock = mk()
    for _ in range(5):
        w.failed(TimeoutError())
        clock[0] += 10
    assert [m for lv, m in logs if lv == "warn"] == [logs[0][1]] and "TimeoutError" in logs[0][1]      # one warning, not one per poll
    assert w.snapshot()["feed_down_s"] == 50
    clock[0] += 260
    w.failed(TimeoutError())
    assert len([1 for lv, _ in logs if lv == "warn"]) == 2 and "still down after 310 s" in logs[-1][1]
    clock[0] += 5
    w.polled(items(11, 12, 13), 10)
    assert logs[-1][0] == "info" and "back after 315 s" in logs[-1][1] and "3 event(s) replayed" in logs[-1][1] and "lost" not in logs[-1][1]
    s = w.snapshot()
    assert s["feed_down_s"] == 0 and s["feed_last_down_s"] == 315 and s["feed_replayed"] == 3 and s["feed_missed"] == 0 and s["feed_outages"] == 1


def test_gap_in_ids_is_counted_as_missed(logs):
    w, clock = mk()
    w.failed(OSError())
    clock[0] += 70
    w.polled(items(40, 41), 10)                            # ids 11..39 were gone from the Host
    assert w.snapshot()["feed_missed"] == 29 and "29 more were no longer on the Host" in logs[-1][1]


def test_no_events_during_outage_and_normal_polls_are_silent(logs):
    w, clock = mk()
    w.polled(items(1), 0)
    w.polled([], 1)
    assert logs == []                                      # no outage: nothing to say
    w.failed(OSError())
    clock[0] += 5
    w.polled([], 1)
    assert "back after 5 s: 0 event(s) replayed" in logs[-1][1]
    w.failed(OSError())
    assert w.snapshot()["feed_outages"] == 2


def test_big_backlog_pages_count_while_recovering(logs):
    w, clock = mk()
    w.failed(OSError())
    clock[0] += 3
    w.polled(items(*range(11, 111)), 10)                   # a full page: more pending
    assert "(more pending)" in logs[-1][1]
    w.polled(items(*range(111, 131)), 110)
    assert w.snapshot()["feed_replayed"] == 120 and len([1 for lv, _ in logs if lv == "info"]) == 1


def test_run_keeps_the_cursor_across_a_failure(monkeypatch, logs):
    calls = []
    plan = iter([{"seq": 5}, {"items": [{"seq": 6, "type": "follow", "user": "a"}]}, TimeoutError(), TimeoutError(),
                 {"items": [{"seq": 7, "type": "follow", "user": "b"}, {"seq": 8, "type": "follow", "user": "c"}]}])

    def get(path):
        calls.append(path)
        r = next(plan)
        if isinstance(r, Exception):
            raise r
        return r

    async def nosleep(_):
        if len(calls) >= 5:
            raise asyncio.CancelledError
    monkeypatch.setattr(hf, "_get", get)
    monkeypatch.setattr(hf.asyncio, "sleep", nosleep)
    monkeypatch.setattr(hf.config, "settings", lambda: {"channel": "c", "host_feed_enabled": True})
    monkeypatch.setattr(hf, "WATCH", hf.FeedWatch())
    inbox = queue.Queue()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(hf.run(inbox, lambda: True))
    assert calls[2] == "/api/activity?since=6&limit=100" and calls[3] == "/api/activity?since=6&limit=100"      # the cursor survived the outage
    assert calls[4] == "/api/activity?since=6&limit=100"
    got = []
    while not inbox.empty():
        got.append(inbox.get().id)
    assert got == ["host:6", "host:7", "host:8"]
    assert hf.WATCH.snapshot()["feed_replayed"] == 2 and len([1 for lv, _ in logs if lv == "warn"]) == 1


def test_status_carries_the_feed_counters():
    assert {"up", "feed_down_s", "feed_last_down_s", "feed_outages", "feed_replayed", "feed_missed"} <= set(hf.status())


def test_old_replayed_events_are_marked_stale_recent_ones_are_not():
    now = 10_000.0
    old = hf.to_message({"seq": 1, "type": "follow", "user": "a", "ts": now - 601}, "c")
    new = hf.to_message({"seq": 2, "type": "follow", "user": "b", "ts": now - 30}, "c")
    raid = hf.to_message({"seq": 3, "type": "raid_out", "user": "t", "ts": now - 3600, "amount": 5}, "c")
    for m, item_ts in ((old, now - 601), (new, now - 30), (raid, now - 3600)):
        hf.mark_stale(m, {"ts": item_ts}, now=lambda: now)
    assert old.meta["stale"] is True and raid.meta["stale"] is True and "stale" not in (new.meta or {})
    assert hf.mark_stale(None, {"ts": 1}) is None


def test_stale_event_is_stored_but_gets_no_alert(monkeypatch):
    import server
    fired, goals = [], []
    monkeypatch.setattr(server.alert_engine, "submit", lambda ev: fired.append(ev))
    monkeypatch.setattr(server.goal, "observe", lambda *a: goals.append(a))
    monkeypatch.setattr(server.hub, "loop", type("L", (), {"call_soon_threadsafe": staticmethod(lambda f, *a: f(*a))})())
    import time
    m = hf.to_message({"seq": 9, "type": "follow", "user": "late", "ts": time.time() - 4000}, "c")
    hf.mark_stale(m, {"ts": time.time() - 4000})
    server._alert_from_message(m)
    assert fired == [] and len(goals) == 1                 # counters still see it, the alert engine does not
    fresh = hf.to_message({"seq": 10, "type": "follow", "user": "now", "ts": time.time()}, "c")
    server._alert_from_message(fresh)
    assert len(fired) == 1


def test_follow_overlay_skips_stale_events():
    import pathlib
    html = (pathlib.Path(__file__).resolve().parent.parent / "static" / "obs.html").read_text(encoding="utf-8")
    assert "m.meta.stale" in html


def test_disabled_tiktok_is_silent_everywhere_i_own(monkeypatch):
    """TikTok is off by default: no viewer-count warning, no outage/chat-in line or per-platform counter mentions it."""
    import asyncio
    import viewers
    from connectors.tiktok import TikTok
    out = []
    monkeypatch.setattr(viewers.console_log, "warn", lambda *a, **k: out.append(a))
    monkeypatch.setattr(hf.console_log, "warn", lambda *a, **k: out.append(a))
    monkeypatch.setattr(hf.console_log, "info", lambda *a, **k: out.append(a))
    monkeypatch.setattr(hf.config, "settings", lambda: {"host_chat_in": True, "bot_accounts": [], "tiktok_enabled": False})
    tt = TikTok(None, lambda e: None)
    assert tt.state.get("status") != "connected" and viewers._tiktok(tt) is None
    c = hf.ChatIn(post=lambda b: 200, now=lambda: 1000.0)
    c.thread = object()
    c.beat_at = 0.0
    c.stats["sent"] = 1
    c._beat(force=True)                                    # a heartbeat with only YouTube traffic
    assert out and all("tiktok" not in str(x).lower() and "tt " not in str(x).lower() for x in out)
    assert not any("tiktok" in k or k == "tt" for k in hf.status()) and not any("tiktok" in k for k in c.snapshot())
