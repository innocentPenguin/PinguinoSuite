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
MIN_OVERLAP = 0.05     # seconds; adjacent (touching) speech is not an overlap
PAD_BEFORE = 5.0       # ask for intervals from this long before the oldest segment

_lock = threading.Lock()
_cache = {"at": 0.0, "since": 0.0, "intervals": None}


def fetch_intervals(since, base=None):
    """[[a, b], ...] in epoch seconds, or None when Voice is unreachable / answers nonsense. Cached ~2 s."""
    now = time.time()
    with _lock:
        c = _cache
        if c["intervals"] is not None and now - c["at"] < CACHE_S and c["since"] <= since:
            return c["intervals"]
    try:
        r = requests.get((base or VOICE_URL) + "/api/speech-intervals", params={"since": f"{since:.3f}"}, timeout=TIMEOUT)
        if not r.ok:
            return None
        iv = [(float(a), float(b)) for a, b in (r.json().get("intervals") or [])]
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return None
    with _lock:
        _cache.update(at=now, since=since, intervals=iv)
    return iv


def overlaps(a, b, intervals):
    return any(min(b, y) - max(a, x) > MIN_OVERLAP for x, y in intervals)


def is_bot(start, end, fallback=None, base=None):
    """True when [start, end] (epoch seconds) overlaps bot speech. `fallback()` answers when Voice is unreachable (the old speaking.json check)."""
    iv = fetch_intervals(start - PAD_BEFORE, base)
    if iv is None:
        try:
            return bool(fallback()) if fallback else False
        except Exception:  # noqa: BLE001
            return False
    return overlaps(start, end, iv)


def reset_cache():
    with _lock:
        _cache.update(at=0.0, since=0.0, intervals=None)
