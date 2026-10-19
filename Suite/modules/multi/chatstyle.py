"""Chat look: fonts, backgrounds, name colours and highlight styles per platform / role / event, saved in settings.json.

The browser compiles this into one stylesheet (static/style.js) so styling costs nothing per message, even in a busy chat.
Everything is validated here: only known keys, #rrggbb colours, clamped numbers. Rule precedence (later wins):
base < platform < role < event < keyword."""
import copy
import re

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
PLATFORMS = ("twitch", "youtube", "discord", "tiktok")
ROLES = ("streamer", "mod", "vip", "sub", "new", "returning", "bot")
EVENTS = ("first", "mention", "sub", "resub", "gift", "cheer", "raid", "follow", "redeem", "highlighted",
          "announcement", "pinned", "modaction")
FAMILIES = ("system-ui", "Segoe UI", "Inter", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Georgia", "Times New Roman",
            "Consolas", "Courier New", "Comic Sans MS", "Impact")


def rule(bg="", bgA=100, bg2="", text="", name="", bold=False, border="", borderW=0, size=100, italic=False, on=True):
    return {"on": on, "bg": bg, "bgA": bgA, "bg2": bg2, "bg2A": bgA, "text": text, "name": name, "bold": bold,
            "border": border, "borderA": 100, "borderW": borderW, "size": size, "italic": italic}


DEFAULT_STYLE = {
    "base": {"family": "system-ui", "size": 14, "weight": 400, "line": 1.35, "spacing": 4, "nameWeight": 700,
             "bg": "#09090a", "bgA": 0, "text": "#ececef", "timestamps": True, "badges": True, "platformTag": True,
             "emoteSize": 150, "radius": 6, "marker": "text"},   # marker: text | logo | both | none
    "platform": {
        "twitch": rule(border="#9146ff", borderW=0),
        "youtube": rule(border="#ff4d4d", borderW=0),
        "discord": rule(border="#5865f2", borderW=0),
        "tiktok": rule(border="#25f4ee", borderW=0),
    },
    "role": {
        "streamer": rule(bg="#ff9900", bgA=14, name="#ffb84d", bold=True),
        "mod": rule(bg="#3ddc97", bgA=8, name="#6ee7b7"),
        "vip": rule(bg="#ff5ca8", bgA=8, name="#ff8ec4"),
        "sub": rule(bg="#ffc94d", bgA=6),
        "new": rule(bg="#3ddc97", bgA=12),
        "returning": rule(bg="#9fb4c7", bgA=10),
        "bot": rule(text="#8f9099", italic=True, size=92),
    },
    "event": {
        "first": rule(bg="#3ddc97", bgA=18, border="#3ddc97", borderW=4, bold=True),
        "mention": rule(bg="#ff9900", bgA=22, border="#ff9900", borderW=4),
        "sub": rule(bg="#ffc94d", bgA=22, bg2="#ff9900", border="#ffc94d", borderW=4, bold=True),
        "resub": rule(bg="#ffc94d", bgA=26, bg2="#ff9900", border="#ffc94d", borderW=4, bold=True),
        "gift": rule(bg="#ff5ca8", bgA=26, bg2="#ff9900", border="#ff5ca8", borderW=4, bold=True),
        "cheer": rule(bg="#e8d44d", bgA=24, bg2="#ff9900", border="#e8d44d", borderW=4, bold=True),
        "raid": rule(bg="#ff4d4d", bgA=26, bg2="#ff9900", border="#ff4d4d", borderW=4, bold=True),
        "follow": rule(bg="#3ddc97", bgA=16, border="#3ddc97", borderW=4),
        "redeem": rule(bg="#25f4ee", bgA=14, border="#25f4ee", borderW=4),
        "highlighted": rule(bg="#ffc94d", bgA=20, border="#ffc94d", borderW=4),
        "announcement": rule(bg="#9fb4c7", bgA=16, border="#9fb4c7", borderW=4),
        "pinned": rule(bg="#ff9900", bgA=12, border="#ff9900", borderW=4),
        "modaction": rule(bg="#ff4d4d", bgA=14, border="#ff4d4d", borderW=4),
    },
    "marker": {p: {"size": 14, "color": ""} for p in PLATFORMS},   # platform logo size (px) and colour ("" = brand colour)
    "keywords": [],      # [{"word": "giveaway", "rule": {...}}] up to 20; a match highlights the message
}


