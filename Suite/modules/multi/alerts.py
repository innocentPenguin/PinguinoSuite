"""Central alert engine: ONE priority queue for follow / refollow / sub / gift / bits / raid / hype / goal / redeem / streak / intro.
Real events (Host feed, /api/events) and test events enter through Engine.submit(); the overlay (/obs/alerts) only renders what the engine emits
('alert.show' / 'alert.end' over the WS hub), so it works offline. Test events are flagged and never leave this module (no inbox, no stats, no chat).
Config (kv 'alerts:cfg'): {active, profiles{name:{types{type:cfg}}}, overrides{login:{type|'*':partial cfg}}, global{gap_ms,max_queue}}."""
import asyncio
import copy
import heapq
import re
import time
from collections import deque

from obs import FONTS, _color, _num

TYPES = ["follow", "refollow", "sub", "resub", "gift", "cheer", "raid", "hype", "goal", "redeem", "streak", "watchtime", "anniversary", "comeback", "intro"]
LABEL = {"follow": "Follow", "refollow": "Refollow", "sub": "Subscription", "resub": "Resub", "gift": "Gift subs", "cheer": "Bits", "raid": "Raid",
         "hype": "Hype train", "goal": "Goal reached", "redeem": "Redemption", "streak": "Watch streak", "watchtime": "Watch-time milestone", "anniversary": "Anniversary", "comeback": "First stream back", "intro": "Intro"}
ANIMS = ["fade", "slide-up", "slide-down", "slide-left", "slide-right", "zoom", "bounce", "flip"]
LAYOUTS = ["card", "banner", "center", "stack"]
VARS = ["{user}", "{amount}", "{tier}", "{months}", "{message}", "{level}", "{recipient}", "{streak}", "{hours}", "{years}", "{platform}", "{currency}"]
ORANGE, DARK, CREAM = "#ff8a1f", "#1a1208", "#ffe9cc"

_STYLE = {"bg": DARK, "fg": CREAM, "accent": ORANGE, "font": "nunito", "size": 30, "layout": "card", "anim_in": "slide-up", "anim_out": "fade",
          "radius": 14, "border": 2, "opacity": 94, "confetti": False}
_SOUND = {"enabled": True, "url": "", "volume": 70, "tier_urls": {"1": "", "2": "", "3": ""}}
_MEDIA = {"url": "", "kind": "image", "position": "above", "size": 160}


def _ms(points, what):
    """default celebration tiers: bigger milestone = higher priority, longer, confetti from the 3rd tier on"""
    out = []
    for i, at in enumerate(points):
        out.append({"at": at, "text": "", "subtext": "", "priority": min(9, 5 + i), "duration": min(14, 6 + i), "accent": ["", "", "", "#ffd23f", "#ffd23f", "#ff4d4d"][min(i, 5)], "confetti": i >= 2})
    return out


def _t(text, sub="", prio=5, dur=6, **kw):
    d = {"enabled": True, "priority": prio, "duration": dur, "text": text, "subtext": sub, "min_amount": 0, "silent": False, "cooldown_s": 0, "max_per_min": 0,
         "conditions": {"first_time_only": False, "tiers": []}, "milestones": [], "exact": False, "style": dict(_STYLE), "sound": copy.deepcopy(_SOUND), "media": dict(_MEDIA)}
    d.update(kw)
    return d


