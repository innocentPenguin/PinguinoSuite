"""Single entry point for every connector: dedupe -> score -> store -> card -> broadcast.

Bounded: the inbound queue drops the oldest LOW-priority message when full (priority candidates are kept).
"""
import asyncio
import time

import config
import ai
import console_log
import ding as ding_mod
import pop as pop_mod
import dedupe
from priority import rules as prio
from models import ChatMessage


class Pipeline:
    def __init__(self, store, cards, emit):
        self.store, self.cards, self.emit = store, cards, emit
        self.seen = dedupe.Seen()
        self.rules = prio.load_rules()
        self.advisor = ai.Advisor(store)
        self.ding = ding_mod.Ding(store)
        self.pop = pop_mod.Pop()
        self.recent_by_user = {}     # (platform,user_id) -> [(ts,text,mention)] small bounded history
        self.stats = {"in": 0, "dupes": 0, "dropped": 0}

    def reload_rules(self):
        self.rules = prio.load_rules()

    def _ctx(self, m):
        key = (m.platform, m.user_id)
        hist = self.recent_by_user.get(key, [])
        answered = any(c["user_id"] == m.user_id and c["platform"] == m.platform and c["state"] == "answered"
                       and time.time() - (c["answered_at"] or 0) <= self.rules["conversation_window_s"]
                       for c in self.cards.cards.values())
        return prio.Context(recent_by_user=hist, user_count=self.store.user_count(m.platform, m.user_id),
                            answered_recently=answered, learned=self.store.kv_get("learned", {}))

    def ingest(self, m: ChatMessage):
        """Process one normalized message. Returns the stored message dict or None for duplicates."""
        if not self.seen.add(m.id):
            self.stats["dupes"] += 1
            return None
        st = config.settings()
        if m.is_self:
            self.pop.observe(m)
            self.store.add_message(m, prio.Decision(0, "none", []))
            self.emit({"type": "message", "message": dict(m.to_dict(), score=0, tier="none", reasons=[])})
            self.cards.on_own_message(m)
            return m.to_dict()
        d = prio.score(m, self._ctx(m), self.rules, st)
        if not self.store.add_message(m, d):          # survives restarts: DB id is the final dedupe
            self.stats["dupes"] += 1
            return None
        self.stats["in"] += 1
        self.ding.observe(m)
        self.pop.observe(m)
        key = (m.platform, m.user_id)
        hist = self.recent_by_user.setdefault(key, [])
        hist.append((m.ts, m.text, prio.mentions_me(m.text, st["my_names"])))
        del hist[:-10]
        if len(self.recent_by_user) > 5000:
            self.recent_by_user.pop(next(iter(self.recent_by_user)))
        ctx_msgs = [dict(x, score=x.get("score", 0)) for x in self.store.user_history(m.platform, m.user_id, 4)[1:]]
        card = self.cards.maybe_create(m, d, context=[{"user": x["user"], "text": x["text"], "ts": x["ts"]}
                                                      for x in ctx_msgs])
        out = dict(m.to_dict(), score=d.score, tier=d.tier, reasons=d.reasons)
        self.emit({"type": "message", "message": out})
        out["_ai"] = self.advisor.wants(d.score, m.text, self.rules)
        return out

    async def refine(self, out):
        """AI second opinion for uncertain scores. Never blocks display; any failure keeps the local score."""
        res = await self.advisor.refine(out["user"], out["text"])
        if not res:
            return None
        score = round(max(0.0, out["score"] + res["delta"]), 1)
        t = self.rules["tiers"]
        tier = "high" if score >= t["high"] else "medium" if score >= t["medium"] else "low" if score >= t["low"] else "none"
        reasons = out["reasons"] + [{"rule": "ai", "points": res["delta"], "detail": res["detail"]}]
        self.store.update_score(out["id"], score, tier)
        card = self.cards.cards.get("c:" + out["id"])
        if card and card["state"] == "open":
            card.update(score=score, tier=tier, reasons=reasons)
            self.cards._save(card, "card.update")
        elif not card and tier in ("medium", "high"):
            from models import Decision, ChatMessage
            m = ChatMessage(**{k: v for k, v in out.items() if k in ChatMessage.__dataclass_fields__})
            self.cards.maybe_create(m, Decision(score, tier, reasons))
        self.emit({"type": "message.rescored", "id": out["id"], "score": score, "tier": tier, "reasons": reasons})
        return score


class Inbox:
    """Bounded async queue in front of the pipeline (burst protection)."""

    def __init__(self, pipeline, cap=2000):
        self.p, self.q, self.cap = pipeline, asyncio.Queue(), cap

    def put(self, m):
        if self.q.qsize() >= self.cap:
            # drop the oldest message that is not a likely priority candidate; never drop mentions/questions
            self.p.stats["dropped"] += 1
            if not (prio.is_question(m.text) or prio.mentions_me(m.text, config.settings()["my_names"])):
                return
        self.q.put_nowait(m)

    async def run(self):
        while True:
            m = await self.q.get()
            try:
                out = self.p.ingest(m)
                if out and out.pop("_ai", False):
                    asyncio.create_task(self.p.refine(out))
            except Exception as e:      # one bad message must never stop the feed
                print("pipeline error:", e, flush=True)
                console_log.error("pipeline", f"ingest failed: {type(e).__name__}: {e}", dedupe_s=60)
            if self.q.qsize() > 50:     # during bursts yield to the event loop frequently
                await asyncio.sleep(0)
