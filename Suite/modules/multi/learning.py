"""Learning v1: bounded, explainable weight nudges from the streamer's own behaviour.

Evidence per rule (from the `events` log): answered +1, dismissed -1, missed -0.5, manual tier up +1 / down -1.
Each event decays with a half-life. A rule needs MIN_EVIDENCE events before it moves; the nudge is
STEP points per unit of net evidence, clamped to +/- CAP_FRAC of the rule's default weight (and CAP_ABS).
Nothing is ever auto-applied beyond that clamp, and reset() returns to defaults."""
import math
import time

from priority import rules as prio

HALF_LIFE_S = 14 * 86400
MIN_EVIDENCE = 5
STEP = 1.0
CAP_FRAC = 0.3
CAP_ABS = 12.0
TIER_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
SKIP = {"ignored"}


def _signal(ev):
    k = ev.get("kind")
    if k == "answered":
        return 1.0
    if k == "dismissed":
        return -1.0
    if k == "missed":
        return -0.5
    if k == "manual_tier":
        d = TIER_RANK.get(ev.get("to"), 0) - TIER_RANK.get(ev.get("from"), 0)
        return 1.0 if d > 0 else -1.0 if d < 0 else 0.0
    return 0.0


def compute(events, now=None, weights=None):
    """-> {rule: {"delta", "evidence", "net", "n"}} for every rule seen; delta is 0 until enough evidence."""
    now = now or time.time()
    weights = weights or prio.DEFAULT_RULES["weights"]
    acc = {}
    for ev in events:
        s = _signal(ev)
        if not s:
            continue
        w = 0.5 ** (max(0.0, now - ev.get("ts", now)) / HALF_LIFE_S)
        for r in ev.get("rules") or []:
            if r in SKIP or r not in weights:
                continue
            a = acc.setdefault(r, {"net": 0.0, "evidence": 0.0, "n": 0})
            a["net"] += s * w
            a["evidence"] += w
            a["n"] += 1
    out = {}
    for r, a in acc.items():
        cap = min(CAP_ABS, abs(weights[r]) * CAP_FRAC) if weights[r] else 0.0
        delta = 0.0
        if a["n"] >= MIN_EVIDENCE and a["evidence"] >= MIN_EVIDENCE * 0.5:
            delta = max(-cap, min(cap, STEP * a["net"]))
        out[r] = {"delta": round(delta, 1), "evidence": round(a["evidence"], 2), "net": round(a["net"], 2),
                  "n": a["n"], "cap": round(cap, 1)}
    return out


def refresh(store, now=None):
    """Recompute from the event log and persist the deltas the scorer reads (kv 'learned')."""
    if store.kv_get("learning_enabled", True) is False:
        store.kv_set("learned", {})
        return {}
    floor = store.kv_get("learning_floor", 0)
    rep = compute([e for e in store.events(5000) if e.get("ts", 0) >= floor], now)
    store.kv_set("learned", {r: v["delta"] for r, v in rep.items() if v["delta"]})
    return rep


def reset(store):
    store.kv_set("learned", {})
    store.kv_set("learning_floor", time.time())   # ignore older events from now on