DEFAULT_TYPES = {
    "follow": _t("{user} followed!", "welcome to the colony", 3, 5),
    "refollow": _t("{user} is back!", "welcome back", 2, 4, silent=True),
    "sub": _t("{user} subscribed!", "Tier {tier}", 7, 7),
    "resub": _t("{user} resubbed!", "{months} months - {message}", 7, 7),
    "gift": _t("{user} gifted {amount} subs!", "thank you!", 8, 8),
    "cheer": _t("{user} cheered {amount} bits!", "{message}", 6, 6, min_amount=1),
    "raid": _t("{user} is raiding with {amount}!", "welcome raiders", 9, 8),
    "hype": _t("HYPE TRAIN!", "level {level}", 8, 7),
    "goal": _t("Goal reached!", "{message}", 6, 7),
    "redeem": _t("{user} redeemed {message}", "", 4, 5),
    "streak": _t("{user} hit a {amount}-stream watch streak!", "", 4, 6),
    "watchtime": _t("{user} reached {hours} hours!", "thank you for hanging out", 6, 7, exact=False, milestones=_ms([10, 50, 100, 250, 500, 1000], "hours")),
    "anniversary": _t("{user}: {years} year(s) watching!", "happy colony-versary", 7, 8, exact=True, milestones=_ms([1, 2, 3, 4, 5], "years")),
    "comeback": _t("{user} is back for the first stream in a while!", "welcome back", 4, 5),
    "intro": _t("{user} has arrived", "{message}", 5, 6),
}
DEFAULT_TYPES["streak"].update(text="{user} is on a {streak}-stream watch streak!", subtext="", exact=True, milestones=_ms([3, 5, 10, 25, 50, 100], "streak"))
GLOBAL = {"gap_ms": 600, "max_queue": 50, "dedupe_s": 10}
THEMES = {"Penguin": {}, "Light": {"*": {"style": {"bg": "#fff7ec", "fg": "#2b1a05", "accent": "#e56f00"}}},
          "Minimal": {"*": {"style": {"layout": "center", "bg": "#000000", "opacity": 0, "border": 0}}}}


def default_config():
    prof = {name: {"types": {t: _merge(copy.deepcopy(DEFAULT_TYPES[t]), (over.get("*") or {})) for t in TYPES}} for name, over in THEMES.items()}
    return {"active": "Penguin", "profiles": prof, "overrides": {}, "global": dict(GLOBAL)}


def _merge(base, over):
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def _url(v):
    v = str(v or "").strip()[:400]
    return v if v.startswith(("http://", "https://", "/")) and not v.startswith("//") else ""


def _int(v, d=0):
    """int from anything a webhook might send (None, '', 'abc', nan, inf, 1e30 -> d / clamped)"""
    try:
        return max(-10**9, min(10**9, int(float(v if v not in (None, "") else d))))
    except (TypeError, ValueError, OverflowError):
        return d


def _font(v):
    v = str(v or "nunito").strip()[:60]
    return v if v in FONTS or re.fullmatch(r"[A-Za-z0-9 ,'_-]+", v) else "nunito"


def sanitize_type(c, base):
    """One alert-type cfg (full or partial) onto its base; unknown keys dropped, numbers clamped."""
    out = copy.deepcopy(base)
    if not isinstance(c, dict):
        return out
    for k in ("enabled", "silent"):
        if k in c:
            out[k] = bool(c[k])
    for k, lo, hi in (("priority", 1, 9), ("duration", 1, 30), ("min_amount", 0, 1000000), ("cooldown_s", 0, 3600), ("max_per_min", 0, 600)):
        if k in c:
            out[k] = int(_num(c[k], lo, hi, out[k]))
    for k in ("text", "subtext"):
        if k in c:
            out[k] = str(c[k] or "")[:200]
    if isinstance(c.get("milestones"), list):
        out["milestones"] = _clean_ms(c["milestones"])
    if "exact" in c:
        out["exact"] = bool(c["exact"])
    cd = c.get("conditions")
    if isinstance(cd, dict):
        if "first_time_only" in cd:
            out["conditions"]["first_time_only"] = bool(cd["first_time_only"])
        if "tiers" in cd:
            out["conditions"]["tiers"] = [x for x in (str(t) for t in (cd["tiers"] if isinstance(cd["tiers"], list) else [])) if x in ("1", "2", "3", "prime")]
    s = c.get("style")
    if isinstance(s, dict):
        o = out["style"]
        for k in ("bg", "fg", "accent"):
            if k in s:
                o[k] = _color(s[k], o[k]) or o[k]
        if "font" in s:
            o["font"] = _font(s["font"])
        for k, lo, hi in (("size", 14, 80), ("radius", 0, 60), ("border", 0, 12), ("opacity", 0, 100)):
            if k in s:
                o[k] = int(_num(s[k], lo, hi, o[k]))
        if s.get("layout") in LAYOUTS:
            o["layout"] = s["layout"]
        if "confetti" in s:
            o["confetti"] = bool(s["confetti"])
        for k in ("anim_in", "anim_out"):
            if s.get(k) in ANIMS:
                o[k] = s[k]
    so = c.get("sound")
    if isinstance(so, dict):
        if "enabled" in so:
            out["sound"]["enabled"] = bool(so["enabled"])
        if "url" in so:
            out["sound"]["url"] = _url(so["url"])
        if "volume" in so:
            out["sound"]["volume"] = int(_num(so["volume"], 0, 100, 70))
        if isinstance(so.get("tier_urls"), dict):
            for t in ("1", "2", "3"):
                if t in so["tier_urls"]:
                    out["sound"]["tier_urls"][t] = _url(so["tier_urls"][t])
    me = c.get("media")
    if isinstance(me, dict):
        if "url" in me:
            out["media"]["url"] = _url(me["url"])
        if me.get("kind") in ("image", "video"):
            out["media"]["kind"] = me["kind"]
        if me.get("position") in ("above", "left", "bg"):
            out["media"]["position"] = me["position"]
        if "size" in me:
            out["media"]["size"] = int(_num(me["size"], 40, 600, 160))
    return out