def _color(v, default=""):
    return v if isinstance(v, str) and (HEX.match(v) or v == "") else default


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _rule(src, base):
    out = dict(base)
    if not isinstance(src, dict):
        return out
    out["on"] = bool(src.get("on", base["on"]))
    for k in ("bg", "bg2", "text", "name", "border"):
        out[k] = _color(src.get(k, base[k]), base[k])
    for k in ("bgA", "bg2A", "borderA"):
        out[k] = int(_num(src.get(k, base[k]), 0, 100, base[k]))
    out["borderW"] = int(_num(src.get("borderW", base["borderW"]), 0, 12, base["borderW"]))
    out["size"] = int(_num(src.get("size", base["size"]), 60, 250, base["size"]))
    out["bold"] = bool(src.get("bold", base["bold"]))
    out["italic"] = bool(src.get("italic", base["italic"]))
    return out


def sanitize(user):
    """Merge a (possibly partial / hostile) style dict over the defaults and return a clean, complete one."""
    user = user if isinstance(user, dict) else {}
    out = copy.deepcopy(DEFAULT_STYLE)
    b, ub = out["base"], user.get("base") if isinstance(user.get("base"), dict) else {}
    fam = str(ub.get("family", b["family"]))
    b["family"] = fam if fam in FAMILIES else b["family"]
    b["size"] = int(_num(ub.get("size", b["size"]), 9, 48, b["size"]))
    b["weight"] = int(_num(ub.get("weight", b["weight"]), 300, 900, b["weight"]) // 100 * 100)
    b["line"] = round(_num(ub.get("line", b["line"]), 1.0, 2.2, b["line"]), 2)
    b["spacing"] = int(_num(ub.get("spacing", b["spacing"]), 0, 20, b["spacing"]))
    b["nameWeight"] = int(_num(ub.get("nameWeight", b["nameWeight"]), 300, 900, b["nameWeight"]) // 100 * 100)
    b["bg"] = _color(ub.get("bg", b["bg"]), b["bg"]) or b["bg"]
    b["bgA"] = int(_num(ub.get("bgA", b["bgA"]), 0, 100, b["bgA"]))
    b["text"] = _color(ub.get("text", b["text"]), b["text"]) or b["text"]
    b["emoteSize"] = int(_num(ub.get("emoteSize", b["emoteSize"]), 80, 300, b["emoteSize"]))
    b["radius"] = int(_num(ub.get("radius", b["radius"]), 0, 24, b["radius"]))
    b["marker"] = ub.get("marker") if ub.get("marker") in ("text", "logo", "both", "none") else b["marker"]
    um = user.get("marker") if isinstance(user.get("marker"), dict) else {}
    for plat in PLATFORMS:
        mk = um.get(plat) if isinstance(um.get(plat), dict) else {}
        out["marker"][plat] = {"size": int(_num(mk.get("size", 14), 10, 40, 14)), "color": _color(mk.get("color", ""), "")}
    for k in ("timestamps", "badges", "platformTag"):
        b[k] = bool(ub.get(k, b[k]))
    for section, keys in (("platform", PLATFORMS), ("role", ROLES), ("event", EVENTS)):
        us = user.get(section) if isinstance(user.get(section), dict) else {}
        for k in keys:
            out[section][k] = _rule(us.get(k), out[section][k])
    kws = []
    for item in (user.get("keywords") or [])[:20]:
        if isinstance(item, dict) and str(item.get("word", "")).strip():
            kws.append({"word": str(item["word"]).strip()[:40],
                        "rule": _rule(item.get("rule"), rule(bg="#ff9900", bgA=22, border="#ff9900", borderW=4))})
    out["keywords"] = kws
    return out
