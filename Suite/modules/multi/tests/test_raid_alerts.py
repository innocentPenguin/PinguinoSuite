"""raid / raid_out alerts end to end in the engine: queued, text filled (raid_out names the TARGET), sound on, never silently eaten (worker 41)."""
import heapq

import alerts
import host_feed
from store import Store


def _eng(tmp_path):
    return alerts.Engine(Store(str(tmp_path / "a.db")), lambda e: None)


def _pop(eng):
    return heapq.heappop(eng.heap)[2]


def _flat(segs):
    return "".join(t for t, _ in segs)


def test_raid_in_and_out_queue_with_text_and_sound(tmp_path):
    eng = _eng(tmp_path)
    assert eng.submit({"type": "raid", "user": "Raider", "amount": 42, "platform": "twitch"}) == (True, "queued")
    assert eng.submit({"type": "raid_out", "user": "TargetChan", "amount": 17, "platform": "twitch"}) == (True, "queued")
    a, b = _pop(eng), _pop(eng)
    assert (a["type"], b["type"]) == ("raid", "raid_out")                        # incoming raid has the higher priority
    assert _flat(a["text"]) == "Raider is raiding with 42!" and _flat(b["text"]) == "Raiding TargetChan with 17 viewers!"
    for p in (a, b):
        assert p["sound"]["on"] is True and p["priority"] >= 8 and p["duration"] >= 7 and not p["test"]


def test_raid_not_eaten_by_dedupe_of_two_different_raids(tmp_path):
    eng = _eng(tmp_path)
    assert eng.submit({"type": "raid", "user": "A", "amount": 10})[0]
    assert eng.submit({"type": "raid", "user": "B", "amount": 10})[0]
    assert eng.submit({"type": "raid_out", "user": "T1", "amount": 10})[0] and eng.submit({"type": "raid_out", "user": "T2", "amount": 10})[0]
    assert len(eng.heap) == 4


def test_raid_defaults_enabled_and_survive_a_sparse_profile():
    c = alerts.sanitize_config({"profiles": {"Vertical": {"types": {"follow": {"enabled": False}}}}, "active": "Vertical"})
    for t in ("raid", "raid_out"):
        d = c["profiles"]["Vertical"]["types"][t]
        assert d["enabled"] and not d["silent"] and d["sound"]["enabled"] and d["min_amount"] == 0


def test_test_path_fills_amount_for_raid_out(tmp_path):
    ev = alerts.test_event("raid_out", user="Somebody")
    assert ev["amount"] == 5 and ev["test"]
    eng = _eng(tmp_path)
    assert eng.submit(ev)[0]
    assert _flat(_pop(eng)["text"]) == "Raiding Somebody with 5 viewers!"


def test_disabled_type_is_reported_not_silent(tmp_path):
    eng = _eng(tmp_path)
    cfg = eng.cfg
    cfg["profiles"][cfg["active"]]["types"]["raid_out"]["enabled"] = False
    eng.save(cfg)
    ok, why = eng.submit({"type": "raid_out", "user": "T", "amount": 3})
    assert not ok and why == "type disabled" and eng.log[0]["status"] == "skipped"


def test_host_feed_raid_out_names_the_target():
    m = host_feed.to_message({"seq": 5, "type": "raid_out", "user": "me", "target": "TargetChan", "amount": 12}, "me")
    assert m.event == "raid_out" and m.user == "targetchan" and m.display == "TargetChan" and m.text == "Raiding TargetChan with 12 viewers" and m.amount == 12
    m2 = host_feed.to_message({"seq": 6, "type": "raid_out", "user": "tgt", "amount": 4}, "me")            # no target field: user is taken as the target
    assert m2.user == "tgt"


# ---- one raid from two sources (Twitch EventSub + Host feed) --------------------------------------------------------------------------
import time as _time

from cards import CardManager
from models import ChatMessage
from pipeline import Pipeline


def _pl(tmp_path):
    st = Store(str(tmp_path / "p.db"))
    ev = []
    pl = Pipeline(st, CardManager(st, ev.append), ev.append)
    stored = []
    pl.on_event = stored.append
    return pl, stored


def _raid(mid, user="Raider", amount=40, ts=None):
    return ChatMessage(id=mid, platform="twitch", channel="me", user_id=user.lower(), user=user.lower(), display=user, text=f"{user} is raiding",
                       ts=ts or _time.time(), event="raid", amount=amount)


def test_host_only_and_eventsub_only(tmp_path):
    pl, got = _pl(tmp_path)
    assert pl.ingest(_raid("host:1")) is not None
    pl, got = _pl(tmp_path)
    assert pl.ingest(_raid("eventsub-abc")) is not None and len(got) == 1


def test_both_sources_either_order_alert_once(tmp_path):
    for first, second in (("eventsub-1", "host:7"), ("host:7", "eventsub-1")):
        d = tmp_path / first.replace(":", "_")
        d.mkdir()
        pl, got = _pl(d)
        assert pl.ingest(_raid(first, amount=40)) is not None
        assert pl.ingest(_raid(second, amount=41)) is None             # copy: dropped, first one (and its amount) wins
        assert len(got) == 1 and got[0].id == first