def _clean_ms(lst):
    out = []
    for m in lst[:12]:
        if not isinstance(m, dict):
            continue
        at = int(_num(m.get("at"), -1, 1000000, 0))
        if at < 1 or any(x["at"] == at for x in out):
            continue
        out.append({"at": at, "text": str(m.get("text") or "")[:200], "subtext": str(m.get("subtext") or "")[:200], "priority": int(_num(m.get("priority"), 1, 9, 7)),
                    "duration": int(_num(m.get("duration"), 1, 30, 8)), "accent": _color(str(m.get("accent") or ""), ""), "confetti": bool(m.get("confetti"))})
    return sorted(out, key=lambda x: x["at"])


def sanitize_config(src):
    d = default_config()
    if not isinstance(src, dict):
        return d
    g = src.get("global")
    if isinstance(g, dict):
        d["global"]["gap_ms"] = int(_num(g.get("gap_ms"), 0, 5000, GLOBAL["gap_ms"]))
        d["global"]["max_queue"] = int(_num(g.get("max_queue"), 5, 200, GLOBAL["max_queue"]))
        d["global"]["dedupe_s"] = int(_num(g.get("dedupe_s"), 0, 120, GLOBAL["dedupe_s"]))
    profs = src.get("profiles")
    if isinstance(profs, dict):
        for name, p in list(profs.items())[:20]:
            name = str(name).strip()[:30]
            if not name:
                continue
            base = d["profiles"].get(name) or {"types": {t: copy.deepcopy(DEFAULT_TYPES[t]) for t in TYPES}}
            ts = (p or {}).get("types") if isinstance(p, dict) else None
            for t in TYPES:
                base["types"][t] = sanitize_type((ts or {}).get(t), base["types"][t])
            d["profiles"][name] = base
    ov = src.get("overrides")
    if isinstance(ov, dict):
        for login, per in list(ov.items())[:300]:
            login = str(login).strip().lower()[:40]
            if login and isinstance(per, dict):
                d["overrides"][login] = {t: _clean_partial(c) for t, c in per.items() if t in TYPES or t == "*"}
    a = str(src.get("active") or "")
    d["active"] = a if a in d["profiles"] else "Penguin"
    return d


def _clean_partial(c):
    """A per-user override keeps only the keys that were set (so the profile still supplies everything else)."""
    full = sanitize_type(c, DEFAULT_TYPES["follow"])
    out = {}
    for k in ("enabled", "silent", "priority", "duration", "text", "subtext", "min_amount", "cooldown_s", "max_per_min", "milestones", "exact"):
        if isinstance(c, dict) and k in c:
            out[k] = full[k]
    for grp in ("style", "sound", "media", "conditions"):
        if isinstance(c, dict) and isinstance(c.get(grp), dict):
            out[grp] = {k: full[grp][k] for k in c[grp] if k in full[grp]}
    return out


# variables -------------------------------------------------------------------------------------
_VAR = re.compile(r"\{(user|amount|tier|months|message|level|recipient|streak|hours|years|platform|currency)\}")


VALUE_OF = {"streak": "streak", "watchtime": "hours", "anniversary": "years"}


def value(ev, key):
    """the milestone number of an event: its own field (streak/hours/years) or, failing that, amount"""
    return _int(ev.get(key) if ev.get(key) not in (None, "") else ev.get("amount"), 0)


