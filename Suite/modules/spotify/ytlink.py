"""YouTube links as a *data source only*: read the title/channel (oEmbed), clean it, and score Spotify search results against it. Nothing is played from YouTube."""
import difflib
import json
import re
import urllib.parse
import urllib.request

_ID = r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])"
_URL = re.compile(r"(?<![\w.-])(?:https?://)?(?:(?:www\.|m\.|music\.)?youtube\.com/(?:watch\?(?:[^\s#]*&)?v=|shorts/|live/|embed/|v/)|youtu\.be/)" + _ID, re.I)
_NOISE = re.compile(r"[\(\[\{][^\)\]\}]*?(official|lyric|video|audio|visuali[sz]er|hd|hq|4k|remaster|explicit|clip|music video|mv|m/v)[^\)\]\}]*?[\)\]\}]", re.I)
_TAIL = re.compile(r"\s*[-|:]?\s*(official\s+(music\s+)?(video|audio|lyric video|visuali[sz]er)|lyrics?( video)?|music video|audio|hd|hq|4k)\s*$", re.I)
_FEAT = re.compile(r"[\(\[]?\s*\b(feat\.?|ft\.?|featuring)\b[^\)\]]*[\)\]]?", re.I)


def video_id(text):
    m = _URL.search(text or "")
    return m.group(1) if m else None


def _http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "PinguinoSuite-Spotify/1.0"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode("utf8"))


def fetch_meta(vid, http=None):
    """-> {title, channel} or None. Only ever requests YouTube's oEmbed for this one video id."""
    watch = "https://www.youtube.com/watch?v=" + vid
    try:
        d = (http or _http)("https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": watch, "format": "json"}))
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get("title"):
        return None
    return {"title": str(d["title"]), "channel": str(d.get("author_name") or "")}


def _strip(s):
    s = _NOISE.sub(" ", s)
    s = _FEAT.sub(" ", s)
    prev = None
    while prev != s:
        prev, s = s, _TAIL.sub("", s)
    return re.sub(r"\s+", " ", s).strip(" -|:·")


def clean(title, channel=""):
    """-> (song, artist). "Artist - Song (Official Video)" is split; otherwise the (cleaned) channel is the artist."""
    t = _strip(title)
    ch = re.sub(r"(?i)\s*(-\s*topic|vevo|official( channel)?)\s*$", "", channel or "").strip()
    if " - " in t:
        a, _, b = t.partition(" - ")
        return _strip(b), _strip(a)
    return t, ch


def _norm(s):
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if a in b or b in a:
        r = max(r, 0.9 if min(len(a), len(b)) >= 3 else r)
    return r


def score(song, artist, track):
    """0-100 for a Spotify track dict ({name, artists}) against the cleaned YouTube data."""
    ts = _sim(song, _strip(track.get("name", "")))
    arts = track.get("artists") or []
    asim = max([_sim(artist, a) for a in arts] or [0.0]) if artist else 0.5      # unknown artist: neutral
    if artist and song and any(_norm(a) and _norm(a) in _norm(song) for a in arts):
        asim = max(asim, 0.8)
    return round(100 * (0.65 * ts + 0.35 * asim))


def best_match(song, artist, search, min_score):
    """search(query)->tracks. -> (track|None, score, query)."""
    best, bs, bq = None, 0, ""
    for q in dict.fromkeys(x for x in (f"{artist} {song}".strip(), song) if x):
        for t in search(q):
            sc = score(song, artist, t)
            if sc > bs:
                best, bs, bq = t, sc, q
        if bs >= max(min_score, 90):
            break
    return (best if bs >= min_score else None), bs, bq
