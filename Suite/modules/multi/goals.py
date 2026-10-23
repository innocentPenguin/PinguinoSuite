"""Stream goal bar: one goal (title, target, current) that fills by hand or from live events (follows, subs, bits). Shown at /obs/goal;
reaching the target fires one "goal" alert. Stored in the kv table, so it survives restarts."""
import re
import time
from collections import deque

KINDS = ("manual", "follow", "sub", "bits")
DEFAULT = {"title": "Stream goal", "target": 100, "current": 0, "kind": "manual", "unit": "", "done": False, "updated": 0}
SUBS = ("sub", "resub")


def _int(v, lo, hi, d):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError, OverflowError):
        return d


class Goal:
    def __init__(self, store, submit):
        self.store, self.submit = store, submit
        self.cfg = self.clean(store.kv_get("goal:cfg") or {}, dict(DEFAULT))
        self.seen = deque(store.kv_get("goal:seen") or [], maxlen=500)     # event ids already counted: a replayed feed/restart must not count twice

    @staticmethod
    def clean(src, base):
        out = dict(base)
        if isinstance(src, dict):
            if "title" in src:
                out["title"] = re.sub(r"\s+", " ", str(src["title"] or ""))[:80] or base["title"]
            if "unit" in src:
                out["unit"] = str(src["unit"] or "")[:12]
            if "kind" in src and src["kind"] in KINDS:
                out["kind"] = src["kind"]
            if "target" in src:
                out["target"] = _int(src["target"], 1, 10**9, base["target"])
            if "current" in src:
                out["current"] = _int(src["current"], 0, 10**9, base["current"])
            if "done" in src:
                out["done"] = bool(src["done"])
        return out

    def state(self):
        c = dict(self.cfg)
        c["pct"] = min(100, int(c["current"] * 100 / c["target"])) if c["target"] else 0
        return c

    def _save(self):
        self.cfg["updated"] = time.time()
        self.store.kv_set("goal:cfg", self.cfg)

    def set(self, src):
        """editor / API: change title, target, kind, or set the current value; a new target or value below it re-arms the finish alert"""
        old = self.cfg
        self.cfg = self.clean(src, old)
        if self.cfg["current"] < self.cfg["target"]:
            self.cfg["done"] = False
        self._save()
        self._check()
        return self.state()

    def reset(self):
        return self.set({"current": 0, "done": False})

    def observe(self, etype, amount=0, platform="twitch", eid=None):
        """a real (non-test) event: follows count 1, subs 1 (gifts: their amount), bits their amount (Twitch only: TikTok gifts and
        YouTube Super Chats are also "cheer" events but are not bits); follow and sub goals count every platform"""
        k = self.cfg["kind"]
        n = 0
        eid = str(eid or "")
        if eid and eid in self.seen:
            return
        if k == "follow" and etype == "follow":
            n = 1
        elif k == "sub" and etype in SUBS:
            n = 1
        elif k == "sub" and etype == "gift":
            n = max(1, int(amount or 1))
        elif k == "bits" and etype == "cheer" and platform == "twitch":
            n = max(0, int(amount or 0))
        if n:
            if eid:
                self.seen.append(eid)
                self.store.kv_set("goal:seen", list(self.seen))
            self.cfg["current"] = min(10**9, self.cfg["current"] + n)
            self._save()
            self._check()

    def _check(self):
        c = self.cfg
        if c["current"] >= c["target"] and not c["done"]:
            c["done"] = True
            self._save()
            self.submit({"type": "goal", "id": f"goal:{c['title']}:{c['target']}:{int(time.time())}", "user": "chat", "message": c["title"], "amount": c["target"]})


HYPE_LOOK = {"label": "Hype train", "c1": "#ff8a1f", "c2": "#ffb35c", "bg": "#14110d", "fg": "#ffffff", "show_after_s": 30, "show_level": True, "show_numbers": True}
_COL = re.compile(r"^#[0-9a-fA-F]{6}$")


