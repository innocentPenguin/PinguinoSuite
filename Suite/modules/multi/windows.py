"""Window manager: persisted window layouts, profiles, monitor/DPI recovery, and the Edge --app shell.

The shell is an interface (Shell.open/close/monitors) so a native shell (Unit 01) can replace Edge later.
Geometry is stored in virtual-desktop pixels plus the monitor it was on and its position relative to
that monitor, so a disconnected monitor snaps to the nearest one and the original is restored on reconnect.
"""
import ctypes
import os
import subprocess
import uuid

WINDOW_TYPES = ("unified", "platform", "priority", "missed", "first", "composer", "status")

WINDOW_DEFAULTS = {
    "type": "unified", "title": "", "x": 100, "y": 100, "w": 480, "h": 700,
    "monitor": "primary", "rel": None,          # rel = (fx, fy, fw, fh) fractions of the monitor work area
    "dpi_scale": 1.0, "platforms": [], "min_tier": "none", "channels": [],
    "font_size": 14, "spacing": 4, "opacity": 1.0, "theme": "dark", "always_on_top": False,
    "visible": True, "scroll": "auto", "preset": "default", "link_group": "", "link_order": 0,
}

PROFILE_DEFAULTS = {
    "Streaming": [
        {"type": "priority", "x": 1500, "y": 40, "w": 400, "h": 520, "always_on_top": True, "opacity": 0.95},
        {"type": "unified", "x": 1500, "y": 570, "w": 400, "h": 460, "min_tier": "low"},
    ],
    "Gaming": [{"type": "priority", "x": 1580, "y": 40, "w": 320, "h": 360, "always_on_top": True, "opacity": 0.85}],
    "Editing": [{"type": "unified", "x": 40, "y": 40, "w": 520, "h": 900}, {"type": "priority", "x": 580, "y": 40, "w": 420, "h": 600}],
    "IRL": [{"type": "priority", "x": 20, "y": 40, "w": 360, "h": 600, "font_size": 18}],
    "Minimal": [{"type": "priority", "x": 1600, "y": 40, "w": 300, "h": 300, "min_tier": "high", "opacity": 0.8, "always_on_top": True}],
    "Full Monitoring": [
        {"type": "unified", "x": 0, "y": 0, "w": 640, "h": 1000},
        {"type": "priority", "x": 650, "y": 0, "w": 420, "h": 700},
        {"type": "missed", "x": 650, "y": 710, "w": 420, "h": 290},
        {"type": "composer", "x": 1080, "y": 800, "w": 500, "h": 200},
        {"type": "status", "x": 1080, "y": 0, "w": 360, "h": 240},
    ],
}


def new_window(**kw):
    w = dict(WINDOW_DEFAULTS)
    w.update({k: v for k, v in kw.items() if k in WINDOW_DEFAULTS})
    w["id"] = kw.get("id") or uuid.uuid4().hex[:8]
    if w["type"] not in WINDOW_TYPES:
        w["type"] = "unified"
    return w


def _intersect(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))


def place(w, monitors):
    """Return window geometry adjusted for the CURRENT monitors. `monitors` = [{id,x,y,w,h,scale,primary}].
    Never mutates the saved geometry; the saved original is what restores when the monitor comes back."""
    if not monitors:
        return {k: w[k] for k in ("x", "y", "w", "h")}
    by_id = {m["id"]: m for m in monitors}
    primary = next((m for m in monitors if m.get("primary")), monitors[0])
    rect = (w["x"], w["y"], w["w"], w["h"])
    mon = by_id.get(w.get("monitor"))
    if mon is None and w.get("monitor") not in (None, "primary"):
        # our monitor is gone: nearest by overlap, else primary
        best = max(monitors, key=lambda m: _intersect(rect, (m["x"], m["y"], m["w"], m["h"])))
        mon = best if _intersect(rect, (best["x"], best["y"], best["w"], best["h"])) > 0 else primary
        fx, fy = (w["rel"][0], w["rel"][1]) if w.get("rel") else (0.1, 0.1)
        x, y = mon["x"] + int(fx * mon["w"]), mon["y"] + int(fy * mon["h"])
    elif mon is not None and w.get("rel"):
        fx, fy, fw, fh = w["rel"]
        x, y = mon["x"] + int(fx * mon["w"]), mon["y"] + int(fy * mon["h"])
        scale_ratio = mon.get("scale", 1.0) / (w.get("dpi_scale") or 1.0)
        return _clamp(x, y, int(w["w"] * scale_ratio), int(w["h"] * scale_ratio), mon)
    else:
        mon = mon or primary
        x, y = w["x"], w["y"]
    return _clamp(x, y, w["w"], w["h"], mon)


