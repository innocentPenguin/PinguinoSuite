"""Optional AI assist for the uncertain score band. Local scoring always runs first and is always shown.

Modes (setting priority_mode): local = never call AI | ai = AI for uncertain messages, errors are surfaced as
fallbacks in stats | auto = same, and any error/timeout/spend-cap silently keeps the local score.
Key lives in Credential Manager ('ai_key'); text sent is just the message and the sender's login.
"""
import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict

import requests

import config
import secrets_store

PRICE_PER_CALL = {"anthropic": 0.0004, "openai": 0.0003, "ollama": 0.0}     # rough upper estimates, USD
PROMPT = ("You help a livestreamer pick which chat messages deserve a personal reply. Rate how much this message "
          "needs a reply from the streamer, 0 (none) to 10 (definitely). Answer ONLY JSON: {\"need\": <int>}.\n"
          "User: {user}\nMessage: {text}")


def _http(provider, model, key, prompt, timeout):
    if provider == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=timeout,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                          json={"model": model, "max_tokens": 30, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    if provider == "openai":
        r = requests.post("https://api.openai.com/v1/chat/completions", timeout=timeout,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "max_tokens": 30, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    if provider == "ollama":
        r = requests.post("http://127.0.0.1:11434/api/generate", timeout=timeout,
                          json={"model": model, "prompt": prompt, "stream": False})
        r.raise_for_status()
        return r.json()["response"]
    raise ValueError("unknown provider")


def parse_need(text):
    m = re.search(r'"need"\s*:\s*(\d+)', text or "")
    if not m:
        raise ValueError("unparseable AI answer")
    return max(0, min(10, int(m.group(1))))


class Advisor:
    def __init__(self, store, call=_http, clock=time.time):
        self.store, self.call, self.clock = store, call, clock
        self.cache = OrderedDict()
        self.stats = {"calls": 0, "cache_hits": 0, "fallbacks": 0}

    # spend ---------------------------------------------------------
    def _day(self):
        return time.strftime("%Y-%m-%d", time.localtime(self.clock()))

    def spend(self):
        s = self.store.kv_get("ai_spend", {})
        return s if s.get("day") == self._day() else {"day": self._day(), "usd": 0.0, "calls": 0}

    def _charge(self, usd):
        s = self.spend()
        s["usd"] = round(s["usd"] + usd, 6)
        s["calls"] += 1
        self.store.kv_set("ai_spend", s)

    def usage(self):
        st = config.settings()
        return dict(self.spend(), cap_usd=st["ai_daily_cap_usd"], mode=st["priority_mode"], provider=st["ai_provider"],
                    has_key=bool(secrets_store.get("ai_key")), **self.stats)

    # gating ----------------------------------------------------------
    def wants(self, score, text, rules):
        st = config.settings()
        if st["priority_mode"] == "local" or len(text.strip()) < 8:
            return False
        t = rules["tiers"]
        return any(abs(score - v) <= st["ai_margin"] for v in (t["low"], t["medium"], t["high"]))

    # refine -----------------------------------------------------------
    async def refine(self, user, text):
        """Returns {'delta': float, 'detail': str} or None (local score stands)."""
        st = config.settings()
        prov = st["ai_provider"]
        key = secrets_store.get("ai_key")
        if prov != "ollama" and not key:
            return self._fallback("no key")
        h = hashlib.sha1(re.sub(r"\W+", " ", text.lower()).strip().encode()).hexdigest()
        if h in self.cache:
            self.stats["cache_hits"] += 1
            self.cache.move_to_end(h)
            return self.cache[h]
        price = PRICE_PER_CALL.get(prov, 0.001)
        if self.spend()["usd"] + price > st["ai_daily_cap_usd"]:
            return self._fallback("daily spend cap")
        prompt = PROMPT.replace("{user}", user).replace("{text}", text[:400])
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self.call, prov, st["ai_model"], key, prompt, st["ai_timeout_s"]),
                timeout=st["ai_timeout_s"] + 0.5)
            need = parse_need(raw)
        except Exception as e:
            return self._fallback(type(e).__name__)
        self.stats["calls"] += 1
        self._charge(price)
        res = {"delta": float((need - 5) * 3), "detail": f"AI rated reply-need {need}/10"}
        self.cache[h] = res
        if len(self.cache) > 500:
            self.cache.popitem(last=False)
        return res

    def _fallback(self, why):
        self.stats["fallbacks"] += 1
        self.stats["last_fallback"] = why
        return None
