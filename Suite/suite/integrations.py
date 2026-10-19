"""Integrations hub: one list of every outside connection (Twitch, Spotify, Discord, Tailscale/Link devices, OBS, Streamer.bot,
the site, API keys) with a status. Modules feed it generically (see Docs/MODULE_CONTRACT.md, "Integrations"):
  1. manifest "integrations": "/api/integrations"  -> {"items": [...]}      (preferred)
  2. a status JSON with "connectors": [...]                                   (Multi's shape)
  3. otherwise the module's last pre-stream items are shown as its connection list.
Item: {id, module, group, name, status: connected|needs_auth|error|off|unknown, detail, connect_url?, test?: "/api/..." (POST), page?: bool}
"""
import json
import re
import socket
from pathlib import Path

STATUSES = ("connected", "needs_auth", "error", "off", "unknown")
SECRET_KEY = re.compile(r"(key|token|secret|password|passwd|credential)", re.I)


def _status(s):
    s = str(s or "").lower()
    if s in STATUSES:
        return s
    if s in ("ok", "pass", "running", "ready", "online", "up", "connected"):
        return "connected"
    if s in ("needs_auth", "auth", "unauthorized", "no_token", "needs-auth", "warn"):
        return "needs_auth"
    if s in ("fail", "failed", "bad", "down", "offline"):
        return "error"
    return "unknown"


def clean_item(mid, it, group=None):
    if not isinstance(it, dict):
        return None
    out = {"id": f"{mid}:{str(it.get('id', it.get('name', '')))[:40]}", "module": mid, "group": str(it.get("group") or group or mid)[:40],
           "name": str(it.get("name") or it.get("label") or it.get("id") or "")[:60], "status": _status(it.get("status")),
           "detail": str(it.get("detail", ""))[:200]}
    url = str(it.get("connect_url") or "")
    if url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        out["connect_url"], out["connect_label"] = url, str(it.get("connect_label") or "Connect")[:20]
    t = str(it.get("test") or "")
    if t.startswith("/api/") and ".." not in t:
        out["test"] = t
    return out if out["name"] else None


def from_items(mid, data, group=None):
    items = (data.get("items") if isinstance(data, dict) else None) or []
    return [x for x in (clean_item(mid, i, group) for i in items[:60]) if x]


def from_connectors(mid, status):
    """Multi-style status JSON: connectors [{platform, label, status, detail}] and an optional twitch_connect_url."""
    out = []
    for c in (status.get("connectors") or [])[:30]:
        st = _status(c.get("status"))
        it = {"id": c.get("platform"), "name": c.get("label") or c.get("platform"), "status": st, "detail": c.get("detail", "")}
        if st == "needs_auth" and c.get("platform") == "twitch" and status.get("twitch_connect_url"):
            it["connect_url"], it["connect_label"] = status["twitch_connect_url"], "Connect Twitch"
        x = clean_item(mid, it, group="Chat platforms")
        if x:
            out.append(x)
    return out


def from_prestream(mid, report_items):
    return [x for x in (clean_item(mid, {"id": i.get("id"), "name": i.get("label"), "status": i.get("status"), "detail": i.get("detail")}) for i in report_items if i.get("module") == mid and i.get("id") != "up") if x]


def tcp(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def from_link_status(status):
    """Link /api/status -> Tailscale + one row per paired device."""
    out = []
    ts = status.get("tailscale") or {}
    st = str(ts.get("state", "")).lower()
    out.append(clean_item("link", {"id": "tailscale", "name": "Tailscale", "group": "Devices & network",
                                   "status": "connected" if st == "running" else "off" if st in ("stopped", "needsmachineauth", "nostate") else "unknown",
                                   "detail": (ts.get("self") or {}).get("name", "") if st == "running" else (ts.get("error") or ts.get("state") or "not running")[:120]}))
    for p in (status.get("peers") or [])[:20]:
        out.append(clean_item("link", {"id": "peer-" + str(p.get("name", p.get("id", ""))), "name": f"Device: {p.get('name', p.get('id', '?'))}", "group": "Devices & network",
                                       "status": "connected" if p.get("online") or p.get("alive") else "off", "detail": p.get("detail", "")}))
    return [x for x in out if x]


def secrets_presence(files):
    """Which API keys / tokens are set, never their values. files = [(label, Path)]."""
    out = []
    for label, p in files:
        try:
            obj = json.loads(Path(p).read_text("utf8"))
        except (OSError, ValueError):
            continue
        def walk(o, prefix=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, (dict, list)):
                        walk(v, prefix + k + ".")
                    elif isinstance(v, str) and SECRET_KEY.search(k):
                        yield (prefix + k, bool(v.strip()))
            elif isinstance(o, list):
                for i, v in enumerate(o[:20]):
                    yield from walk(v, prefix + f"{i}.")
        for key, has in walk(obj):
            out.append({"id": f"keys:{label}:{key}", "module": "core", "group": "API keys", "name": f"{label}: {key}",
                        "status": "connected" if has else "needs_auth", "detail": "set" if has else "not set"})
    return out