def render(text, ev):
    """text with variables -> list of [segment, kind]; kind 'user' marks the viewer's name (drawn in their rank colour)."""
    vals = {"amount": str(ev.get("amount") or 0), "tier": str(ev.get("tier") or "1"), "months": str(ev.get("months") or 1),
            "message": str(ev.get("message") or ""), "level": str(ev.get("level") or ""), "recipient": str(ev.get("recipient") or ""),
            "platform": str(ev.get("platform") or "twitch").capitalize(), "currency": str(ev.get("currency") or ""), "streak": str(value(ev, "streak")), "hours": str(value(ev, "hours")), "years": str(value(ev, "years"))}
    out, pos = [], 0
    for m in _VAR.finditer(text or ""):
        if m.start() > pos:
            out.append([text[pos:m.start()], ""])
        out.append([ev.get("display") or ev.get("user") or "someone", "user"] if m.group(1) == "user" else [vals[m.group(1)], ""])
        pos = m.end()
    if pos < len(text or ""):
        out.append([text[pos:], ""])
    return [s for s in out if s[0] != ""]


def sync_bridge_token(data_dir, token):
    """The Host posts alerts/tests to Multi with the token in its alert_bridge.json (HostAlertBridge). Multi only knows its own module token,
    so it writes it into that file's Token key (other keys untouched; a missing file gets just the Token, the Host fills defaults). True if changed."""
    import json
    import os
    if not data_dir or not token:
        return False
    p = os.path.join(data_dir, "alert_bridge.json")
    try:
        doc = {}
        if os.path.isfile(p):
            with open(p, encoding="utf-8-sig") as f:
                doc = json.load(f)
        if doc.get("Token") == token:
            return False
        doc["Token"] = token
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        os.replace(tmp, p)
        return True
    except (OSError, ValueError):
        return False


