"""Bot speech filter: the mic hears the bot's own voice (PinguinoVoice / Speak). Voice publishes when it talks
(GET :8772/api/speech-intervals?since=<epoch> -> {"now","speaking","intervals":[[a,b]]}, epoch seconds); a live segment that overlaps one
of those intervals is the bot, not the streamer. When Voice cannot be reached the old speaking.json check is used instead. Never raises."""
import os
import threading
import time

import requests

VOICE_URL = os.environ.get("PINGUINO_VOICE_URL", "http://127.0.0.1:8772")
TIMEOUT = 1.0          # seconds; the ASR loop must never wait on Voice
CACHE_S = 2.0
FAIL_S = 5.0           # after a failed fetch, do not ask Voice again for this long (the fallback answers meanwhile)
FRESH_MARGIN = 0.5     # a cached answer must have been fetched at least this long AFTER the segment ended
OPEN_S = 2.0           # "speaking" with no closed interval yet: treat the last this-many seconds as bot speech
MIN_OVERLAP = 0.05     # seconds; adjacent (touching) speech is not an overlap
PAD_BEFORE = 5.0       # ask for intervals from this long before the oldest segment

_lock = threading.Lock()
_cache = {"at": 0.0, "since": 0.0, "intervals": None, "fail_at": 0.0}


def fetch_intervals(since, base=None, end=None):
    """[[a, b], ...] in epoch seconds, or None when Voice is unreachable / answers nonsense. Cached ~2 s, but never an answer fetched before
    the segment (`end`) was over: a bot that just started would be missing from it. A failure is cached ~5 s (None, no waiting)."""
    now = time.time()
    with _lock:
        c = _cache
        if now - c["fail_at"] < FAIL_S:
            return None
        if c["intervals"] is not None and now - c["at"] < CACHE_S and c["since"] <= since and (end is None or end <= c["at"] - FRESH_MARGIN):
            return c["intervals"]
    try:
        r = requests.get((base or VOICE_URL) + "/api/speech-intervals", params={"since": f"{since:.3f}"}, timeout=TIMEOUT)
        if not r.ok:
            raise ValueError("http")
        d = r.json()
        iv = [(float(a), float(b)) for a, b in (d.get("intervals") or [])]
        if d.get("speaking"):    # an utterance in progress has no closed interval yet
            iv.append((now - OPEN_S, now))
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        with _lock:
            _cache["fail_at"] = time.time()
        return None
    with _lock:
        _cache.update(at=now, since=since, intervals=iv, fail_at=0.0)
    return iv


def overlaps(a, b, intervals):
    return any(min(b, y) - max(a, x) > MIN_OVERLAP for x, y in intervals)


def is_bot(start, end, fallback=None, base=None):
    """True when [start, end] (epoch seconds) overlaps bot speech. `fallback()` answers when Voice is unreachable (the old speaking.json check)."""
    iv = fetch_intervals(start - PAD_BEFORE, base, end)
    if iv is None:
        try:
            return bool(fallback()) if fallback else False
        except Exception:  # noqa: BLE001
            return False
    return overlaps(start, end, iv)


def reset_cache():
    with _lock:
        _cache.update(at=0.0, since=0.0, intervals=None, fail_at=0.0)