def _clamp(x, y, ww, hh, mon):
    ww, hh = min(ww, mon["w"]), min(hh, mon["h"])
    x = max(mon["x"], min(x, mon["x"] + mon["w"] - ww))
    y = max(mon["y"], min(y, mon["y"] + mon["h"] - hh))
    return {"x": x, "y": y, "w": ww, "h": hh}


def describe_geometry(w, monitors):
    """Fill monitor/rel/dpi_scale from absolute x/y/w/h so the layout survives monitor changes."""
    if not monitors:
        return w
    rect = (w["x"], w["y"], w["w"], w["h"])
    mon = max(monitors, key=lambda m: _intersect(rect, (m["x"], m["y"], m["w"], m["h"])))
    w["monitor"] = mon["id"]
    w["rel"] = [(w["x"] - mon["x"]) / mon["w"], (w["y"] - mon["y"]) / mon["h"], w["w"] / mon["w"], w["h"] / mon["h"]]
    w["dpi_scale"] = mon.get("scale", 1.0)
    return w


def list_monitors():
    """Enumerate monitors via Win32 (ctypes, no extra deps). Empty list on non-Windows / failure."""
    if os.name != "nt":
        return []
    try:
        user32, shcore = ctypes.windll.user32, ctypes.windll.shcore
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        out = []

        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

        class MI(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("mon", RECT), ("work", RECT), ("flags", ctypes.c_ulong),
                        ("dev", ctypes.c_wchar * 32)]

        PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_double)

        def cb(hmon, _hdc, _r, _d):
            mi = MI()
            mi.cb = ctypes.sizeof(MI)
            user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            try:
                shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))
                scale = dx.value / 96 if dx.value else 1.0
            except Exception:
                scale = 1.0
            wk = mi.work
            out.append({"id": mi.dev, "x": wk.l, "y": wk.t, "w": wk.r - wk.l, "h": wk.b - wk.t,
                        "scale": round(scale, 2), "primary": bool(mi.flags & 1)})
            return 1

        user32.EnumDisplayMonitors(0, 0, PROC(cb), 0)
        return out
    except Exception:
        return []


class EdgeShell:
    """Opens each window as an Edge --app window pointed at the local UI. Limits (documented): Edge cannot be
    click-through, and always-on-top is applied afterwards through Win32. A native shell removes both limits."""

    EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    def __init__(self, base_url):
        self.base, self.procs = base_url, {}

    def open(self, w, geom):
        if self.is_open(w["id"]):
            return
        exe = self.EDGE if os.path.exists(self.EDGE) else "msedge.exe"
        profile = os.path.join(os.environ.get("TEMP", "."), "pinguinomulti-edge", w["id"])
        url = f"{self.base}/?win={w['id']}"
        try:
            self.procs[w["id"]] = subprocess.Popen(
                [exe, f"--app={url}", f"--window-position={geom['x']},{geom['y']}",
                 f"--window-size={geom['w']},{geom['h']}", f"--user-data-dir={profile}", "--no-first-run"])
        except Exception as e:
            print("cannot open window:", e, flush=True)

    def is_open(self, wid):
        p = self.procs.get(wid)
        return bool(p and p.poll() is None)

    def close(self, wid):
        p = self.procs.pop(wid, None)
        if p and p.poll() is None:
            p.terminate()