# engine ----------------------------------------------------------------------------------------
class Engine:
    def __init__(self, store, emit):
        self.store, self.emit = store, emit
        self.cfg = sanitize_config(store.kv_get("alerts:cfg", None))
        self.heap, self.seq, self.current, self.paused = [], 0, None, False
        self.seen = deque(store.kv_get("alerts:seen", []) or [], maxlen=500)
        self.recent = {}                      # (type,user,amount) -> ts, short dedupe of the same thing arriving twice
        self.user_last, self.type_hits = {}, {}
        self.log = deque(maxlen=300)
        self.wake, self.task, self.skip_ev = None, None, None

    # -- config
    def save(self, cfg):
        self.cfg = sanitize_config(cfg)
        self.store.kv_set("alerts:cfg", self.cfg)
        self.emit({"type": "alert.config"})
        return self.cfg

    def type_cfg(self, t, login=""):
        prof = self.cfg["profiles"].get(self.cfg["active"]) or next(iter(self.cfg["profiles"].values()))
        c = copy.deepcopy(prof["types"][t])
        ov = self.cfg["overrides"].get((login or "").lower())
        if ov:
            _merge(c, ov.get("*"))
            _merge(c, ov.get(t))
        return c

    # -- ingest
    def classify(self, ev):
        t = ev.get("type")
        if t == "follow" and ev.get("refollow"):
            return "refollow"
        return t if t in TYPES else None

    def submit(self, ev):
        """ev: {id,type,user,display,amount,tier,months,message,level,rank_colour,avatar,first_time,refollow,test,source}. Returns (ok, reason)."""
        t = self.classify(ev)
        test = bool(ev.get("test"))
        if not t:
            return self._note(ev, "ignored", "not an alert type")
        ev = dict(ev, type=t, user=str(ev.get("user") or "someone")[:60])
        ev["amount"] = _int(ev.get("amount"))
        for k, n in (("message", 300), ("display", 60), ("recipient", 60), ("level", 20), ("tier", 10)):
            if k in ev:
                ev[k] = str(ev[k] if ev[k] is not None else "")[:n]
        ev["display"] = ev.get("display") or ev["user"]
        eid = str(ev.get("id") or f"a:{time.time_ns()}")
        ev["id"] = eid
        now = time.time()
        if not test:
            if eid in self.seen:
                return self._note(ev, "duplicate", "already fired (replay)")
            key = (t, str(ev.get("platform") or "") + ":" + ev["user"].lower(), value(ev, VALUE_OF[t]) if t in VALUE_OF else int(ev.get("amount") or 0))
            if now - self.recent.get(key, 0) < self.cfg["global"]["dedupe_s"]:
                return self._note(ev, "duplicate", "same event just fired")
            self.seen.append(eid)
            self.store.kv_set("alerts:seen", list(self.seen))
        c = self.type_cfg(t, ev["user"])
        why = self._milestone(c, t, ev)
        if not why:
            why = self._blocked(c, t, ev, now, test)
        if why:
            return self._note(ev, "skipped", why)
        if not test:
            self.recent[key] = now                      # only an event that is really shown counts as "just fired"
            if len(self.recent) > 500:
                self.recent = {k: v for k, v in self.recent.items() if now - v < 120}
        if len(self.heap) >= self.cfg["global"]["max_queue"]:
            return self._note(ev, "dropped", "queue full")
        payload = self._payload(c, ev, test)
        self.seq += 1
        heapq.heappush(self.heap, (-c["priority"], self.seq, payload))
        self._note(ev, "queued", f"priority {c['priority']}")
        self._poke()
        return True, "queued"

    def _milestone(self, c, t, ev):
        """celebration tiers: pick the biggest milestone reached and apply its look; exact types only fire ON a milestone. Returns a skip reason or ''."""
        ms = c.get("milestones") or []
        if t not in VALUE_OF or not ms:
            return ""
        v = value(ev, VALUE_OF[t])
        hit = [m for m in ms if m["at"] <= v]
        if not hit:
            return f"below the first milestone ({ms[0]['at']})"
        m = hit[-1]
        if c.get("exact") and m["at"] != v:
            return f"{v} is not a milestone"
        for k in ("text", "subtext"):
            if m[k]:
                c[k] = m[k]
        c["priority"], c["duration"] = m["priority"], m["duration"]
        if m["accent"]:
            c["style"]["accent"] = m["accent"]
        if m["confetti"]:
            c["style"]["confetti"] = True
        return ""

    def _blocked(self, c, t, ev, now, test):
        if not c["enabled"]:
            return "type disabled"
        if _int(ev.get("amount")) < c["min_amount"]:
            return f"below minimum {c['min_amount']}"
        cd = c["conditions"]
        if cd["first_time_only"] and not ev.get("first_time"):
            return "only for first-time viewers"
        if cd["tiers"] and str(ev.get("tier") or "1") not in cd["tiers"]:
            return "tier not selected"
        if not test:
            uk = (t, ev["user"].lower())
            if c["cooldown_s"] and now - self.user_last.get(uk, 0) < c["cooldown_s"]:
                return "per-user cooldown"
            hits = [x for x in self.type_hits.get(t, []) if now - x < 60]
            if c["max_per_min"] and len(hits) >= c["max_per_min"]:
                return "rate limit"
            self.user_last[uk] = now
            self.type_hits[t] = hits + [now]
        return ""

    def _payload(self, c, ev, test):
        so = c["sound"]
        url = (so["tier_urls"].get(str(ev.get("tier") or ""), "") or so["url"]) if so["enabled"] and not c["silent"] else ""
        return {"id": ev["id"], "type": ev["type"], "label": LABEL[ev["type"]], "priority": c["priority"], "duration": c["duration"], "test": test,
                "text": render(c["text"], ev), "subtext": render(c["subtext"], ev), "style": c["style"], "media": c["media"] if c["media"]["url"] else None,
                "sound": {"on": bool(so["enabled"] and not c["silent"]), "url": url, "volume": so["volume"]},
                "platform": str(ev.get("platform") or ""), "rank_colour": _color(str(ev.get("rank_colour") or ""), ""), "avatar": _url(ev.get("avatar")), "user": ev["user"]}

    def preview(self, t, ev=None):
        """Resolved payload without queueing (editor preview)."""
        ev = dict({"type": t, "user": "penguin", "display": "Penguin", "amount": 5, "tier": "1", "months": 6, "message": "hello colony", "level": 3,
                   "id": "preview"}, **(ev or {}))
        c = self.type_cfg(self.classify(ev) or t, ev["user"])
        return self._payload(c, ev, True)

    # -- queue runner
    def _poke(self):
        if self.wake:
            self.wake.set()

    def start(self):
        self.wake = asyncio.Event()
        self.task = asyncio.ensure_future(self._run())

    async def _run(self):
        while True:
            if self.paused or not self.heap:
                self.wake.clear()
                self._state()
                await self.wake.wait()
                continue
            _, _, p = heapq.heappop(self.heap)
            self.current = p
            self.skip_ev = asyncio.Event()
            try:
                self.emit({"type": "alert.show", "alert": p})
                self._note(p, "fired", "test" if p["test"] else "live")
                self._state()
                await asyncio.wait_for(self.skip_ev.wait(), p["duration"] + 0.6)
            except asyncio.TimeoutError:
                pass
            except Exception as e:                       # one bad emit must never kill the queue runner for the rest of the stream
                self._note(p, "error", f"{type(e).__name__}: {e}"[:120])
            self.current = None
            try:
                self.emit({"type": "alert.end", "id": p["id"]})
            except Exception:
                pass
            await asyncio.sleep(self.cfg["global"]["gap_ms"] / 1000)

    def _state(self):
        self.emit({"type": "alert.state", **self.status()})

    def status(self):
        return {"queued": len(self.heap), "current": self.current["id"] if self.current else None, "paused": self.paused}

    def skip(self):
        if self.skip_ev:
            self.skip_ev.set()

    def clear(self):
        n = len(self.heap)
        self.heap.clear()
        self.skip()
        self._state()
        return n

    def pause(self, on):
        self.paused = bool(on)
        self._poke()
        self._state()

    def _note(self, ev, status, why):
        self.log.appendleft({"ts": time.time(), "id": ev.get("id"), "type": ev.get("type"), "user": ev.get("user"), "amount": ev.get("amount"),
                             "status": status, "why": why, "test": bool(ev.get("test"))})
        return status in ("queued", "fired"), why