def test_replay_same_id_and_two_raiders_kept(tmp_path):
    pl, got = _pl(tmp_path)
    assert pl.ingest(_raid("host:1", "A")) is not None
    assert pl.ingest(_raid("host:1", "A")) is None                    # replay
    assert pl.ingest(_raid("host:2", "B")) is not None                # another raider in the same minute
    assert [m.user for m in got] == ["a", "b"]


def test_same_raider_again_after_the_window(tmp_path):
    clock = [1000.0]
    w = host_feed.RaidWindow(now=lambda: clock[0])
    assert not w.dup("R", "h:1")
    assert w.dup("r", "e:9")                                           # case-insensitive raider
    clock[0] += 61
    assert not w.dup("R", "h:2")                                       # a new raid by the same person later is a new raid
    assert w.dup("R", "h:3")


def test_engine_collapses_fire_and_eventsub_copy(tmp_path):
    eng = _eng(tmp_path)
    assert eng.submit({"id": "eventsub-1", "type": "raid", "user": "Raider", "amount": 40})[0]
    ok, why = eng.submit({"id": "host:7", "type": "raid", "user": "raider", "amount": 41})
    assert not ok and eng.log[0]["status"] == "duplicate" and len(eng.heap) == 1
    assert eng.submit({"id": "host:8", "type": "raid", "user": "Other", "amount": 5})[0] and len(eng.heap) == 2
    assert eng.submit({"id": "t1", "type": "raid", "user": "Raider", "amount": 40, "test": True})[0]      # tests are never swallowed


def test_engine_skipped_raid_is_not_recorded(tmp_path):
    eng = _eng(tmp_path)
    cfg = eng.cfg
    cfg["profiles"][cfg["active"]]["types"]["raid"]["min_amount"] = 50
    eng.save(cfg)
    assert not eng.submit({"id": "a", "type": "raid", "user": "Raider", "amount": 10})[0]
    cfg["profiles"][cfg["active"]]["types"]["raid"]["min_amount"] = 0
    eng.save(cfg)
    assert eng.submit({"id": "b", "type": "raid", "user": "Raider", "amount": 10})[0]                      # the blocked copy did not use up the raid


# ---- three sources: Host fire (raid:<id>), Host feed item (host:<seq>), Twitch EventSub (twitch:...) -------------------------------------
import itertools


def _three(tmp_path, order, kind="raid", who="Raider"):
    """feed item + EventSub go through the pipeline into the engine, fire goes straight to the engine; returns how many alerts queued"""
    eng = _eng(tmp_path)
    pl, _ = _pl(tmp_path)
    pl.on_event = lambda m: eng.submit({"id": m.id, "type": m.event, "user": m.user, "amount": m.amount, "platform": m.platform})
    src = {"fire": lambda: eng.submit({"id": f"{kind}:EV1", "type": kind, "user": who, "amount": 2, "platform": "twitch", "viewers": 2}),
           "feed": lambda: pl.ingest(_rd("host:12", kind, who, 3)),
           "eventsub": lambda: pl.ingest(_rd("twitch:abc", kind, who, 2))}
    for s in order:
        src[s]()
    return eng


def _rd(mid, kind, who, amount):
    m = _raid(mid, who, amount)
    m.event = kind
    return m


def test_three_sources_any_order_one_alert(tmp_path):
    for kind in ("raid", "raid_out"):
        for i, order in enumerate(itertools.permutations(["fire", "feed", "eventsub"])):
            if kind == "raid_out" and "eventsub" in order:
                continue                                                # raid_out never comes from EventSub
            d = tmp_path / f"{kind}{i}"
            d.mkdir()
            assert len(_three(d, order, kind).heap) == 1, (kind, order)
        for order in (("fire", "feed"), ("feed", "fire")):
            d = tmp_path / f"{kind}-{'-'.join(order)}"
            d.mkdir()
            assert len(_three(d, order, kind).heap) == 1


def test_three_sources_two_targets_or_raiders_kept(tmp_path):
    for kind in ("raid", "raid_out"):
        eng = _eng(tmp_path / kind) if (tmp_path / kind).mkdir() is None else None
        assert eng.submit({"id": f"{kind}:1", "type": kind, "user": "One"})[0]
        assert eng.submit({"id": f"{kind}:2", "type": kind, "user": "Two"})[0]
        assert not eng.submit({"id": f"{kind}:1", "type": kind, "user": "One"})[0]                    # replay of the same id
        assert len(eng.heap) == 2


def test_raid_and_raid_out_do_not_collide(tmp_path):
    eng = _eng(tmp_path)
    assert eng.submit({"id": "raid:1", "type": "raid", "user": "Same"})[0] and eng.submit({"id": "raid_out:1", "type": "raid_out", "user": "Same"})[0]


def test_every_default_profile_has_raids_on_with_chime():
    c = alerts.sanitize_config(None)
    assert c["active"] == "Penguin"
    for p in c["profiles"].values():
        for t in ("raid", "raid_out"):
            d = p["types"][t]
            assert d["enabled"] and not d["silent"] and d["sound"]["enabled"] and d["sound"]["url"] == ""      # empty url = the page's built-in chime
