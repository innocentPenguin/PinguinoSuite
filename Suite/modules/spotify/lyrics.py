"""Lyrics lookup via LRCLIB (free, no key). Only artist/title/duration are sent; results are cached (also "no lyrics")."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

LRCLIB = os.environ.get("SPOTIFY_LRCLIB") or "https://lrclib.net/api/get"      # e2e points this at a fake
_cache = {}                 # key -> (expires_at or 0 = forever, result)
_lock = threading.Lock()
RETRY_S = 60                # after a network failure: no new lookup for this long
_now = time.time


class NotFound(Exception):
    pass


def _http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "PinguinoSuite-Spotify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read(1_000_000).decode("utf8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound() from None
        raise


def parse_lrc(text):
    out = []
    for line in (text or "").splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", line)
        if not stamps:
            continue
        body = re.sub(r"^(?:\s*\[\d+:\d+(?:\.\d+)?\])+", "", line).strip()
        for mm, ss in stamps:
            out.append({"t": int((int(mm) * 60 + float(ss)) * 1000), "text": body})
    out.sort(key=lambda x: x["t"])
    return out


def _copy(res):
    return {"found": res["found"], "synced": list(res["synced"]), "plain": res["plain"]}


def lookup(artist, title, duration_ms=0, http=None):
    artist, title = str(artist or ""), str(title or "")
    key = artist.lower(), title.lower()
    with _lock:
        hit = _cache.get(key)
        if hit and (not hit[0] or hit[0] > _now()):
            return _copy(hit[1])
    res, ttl = {"found": False, "synced": [], "plain": ""}, 0
    if title and artist:
        q = {"artist_name": artist, "track_name": title}
        if duration_ms:
            q["duration"] = round(duration_ms / 1000)
        try:
            d = (http or _http)(LRCLIB + "?" + urllib.parse.urlencode(q))
            if isinstance(d, dict):
                res = {"found": bool(d.get("syncedLyrics") or d.get("plainLyrics")), "synced": parse_lrc(d.get("syncedLyrics")),
                       "plain": d.get("plainLyrics") or ""}
        except NotFound:
            pass                                    # LRCLIB has none: remembered for good
        except Exception:
            ttl = _now() + RETRY_S                  # transient: remembered briefly so overlay polls don't hammer LRCLIB
    with _lock:
        if len(_cache) > 200:
            _cache.clear()
        _cache[key] = (ttl, res)
    return _copy(res)
