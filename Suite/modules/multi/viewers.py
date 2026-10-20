"""Live viewer counts per platform, polled every 30 s and pushed to the pages as {"type": "viewers", "counts": {...}}.
Twitch: Helix streams (needs the Twitch token Multi already has). YouTube: the active broadcast's concurrentViewers.
TikTok: the unofficial client's room count when it reports one. Kick/Discord: no count (shown as a dash). Read-only, never raises."""
import asyncio
import time

import requests

import config
import secrets_store

counts = {}      # platform -> {"n": int|None, "live": bool, "ts": float}


def _twitch(conn):
    tok = conn.tokens()
    if not tok or conn.describe().get("status") != "connected":
        return None
    r = requests.get("https://api.twitch.tv/helix/streams", params={"user_login": config.settings()["channel"].lstrip("#")}, headers=conn._headers(tok), timeout=10)
    if r.status_code != 200:
        return None
    d = r.json().get("data") or []
    return {"n": int(d[0]["viewer_count"]), "live": True} if d else {"n": 0, "live": False}


def _youtube(conn):
    vid, tok = getattr(conn, "video_id", None), secrets_store.get("youtube_token")
    if not vid or not tok:
        return None
    r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "liveStreamingDetails", "id": vid}, headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    if r.status_code != 200:
        return None
    it = (r.json().get("items") or [{}])[0].get("liveStreamingDetails", {})
    return {"n": int(it["concurrentViewers"]), "live": True} if "concurrentViewers" in it else {"n": 0, "live": False}


def _tiktok(conn):
    n = conn.state.get("viewers")
    return {"n": int(n), "live": True} if n is not None else None


async def run(connectors, emit):
    fns = {"twitch": _twitch, "youtube": _youtube, "tiktok": _tiktok}
    while True:
        for p, fn in fns.items():
            if p not in connectors:
                continue
            try:
                r = await asyncio.to_thread(fn, connectors[p])
            except Exception:
                r = None
            if r is None:
                counts.pop(p, None)
            else:
                counts[p] = dict(r, ts=time.time())
        emit({"type": "viewers", "counts": counts})
        await asyncio.sleep(30)
