"""Real Twitch chat badge images for the OBS chat overlay: Helix global + channel badge sets, cached for an hour.

Read-only use of the Twitch connector's token. Failure returns what we had (or {}): the overlay then falls back to text pills.
Related: obs.py (look settings), server.py (/api/obs/badges), static/obs.html (renders them).
"""
import threading
import time

import requests

HELIX = "https://api.twitch.tv/helix"
TTL, RETRY = 3600.0, 60.0
_lock = threading.Lock()
_cache = {"at": 0.0, "ttl": 0.0, "data": {}}


def _sets(rows):
    out = {}
    for s in rows or []:
        vers = {}
        for v in s.get("versions") or []:
            url = v.get("image_url_2x") or v.get("image_url_1x") or ""
            if v.get("id") is not None and url.startswith("https://"):
                vers[str(v["id"])] = url
        if s.get("set_id") and vers:
            out[s["set_id"]] = vers
    return out


def fetch(headers, broadcaster_id, get=requests.get):
    """{set_id: {version: image_url}}; channel sets (sub months, bits tiers) override the global ones."""
    g = get(f"{HELIX}/chat/badges/global", headers=headers, timeout=8)
    data = _sets(g.json().get("data")) if g.status_code == 200 else {}
    if broadcaster_id:
        c = get(f"{HELIX}/chat/badges", headers=headers, params={"broadcaster_id": broadcaster_id}, timeout=8)
        if c.status_code == 200:
            data.update(_sets(c.json().get("data")))
    return data


def badges(connector, now=time.time, get=requests.get):
    """Cached badge map for the live Twitch connector; {} while Twitch is not connected."""
    with _lock:
        if now() - _cache["at"] < _cache["ttl"]:
            return _cache["data"]
    data, ttl = _cache["data"], RETRY
    try:
        tok = connector.tokens() if connector else None
        if tok:
            data, ttl = fetch(connector._headers(tok), getattr(connector, "broadcaster_id", None), get) or _cache["data"], TTL
    except Exception:
        pass
    with _lock:
        _cache.update(at=now(), ttl=ttl if data else RETRY, data=data)
    return data
