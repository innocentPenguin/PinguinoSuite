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
