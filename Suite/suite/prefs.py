"""Per-device UI preferences (theme, layout, nav, dashboard cards, sounds, saved profiles). Stored in <data dir>/prefs.json, which is
per device by design (the data dir is not shared between devices; export/import moves them). Everything coming from the UI is
whitelisted and bounded here: unknown keys are dropped, colours must look like colours, so a bad file can never inject CSS."""
import json
import os
import re
import threading
from pathlib import Path

_lock = threading.Lock()
HEX = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
ROUTE = re.compile(r"^[\w:@.-]{1,40}$")
VAR = re.compile(r"^--[a-z0-9-]{1,24}$")
NAME = re.compile(r"^[^\x00-\x1f<>]{1,40}$")

ENUMS = {
    "preset": ["penguin", "midnight", "forest", "violet", "rose", "ice", "contrast", "paper", "custom"],
    "radius": ["sharp", "round", "pill"],
    "density": ["comfortable", "compact"],
    "motion": ["full", "calm"],
    "sidebar": ["full", "icons", "hidden"],
    "tone": ["chime", "ping", "soft", "pop"],
    "hours": ["auto", "12", "24"],
}
DASH_ORDER = ["listen", "modules", "activity", "prestream", "chatrate"]
DASH_FULL = ["hero", "devices", "tiles"]
TILES = ["t_stream", "t_chat", "t_devices", "t_modules", "t_prestream", "t_errors"]
SOUND_EVENTS = ["golive", "prestream_fail", "prestream_ok", "error", "module_down", "act_follow", "act_sub", "act_raid", "act_cheer", "act_redeem"]

DEFAULTS = {
    "v": 1,
    "theme": {"preset": "penguin", "accent": "", "radius": "round", "density": "comfortable", "motion": "full", "zoom": 100, "vars": {}},
    "layout": {"sidebar": "full", "start": "dashboard", "nav_hidden": [], "nav_order": []},
    "dash": {"full": list(DASH_FULL), "cards": list(DASH_ORDER), "tiles": list(TILES), "hidden": []},
    "sound": {"on": False, "volume": 50, "tone": "chime", "events": {"golive": True, "prestream_fail": True, "prestream_ok": False, "error": False, "module_down": False, "act_follow": False, "act_sub": False, "act_raid": False, "act_cheer": False, "act_redeem": False}},
    "notify": {"toasts": True, "desktop": True},
    "time": {"hours": "auto"},
    "text": {"app_name": "PinguinoSuite", "idle_title": "Ready when you are", "live_pill": "LIVE", "offline_pill": "Offline"},   # wording the user may change
    "thresholds": {"errors_min": 30, "tile_errors_hide_zero": False},
    "profiles": {},
    "auto": {"live": "", "idle": ""},
}


def _enum(v, key, default):
    return v if v in ENUMS[key] else default


def _ids(v, allowed, default):
    """A list of ids: only known ones, no duplicates; missing known ones are appended so a new card shows up after an update."""
    out = []
    for x in v if isinstance(v, list) else []:
        if x in allowed and x not in out:
            out.append(x)
    return out + [a for a in default if a not in out]


def _routes(v, cap=60):
    return [x for x in (v if isinstance(v, list) else [])[:cap] if isinstance(x, str) and ROUTE.match(x)]