# test tools ------------------------------------------------------------------------------------
MILESTONE_TEST = {"streak": [3, 10, 25, 100], "watchtime": [10, 100, 500, 1000], "anniversary": [1, 2, 3, 5]}
VARIANTS = {"tier1": {"tier": "1"}, "tier2": {"tier": "2"}, "tier3": {"tier": "3"}, "prime": {"tier": "prime"}, "first": {"first_time": True},
            "refollow": {"refollow": True}, "noavatar": {"avatar": ""}, "long": {"display": "TheMostIncrediblyLongViewerNameEver_1234"},
            "unicode": {"display": "Pinguïno_ペンギン"}, "small": {}, "mid": {}, "big": {}, "huge": {}, "msg": {"message": "This is a long resub message that wraps over several lines to check the layout holds up nicely."}}


def test_event(t, user="penguin", amount=None, variants=(), **kw):
    ev = {"type": t, "user": user or "penguin", "display": user or "Penguin", "amount": 0, "tier": "1", "months": 6, "message": "hello colony", "level": 3,
          "test": True, "source": kw.get("source", "ui"), "avatar": "", "rank_colour": kw.get("rank_colour", "")}
    ev["id"] = f"test:{time.time_ns()}"
    if t in ("gift", "raid", "cheer"):
        ev["amount"] = 5 if t != "cheer" else 100
    if t in MILESTONE_TEST:
        ev["amount"] = MILESTONE_TEST[t][1]
    for v in variants or ():
        v = str(v).lower()
        if t in MILESTONE_TEST and v in ("small", "mid", "big", "huge"):
            ev["amount"] = MILESTONE_TEST[t][("small", "mid", "big", "huge").index(v)]
        ev.update(VARIANTS.get(v, {}))
    if amount is not None:
        ev["amount"] = int(amount)
    for k in ("tier", "months", "message", "level", "recipient"):
        if kw.get(k) not in (None, ""):
            ev[k] = kw[k]
    return ev


def host_token(data_dir):
    """The Host's module token, derived read-only from the key the Suite keeps in <data_dir>/module_secret (same formula as suite.module_token).
    '' when the key file is missing or unreadable."""
    import hashlib
    import os
    import hmac as _hmac
    if not data_dir:
        return ""
    try:
        with open(os.path.join(data_dir, "module_secret"), encoding="utf-8") as fh:
            key = fh.read().strip()
    except OSError:
        return ""
    if len(key) < 32:
        return ""
    return _hmac.new(key.encode(), b"module:host", hashlib.sha256).hexdigest()[:40]


HOST_TOKEN_PATHS = ("/api/alerts/", "/api/events")
