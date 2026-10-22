"""Lyrics lookup via LRCLIB (free, no key). Only artist/title/duration are sent; results are cached."""
import json
import re
import urllib.parse
import urllib.request

_cache = {}


def _http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "PinguinoSuite-Spotify/1.0"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode("utf8"))


def parse_lrc(text):
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"\s*\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)", line)
        if m:
            out.append({"t": int((int(m.group(1)) * 60 + float(m.group(2))) * 1000), "text": m.group(3).strip()})
    return out


def lookup(artist, title, duration_ms=0, http=None):
    key = (artist or "").lower(), (title or "").lower()
    if key in _cache:
        return _cache[key]
    res = {"found": False, "synced": [], "plain": ""}
    if title:
        q = {"artist_name": artist, "track_name": title}
        if duration_ms:
            q["duration"] = round(duration_ms / 1000)
        try:
            d = (http or _http)("https://lrclib.net/api/get?" + urllib.parse.urlencode(q))
            if isinstance(d, dict):
                res = {"found": bool(d.get("syncedLyrics") or d.get("plainLyrics")), "synced": parse_lrc(d.get("syncedLyrics")),
                       "plain": d.get("plainLyrics") or ""}
        except Exception:
            return res          # transient failure: do not cache
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = res
    return res