class HypeBar:
    """Hype-train progress bar (/obs/hypebar). Fed by hype_start / hype_level / hype_end events ({level, progress, goal, total}) from /api/alerts/fire
    and the Host feed, or by the Host live-state hype object; stays on screen show_after_s seconds after the train ends. Look is editable and stored in kv."""

    def __init__(self, store):
        self.store = store
        self.look = self.clean_look(store.kv_get("hypebar:cfg") or {}, dict(HYPE_LOOK))
        self.st = {"active": False, "level": 0, "progress": 0, "goal": 0, "total": 0, "ended_at": 0}
        saved = store.kv_get("hypebar:st")                 # a restart mid-train keeps the bar where it was
        if isinstance(saved, dict):
            for k in ("level", "progress", "goal", "total"):
                self.st[k] = _int(saved.get(k), 0, 10**9, 0)
            self.st["active"] = bool(saved.get("active"))
            try:
                self.st["ended_at"] = float(saved.get("ended_at") or 0)
            except (TypeError, ValueError):
                pass
        self.seen = deque(store.kv_get("hypebar:seen") or [], maxlen=100)

    @staticmethod
    def clean_look(src, base):
        out = dict(base)
        if isinstance(src, dict):
            if "label" in src:
                out["label"] = re.sub(r"\s+", " ", str(src["label"] or "")).strip()[:40] or base["label"]
            for k in ("c1", "c2", "bg", "fg"):
                if k in src and _COL.match(str(src[k])):
                    out[k] = str(src[k]).lower()
            if "show_after_s" in src:
                out["show_after_s"] = _int(src["show_after_s"], 0, 3600, base["show_after_s"])
            for k in ("show_level", "show_numbers"):
                if k in src:
                    out[k] = bool(src[k])
        return out

    def set_look(self, src):
        self.look = self.clean_look(src, self.look)
        self.store.kv_set("hypebar:cfg", self.look)
        return self.look

    def observe(self, etype, ev):
        """etype hype_start | hype_level | hype_end (or the legacy 'hype' with phase start/end); anything else is ignored"""
        if etype == "hype":
            etype = "hype_end" if str(ev.get("phase") or "") == "end" else "hype_start"
        if etype not in ("hype_start", "hype_level", "hype_end"):
            return
        eid = str(ev.get("id") or "")
        if eid and eid in self.seen:
            return                                          # replayed event (Host re-sent it, or Multi restarted): the bar already has it
        if eid:
            self.seen.append(eid)
            self.store.kv_set("hypebar:seen", list(self.seen))
        s = self.st
        for k in ("level", "progress", "goal", "total"):
            if ev.get(k) not in (None, ""):
                s[k] = _int(ev[k], 0, 10**9, s[k])
        if etype == "hype_start":
            s.update(active=True, ended_at=0)
            s["level"] = s["level"] or 1
        elif etype == "hype_level":
            s.update(active=True, ended_at=0)
        else:
            s.update(active=False, ended_at=time.time())
        self.store.kv_set("hypebar:st", dict(s))

    def view(self, live=None, now=None):
        """what the overlay draws: the Host's live hype object wins while it reports a running train, else the pushed state"""
        now = now or time.time()
        s = dict(self.st)
        if isinstance(live, dict) and live.get("state") in ("begin", "progress"):
            s.update(active=True, ended_at=0, level=_int(live.get("level"), 0, 10**9, s["level"]), progress=_int(live.get("progress"), 0, 10**9, 0),
                     goal=_int(live.get("goal"), 0, 10**9, 0), total=_int(live.get("total"), 0, 10**9, 0))
        after = self.look["show_after_s"]
        visible = bool(s["active"] or (s["ended_at"] and now - s["ended_at"] < after))
        s["pct"] = min(100, int(s["progress"] * 100 / s["goal"])) if s["goal"] else 0
        s["visible"], s["look"] = visible, dict(self.look)
        return s
