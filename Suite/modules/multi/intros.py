"""Viewer intros: when a REAL person's first-time or returning message arrives, ask the Host (which stores the viewers' submitted intros and the mods'
approvals) for that viewer's APPROVED intro and put it through the central alert queue as an "intro" alert. One play per viewer per stream.
Multi never stores or approves intros; it only plays what the Host says is approved, and re-checks length and links itself."""
import asyncio
import json
import os
import re
import time
import urllib.parse
import urllib.request

import alert_media
import config
import console_log

HOST = "http://127.0.0.1:8770"
# The Host's plain GET /api/intro is its OLD sub-intro video system (returns its settings and queue), so viewer intros live
# on their own path. The Host must answer {text, sound_id, status: "approved"} there; anything without an explicit
# status "approved" is treated as "no intro".
VIEWER_PATH = "/api/intro/viewer"
MAX_LEN = 140
_LINK = re.compile(r"(https?:|www\.|\b[\w-]+\.(com|net|org|tv|gg|io|me|co|xyz|ly)\b|@everyone)", re.I)


def clean_text(text):
    """-> cleaned intro text or '' when it must not play (empty, too long, contains a link)"""
    t = " ".join(str(text or "").split())
    if not t or len(t) > MAX_LEN or _LINK.search(t):
        return ""
    return t


def fetch_host(platform, user_id):
    """-> {text, sound_id, status?} or None. Origin-gated Host API; sends Multi's own origin and module token."""
    url = f"{HOST}{VIEWER_PATH}?platform={urllib.parse.quote(platform)}&user_id={urllib.parse.quote(str(user_id))}"
    h = {"Origin": "http://127.0.0.1:8766"}
    tok = os.environ.get("PINGUINO_API_TOKEN")
    if tok:
        h["Authorization"] = "Bearer " + tok
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=2.5) as r:
            d = json.loads(r.read().decode("utf-8"))
            return d if isinstance(d, dict) else None
    except Exception:
        return None


class Intros:
    def __init__(self, store, submit, epoch, fetch=fetch_host, clock=time.time):
        self.store, self.submit, self.epoch, self.fetch, self.clock = store, submit, epoch, fetch, clock
        self.miss = {}                                      # (platform, user_id) -> ts of a "no intro" answer (cached 60 s)
        s = store.kv_get("intro:played") or {}
        self.stream, self.played = s.get("stream", 0), set(s.get("users", []))
        self.stats = {"played": 0, "none": 0}

    def _roll(self):
        """a new stream (the new-chatter list rolled over) forgets who already had their intro"""
        e = self.epoch()
        if e != self.stream:
            self.stream, self.played = e, set()
            self.store.kv_set("intro:played", {"stream": e, "users": []})

    def wants(self, m):
        fl = m.flags or []
        return bool(config.settings().get("intro_enabled", True) and m.user_id and not m.is_bot and not m.is_self
                    and (m.first_time or "new" in fl or "returning" in fl))

    async def observe(self, m):
        """Never raises. Returns True when an intro was queued."""
        try:
            if not self.wants(m):
                return False
            self._roll()
            key = f"{m.platform}:{m.user_id}"
            now = self.clock()
            if key in self.played or now - self.miss.get(key, 0) < 60:
                return False
            d = await asyncio.to_thread(self.fetch, m.platform, m.user_id)
            if not d or d.get("status") != "approved" or not d.get("approved", True) or "text" not in d:
                self.miss[key] = now
                self.stats["none"] += 1
                if len(self.miss) > 5000:
                    self.miss.clear()
                return False
            text = clean_text(d.get("text"))
            if not text:
                self.miss[key] = now
                return False
            ev = {"type": "intro", "user": m.user, "display": m.display, "message": text, "platform": m.platform, "id": f"intro:{key}:{self.stream}",
                  "first_time": bool(m.first_time or "new" in (m.flags or []))}
            sid = alert_media.safe_name(d.get("sound_id") or "")
            if sid and (alert_media.DIR / sid).is_file() and alert_media.KIND.get(os.path.splitext(sid)[1].lower()) == "sound":
                ev["sound_url"] = "/alert-media/" + sid
            ok, _ = self.submit(ev)
            if ok:
                self.played.add(key)
                self.store.kv_set("intro:played", {"stream": self.stream, "users": sorted(self.played)[-5000:]})
                self.stats["played"] += 1
            return bool(ok)
        except Exception as e:
            console_log.error("intro", f"intro lookup failed: {e}", dedupe_s=60)
            return False
