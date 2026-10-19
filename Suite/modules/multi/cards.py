"""Priority cards: state machine + reply tracking.

States: open -> answered (fades after answered_fade_s) | missed (after missed_after_s, recoverable)
        | dismissed | snoozed (returns to open when the snooze ends). missed/answered/dismissed can be reopened.
The clock is injectable so timers are testable. Every change goes through _emit so the UI sees one event stream.
"""
import time

import config

MIN_TIER_FOR_CARD = ("medium", "high")


class CardManager:
    def __init__(self, store, emit=lambda ev: None, clock=time.time):
        self.store, self.emit, self.clock = store, emit, clock
        self.cards = {c["id"]: c for c in store.load_cards()}

    # creation -------------------------------------------------------
    def maybe_create(self, msg, decision, context=None):
        """Create a card for a message whose tier qualifies. Returns the card or None."""
        if decision.tier not in MIN_TIER_FOR_CARD:
            return None
        cid = "c:" + msg.id
        if cid in self.cards:
            return None
        now = self.clock()
        c = {
            "id": cid, "message_id": msg.id, "platform": msg.platform, "channel": msg.channel,
            "user": msg.user, "user_id": msg.user_id, "display": msg.display, "text": msg.text,
            "msg_ts": msg.ts, "score": decision.score, "tier": decision.tier, "reasons": decision.reasons,
            "context": context or [], "state": "open", "created": now, "updated": now,
            "answered_at": None, "answered_via": None, "snooze_until": None, "faded": False,
        }
        self.cards[cid] = c
        self._save(c, "card.new")
        self._enforce_cap()
        return c

    def mark(self, m):
        """The streamer marked any stored message (dict) to answer: make/reopen a normal medium card for it."""
        cid = "c:" + m["id"]
        c = self.cards.get(cid)
        if c:
            if not any(r["rule"] == "marked" for r in c["reasons"]):
                c["reasons"] = [{"rule": "marked", "points": 0, "detail": "you marked this to answer"}] + c["reasons"]
            c["score"] = max(c["score"], 60.0)
            if c["state"] != "open":
                self.set_state(cid, "open", reason="marked to answer")
            else:
                self._save(c, "card.update")
            return self.cards[cid]
        now = self.clock()
        c = {"id": cid, "message_id": m["id"], "platform": m["platform"], "channel": m.get("channel", ""), "user": m["user"],
             "user_id": m["user_id"], "display": m.get("display") or m["user"], "text": m["text"], "msg_ts": m["ts"], "score": 60.0,
             "tier": "medium", "reasons": [{"rule": "marked", "points": 60, "detail": "you marked this to answer"}], "context": [],
             "state": "open", "created": now, "updated": now, "answered_at": None, "answered_via": None, "snooze_until": None, "faded": False}
        self.cards[cid] = c
        self._save(c, "card.new")
        self._enforce_cap()
        return c

    def _enforce_cap(self):
        cap = config.settings()["max_cards"]
        open_cards = sorted((c for c in self.cards.values() if c["state"] == "open"), key=lambda c: c["score"])
        while len(open_cards) > cap:
            low = open_cards.pop(0)
            self.set_state(low["id"], "missed", reason="over card cap")

    # transitions ----------------------------------------------------
    def set_state(self, cid, state, via=None, reason=None):
        c = self.cards.get(cid)
        if not c:
            return None
        now = self.clock()
        c["state"], c["updated"] = state, now
        if state == "answered":
            c["answered_at"], c["answered_via"], c["faded"] = now, via, False
            self.store.log_event("answered", {"card": cid, "via": via, "user_id": c["user_id"],
                                              "platform": c["platform"], "score": c["score"],
                                              "rules": [r["rule"] for r in c["reasons"]],
                                              "latency_s": round(now - c["created"], 1)})
        elif state in ("dismissed", "missed"):
            self.store.log_event(state, {"card": cid, "user_id": c["user_id"], "platform": c["platform"],
                                        "score": c["score"], "rules": [r["rule"] for r in c["reasons"]]})
        elif state == "open":
            c["faded"], c["snooze_until"] = False, None
            if c["answered_at"] or c["state"] == "open":
                self.store.log_event("reopened", {"card": cid, "user_id": c["user_id"]})
        if reason:
            c["note"] = reason
        self._save(c, "card.update")
        return c

    def answer(self, cid, via="manual"):
        return self.set_state(cid, "answered", via=via)

    def dismiss(self, cid):
        return self.set_state(cid, "dismissed")

    def reopen(self, cid):
        return self.set_state(cid, "open")

    def snooze(self, cid, seconds=300):
        c = self.cards.get(cid)
        if not c:
            return None
        c["snooze_until"] = self.clock() + seconds
        return self.set_state(cid, "snoozed")

    def set_tier(self, cid, tier):
        c = self.cards.get(cid)
        if c:
            self.store.log_event("manual_tier", {"card": cid, "from": c["tier"], "to": tier, "user_id": c["user_id"],
                                                 "rules": [r["rule"] for r in c["reasons"]]})
            c["tier"] = tier
            self._save(c, "card.update")
        return c

    # reply detection ------------------------------------------------
    def on_own_message(self, msg):
        """Called for every message sent by the streamer (any route). Closes matching open cards.
        Platform reply (reply_to) is exact; an @mention of the viewer only counts on the same platform."""
        closed = []
        text = msg.text.lower()
        for c in list(self.cards.values()):
            if c["state"] not in ("open", "missed", "snoozed") or c["platform"] != msg.platform:
                continue
            if msg.reply_to and msg.reply_to == c["message_id"]:
                closed.append(self.answer(c["id"], via="platform_reply"))
            elif f"@{c['user'].lower()}" in text:
                closed.append(self.answer(c["id"], via="mention"))
        return closed

    # timers ---------------------------------------------------------
    def tick(self):
        now, st = self.clock(), config.settings()
        changed = []
        for c in list(self.cards.values()):
            s = c["state"]
            if s == "open" and now - c["created"] >= st["missed_after_s"]:
                changed.append(self.set_state(c["id"], "missed"))
            elif s == "snoozed" and c["snooze_until"] and now >= c["snooze_until"]:
                c["state"], c["snooze_until"], c["updated"] = "open", None, now
                self._save(c, "card.update")
                changed.append(c)
            elif s == "answered" and not c["faded"] and now - c["answered_at"] >= st["answered_fade_s"]:
                c["faded"] = True
                self._save(c, "card.update")
                changed.append(c)
        return changed

    def view(self):
        """Cards the UI should show: open + snoozed hidden, answered until faded, missed separately."""
        out = {"open": [], "answered": [], "missed": []}
        for c in self.cards.values():
            if c["state"] == "open":
                out["open"].append(c)
            elif c["state"] == "answered" and not c["faded"]:
                out["answered"].append(c)
            elif c["state"] == "missed":
                out["missed"].append(c)
        out["open"].sort(key=lambda c: (-c["score"], c["created"]))
        out["missed"].sort(key=lambda c: -c["updated"])
        return out

    def recap(self, limit=50):
        """Post-stream list of everything never answered (open, missed, snoozed), best first."""
        todo = [c for c in self.cards.values() if c["state"] in ("open", "missed", "snoozed")]
        todo.sort(key=lambda c: (-c["score"], c["created"]))
        return todo[:limit]

    def _save(self, c, ev):
        self.store.save_card(c)
        self.emit({"type": ev, "card": c})
