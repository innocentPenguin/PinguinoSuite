"""Stream goal bar: one goal (title, target, current) that fills by hand or from live events (follows, subs, bits). Shown at /obs/goal;
reaching the target fires one "goal" alert. Stored in the kv table, so it survives restarts."""
import re
import time

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

    def observe(self, etype, amount=0):
        """a real (non-test) event: follows count 1, subs 1 (gifts: their amount), bits their amount"""
        k = self.cfg["kind"]
        n = 0
        if k == "follow" and etype == "follow":
            n = 1
        elif k == "sub" and etype in SUBS:
            n = 1
        elif k == "sub" and etype == "gift":
            n = max(1, int(amount or 1))
        elif k == "bits" and etype == "cheer":
            n = max(0, int(amount or 0))
        if n:
            self.cfg["current"] = min(10**9, self.cfg["current"] + n)
            self._save()
            self._check()

    def _check(self):
        c = self.cfg
        if c["current"] >= c["target"] and not c["done"]:
            c["done"] = True
            self._save()
            self.submit({"type": "goal", "id": f"goal:{c['title']}:{c['target']}:{int(time.time())}", "user": "chat", "message": c["title"], "amount": c["target"]})