def clean(p, _depth=0):
    """Return a fully-populated, validated prefs dict from untrusted input (missing -> defaults)."""
    p = p if isinstance(p, dict) else {}
    d = json.loads(json.dumps(DEFAULTS))
    t, th = p.get("theme") if isinstance(p.get("theme"), dict) else {}, d["theme"]
    th["preset"] = _enum(t.get("preset"), "preset", th["preset"])
    th["accent"] = t["accent"] if isinstance(t.get("accent"), str) and HEX.match(t["accent"]) else ""
    th["radius"] = _enum(t.get("radius"), "radius", th["radius"])
    th["density"] = _enum(t.get("density"), "density", th["density"])
    th["motion"] = _enum(t.get("motion"), "motion", th["motion"])
    try:
        th["zoom"] = max(80, min(160, int(t.get("zoom", 100))))
    except (TypeError, ValueError):
        pass
    if isinstance(t.get("vars"), dict):   # computed palette the shell sends; the core serves it to module pages through /theme.css
        th["vars"] = {k: v for k, v in list(t["vars"].items())[:40] if isinstance(k, str) and VAR.match(k) and isinstance(v, str) and (HEX.match(v) or re.match(r"^(rgba?\([\d\s.,%]+\)|[0-9.]+px)$", v))}
    la, ly = p.get("layout") if isinstance(p.get("layout"), dict) else {}, d["layout"]
    ly["sidebar"] = _enum(la.get("sidebar"), "sidebar", ly["sidebar"])
    ly["start"] = la["start"] if isinstance(la.get("start"), str) and ROUTE.match(la["start"]) else "dashboard"
    ly["nav_hidden"] = _routes(la.get("nav_hidden"))
    ly["nav_order"] = _routes(la.get("nav_order"))
    da, dd = p.get("dash") if isinstance(p.get("dash"), dict) else {}, d["dash"]
    dd["full"] = _ids(da.get("full"), DASH_FULL, DASH_FULL)
    dd["cards"] = _ids(da.get("cards"), DASH_ORDER, DASH_ORDER)
    dd["tiles"] = _ids(da.get("tiles"), TILES, TILES)
    dd["hidden"] = [x for x in (da.get("hidden") if isinstance(da.get("hidden"), list) else []) if x in DASH_FULL + DASH_ORDER + TILES]
    so, sd = p.get("sound") if isinstance(p.get("sound"), dict) else {}, d["sound"]
    sd["on"] = bool(so.get("on"))
    try:
        sd["volume"] = max(0, min(100, int(so.get("volume", 50))))
    except (TypeError, ValueError):
        pass
    sd["tone"] = _enum(so.get("tone"), "tone", sd["tone"])
    if isinstance(so.get("events"), dict):
        for k in SOUND_EVENTS:
            if k in so["events"]:
                sd["events"][k] = bool(so["events"][k])
    no = p.get("notify") if isinstance(p.get("notify"), dict) else {}
    d["notify"] = {"toasts": bool(no.get("toasts", True)), "desktop": bool(no.get("desktop", True))}
    d["time"]["hours"] = _enum((p.get("time") or {}).get("hours") if isinstance(p.get("time"), dict) else None, "hours", "auto")
    tx = p.get("text") if isinstance(p.get("text"), dict) else {}
    for k, mx in (("app_name", 24), ("idle_title", 60), ("live_pill", 14), ("offline_pill", 14)):
        v = tx.get(k)
        d["text"][k] = v.strip()[:mx] if isinstance(v, str) and v.strip() and NAME.match(v.strip()[:mx]) else d["text"][k]
    th2 = p.get("thresholds") if isinstance(p.get("thresholds"), dict) else {}
    try:
        d["thresholds"]["errors_min"] = max(5, min(240, int(th2.get("errors_min", 30))))
    except (TypeError, ValueError):
        pass
    d["thresholds"]["tile_errors_hide_zero"] = bool(th2.get("tile_errors_hide_zero"))
    if _depth == 0 and isinstance(p.get("profiles"), dict):   # saved looks ("Streaming", "Editing"...): each is itself a cleaned prefs without profiles
        for name, snap in list(p["profiles"].items())[:12]:
            if isinstance(name, str) and NAME.match(name) and isinstance(snap, dict):
                s = clean({**snap, "profiles": {}}, 1)
                s.pop("profiles", None)
                s.pop("auto", None)
                d["profiles"][name] = s
    au = p.get("auto") if isinstance(p.get("auto"), dict) else {}
    d["auto"] = {k: (au[k] if isinstance(au.get(k), str) and au[k] in d["profiles"] else "") for k in ("live", "idle")}
    if _depth:
        d.pop("profiles", None)
    return d


class Prefs:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        for f in (self.path, self.path.with_name(self.path.name + ".bak")):
            try:
                return clean(json.loads(f.read_text("utf8")))
            except (OSError, ValueError):
                continue
        return clean({})

    def save(self, p):
        c = clean(p)
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(c, indent=1), "utf8")
            if self.path.exists():
                try:
                    os.replace(self.path, self.path.with_name(self.path.name + ".bak"))
                except OSError:
                    pass
            os.replace(tmp, self.path)
        return c

    def reset(self):
        return self.save({})

    def css(self):
        """:root{...} overrides for module pages that link /theme.css (empty when the user kept the default palette)."""
        v = self.load()["theme"]["vars"]
        return ":root{" + ";".join(f"{k}:{x}" for k, x in v.items()) + "}" if v else ""
