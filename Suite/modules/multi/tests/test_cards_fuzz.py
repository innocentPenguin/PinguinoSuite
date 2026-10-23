"""Fuzz for the intermittent /api/cards 500 (worker 42): odd stored cards, NaN scores, concurrent mutation."""
import json
import threading
from types import SimpleNamespace as NS

import cards as cm


class FakeStore:
    def __init__(self, rows):
        self.rows, self.events, self.saved = rows, [], []

    def load_cards(self):
        return self.rows

    def save_card(self, c):
        self.saved.append(c["id"])

    def log_event(self, *a, **k):
        self.events.append(a)


ODD = [
    {"id": "c:1"},                                                   # nothing but an id
    {"id": "c:2", "score": None, "created": None, "state": "open", "reasons": None},
    {"id": "c:3", "score": float("nan"), "created": float("inf"), "updated": "x", "state": "missed"},
    {"id": "c:4", "score": "55", "state": "answered", "answered_at": None, "faded": 0},
    {"id": "c:5", "state": "weird", "user": None, "user_id": 12345, "text": None, "reasons": [1, {"rule": "r"}, {"nope": 1}]},
    {"id": "c:6", "state": "snoozed", "snooze_until": "later", "context": "str"},
    {"id": "c:7", "score": 10 ** 400 if False else 1e308, "state": "open"},
    {"no_id": True}, None, "junk", 42,
]


def test_view_recap_tick_survive_odd_stored_cards_and_are_json_safe():
    m = cm.CardManager(FakeStore([dict(c) if isinstance(c, dict) else c for c in ODD]), clock=lambda: 1000.0)
    assert len(m.cards) == 7
    v = m.view()
    json.dumps(v, allow_nan=False)                                   # FastAPI uses allow_nan=False -> a NaN is a 500
    json.dumps(m.recap(), allow_nan=False)
    m.tick()
    json.dumps(m.view(), allow_nan=False)
    assert m.cards["c:5"]["state"] == "open" and m.cards["c:5"]["reasons"] == [{"rule": "r"}]
    for cid in m.cards:                                              # every transition works on repaired cards
        m.answer(cid); m.reopen(cid); m.dismiss(cid); m.snooze(cid); m.set_tier(cid, "high"); m.mark({"id": cid[2:], "platform": "t", "user": "u", "user_id": "1", "text": "t", "ts": 1})
    json.dumps(m.view(), allow_nan=False)


def test_new_cards_with_nan_or_none_scores():
    m = cm.CardManager(FakeStore([]), clock=lambda: 5.0)
    msg = NS(id="a", platform="twitch", channel="c", user="u", user_id="1", display="U", text="hi", ts=1.0)
    for sc in (float("nan"), None, float("inf"), "x"):
        msg.id = f"a{sc}"
        c = m.maybe_create(msg, NS(tier="high", score=sc, reasons=[]))
        assert c and c["score"] == 0.0
    json.dumps(m.view(), allow_nan=False)


def test_view_while_cards_are_added_mid_iteration():
    """Deterministic stand-in for the thread race: reading a card's fields adds another card to the manager
    (what the pipeline does from the event loop while /api/cards iterates in a worker thread)."""
    m = cm.CardManager(FakeStore([]), clock=lambda: 5.0)

    class Adding(dict):
        n = 0

        def __getitem__(self, k):
            if k == "state" and Adding.n < 50:
                Adding.n += 1
                m.cards[f"c:new{Adding.n}"] = cm.normalize({"id": f"c:new{Adding.n}", "state": "open"})
            return dict.__getitem__(self, k)
    for i in range(5):
        m.cards[f"c:{i}"] = Adding(cm.normalize({"id": f"c:{i}", "state": "open", "score": i}))
    m.view(); m.recap(); m.tick(); m._enforce_cap()
    assert len(m.cards) > 5
