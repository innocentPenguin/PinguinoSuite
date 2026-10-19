"""Panes: a chat window with its own filter and look, used for split chat and extra pop-out windows.

A pane is saved by id in the key/value store; the page reads it with ?pane=ID. Filters decide which messages the pane shows
(platforms, chat vs events, roles); `flow` links panes into one continuous feed; `look` is a small per-pane look override."""
import re

import chatstyle

PLATFORMS = chatstyle.PLATFORMS
ROLES = ("streamer", "mod", "vip", "sub", "bot", "viewer")
KINDS = ("all", "chat", "events")
SPLIT_MODES = ("flow", "platform", "events", "people")


def pane_id(v):
    return re.sub(r"[^a-z0-9-]", "", str(v or "").lower())[:24]


def sanitize(src, old=None):
    base = dict(old or {"name": "", "filter": {"platforms": [], "kind": "all", "roles": [], "invert_roles": False},
                        "flow": None, "look": {}, "aot": False, "geom": None})
    s = src if isinstance(src, dict) else {}
    if "name" in s:
        base["name"] = str(s["name"]).strip()[:40]
    if isinstance(s.get("filter"), dict):
        f = s["filter"]
        base["filter"] = {"platforms": [p for p in f.get("platforms", []) if p in PLATFORMS],
                          "kind": f.get("kind") if f.get("kind") in KINDS else "all",
                          "roles": [r for r in f.get("roles", []) if r in ROLES],
                          "invert_roles": bool(f.get("invert_roles", False))}
    if "flow" in s:
        fl = s["flow"]
        base["flow"] = ({"group": pane_id(fl.get("group")) or "split", "order": max(0, min(5, int(fl.get("order", 0))))}
                        if isinstance(fl, dict) else None)
    if "look" in s:
        base["look"] = chatstyle.sanitize_look(s["look"])
    if "aot" in s:
        base["aot"] = bool(s["aot"])
    if isinstance(s.get("geom"), dict):
        g = s["geom"]
        try:
            base["geom"] = {k: int(g[k]) for k in ("x", "y", "w", "h")}
        except (KeyError, TypeError, ValueError):
            pass
    return base


def build_split(mode, platforms=None, aot=False):
    """Two panes for a split. A is the upper/left one, B the lower/right one. Returns {id: pane}."""
    plats = [p for p in (platforms or []) if p in PLATFORMS]
    a = {"name": "Chat A", "aot": aot}
    b = {"name": "Chat B", "aot": aot}
    if mode == "flow":
        a.update(name="Chat (older messages)", flow={"group": "chat-split", "order": 1})
        b.update(name="Chat (newest messages)", flow={"group": "chat-split", "order": 0})
    elif mode == "platform":
        rest = [p for p in PLATFORMS if p not in plats]
        a.update(name="Chat: " + (", ".join(plats) or "twitch"), filter={"platforms": plats or ["twitch"], "kind": "all"})
        b.update(name="Chat: " + (", ".join(rest) or "others"), filter={"platforms": rest, "kind": "all"})
    elif mode == "events":
        a.update(name="Chat", filter={"kind": "chat"})
        b.update(name="Stream events", filter={"kind": "events"})
    elif mode == "people":
        a.update(name="Streamer, mods and VIPs", filter={"roles": ["streamer", "mod", "vip"]})
        b.update(name="Viewers", filter={"roles": ["streamer", "mod", "vip"], "invert_roles": True})
    else:
        raise ValueError("unknown split mode")
    return {"split-a": sanitize(a), "split-b": sanitize(b)}
