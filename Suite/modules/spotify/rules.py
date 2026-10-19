"""Song-request rules + chat command parsing. Pure functions, no network."""
import re
import time

DEFAULTS = {
    "requests_open": False,      # ships CLOSED: a mod/broadcaster opens requests (!sr open, UI toggle, site)
    "mod_only": False,            # only mods/broadcaster may request
    "sub_only": False,            # only subs/VIPs/mods may request
    "per_user_limit": 2,          # pending requests per viewer
    "sub_extra": 2,               # extra pending slots for subs/VIPs
    "mods_bypass_limits": True,
    "queue_max": 50,
    "max_length_s": 600,
    "block_explicit": False,
    "dup_cooldown_min": 60,       # same track can't be requested again within this many minutes of playing
    "sub_priority": True,         # subs/VIPs ranked ahead within the same fairness round
    "blocklist": [],              # lowercase substrings of title/artist, or spotify ids/uris
    "blocked_users": [],
    "stream_safe": False,         # forces explicit block + approval inbox
    "require_approval": False,    # every viewer request waits in the inbox until approved
    "skip_votes": 3,
    "skip_mod_instant": True,
    "jit_ms": 25000,              # push next track to Spotify's queue when this much time is left
    "np_template": "{title} - {artist}",
    "np_idle_text": "",
    "overlay_show_next": 2,
    "chat_replies": True,
}

TIER_REDEEM, TIER_SUB, TIER_NORMAL = 2, 1, 0


def _type_ok(default, v):
    if isinstance(default, bool):
        return isinstance(v, bool)
    if isinstance(default, (int, float)):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, type(default))


def merged(saved):
    """Defaults overlaid with saved values; unknown keys and wrong types are dropped."""
    s = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    if isinstance(saved, dict):
        for k, v in saved.items():
            if k in DEFAULTS and _type_ok(DEFAULTS[k], v):
                s[k] = v
    return s


def is_staff(roles):
    return bool(set(roles) & {"broadcaster", "mod"})


def tier_for(settings, roles, redeem=False):
    if redeem:
        return TIER_REDEEM
    if settings["sub_priority"] and set(roles) & {"sub", "vip"}:
        return TIER_SUB
    return TIER_NORMAL


def _norm(s):
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def blocked_reason(settings, track):
    hay = _norm(track.get("name", "")) + " | " + " | ".join(_norm(a) for a in track.get("artists", []))
    ids = {_norm(track.get("id", "")), _norm(track.get("uri", ""))}
    for b in settings["blocklist"]:
        b = _norm(b)
        if b and (b in ids or b in hay):
            return b
    return None


def evaluate(settings, track, user, roles, queue, now_uri, now=None):
    """-> (ok, code, message). code is machine-readable; message is a chat-ready sentence."""
    now = now or time.time()
    roles = set(roles)
    if "broadcaster" in roles:
        return True, "ok", ""
    staff = is_staff(roles)
    low = user.lower()
    if low in {_norm(u) for u in settings["blocked_users"]}:
        return False, "user_blocked", f"@{user} you can't request songs."
    if not settings["requests_open"] and not staff:
        return False, "closed", "Song requests are closed right now."
    if settings["mod_only"] and not staff:
        return False, "mod_only", "Only mods can request songs right now."
    if settings["sub_only"] and not (staff or roles & {"sub", "vip"}):
        return False, "sub_only", "Song requests are for subscribers right now."
    why = blocked_reason(settings, track)
    if why:
        return False, "blocked", f"@{user} that song/artist isn't allowed on stream."
    if (settings["block_explicit"] or settings["stream_safe"]) and track.get("explicit"):
        return False, "explicit", f"@{user} explicit songs aren't allowed right now."
    if settings["max_length_s"] and track.get("duration_ms", 0) > settings["max_length_s"] * 1000:
        return False, "too_long", f"@{user} that song is too long (max {settings['max_length_s'] // 60} min)."
    if len(queue.items) >= settings["queue_max"] and not staff:
        return False, "full", "The queue is full."
    uri = track.get("uri")
    if queue.contains_uri(uri) or uri == now_uri:
        return False, "dup_queue", f"@{user} that song is already queued or playing."
    cd = settings["dup_cooldown_min"] * 60
    if cd:
        for h in queue.history:
            if h.get("uri") == uri and now - h.get("played_at", 0) < cd:
                return False, "dup_recent", f"@{user} that song was played recently."
    if not (staff and settings["mods_bypass_limits"]):
        limit = settings["per_user_limit"] + (settings["sub_extra"] if roles & {"sub", "vip"} else 0)
        if limit and queue.pending_for(user) >= limit:
            return False, "limit", f"@{user} you already have {limit} request(s) in the queue."
    return True, "ok", ""


def needs_approval(settings, roles):
    if "broadcaster" in set(roles):
        return False
    return bool(settings["require_approval"] or settings["stream_safe"]) and not (is_staff(roles) and not settings["stream_safe"])


_CMDS = {"sr": "sr", "request": "sr", "songrequest": "sr", "skip": "skip", "voteskip": "skip", "queue": "queue", "q": "queue", "songqueue": "queue", "srqueue": "queue",
         "song": "song", "currentsong": "song", "nowplaying": "song", "np": "song", "oops": "oops", "wrongsong": "oops",
         "blocksong": "blocksong", "srclear": "clear"}


def parse(text):
    """'!sr  foo bar' -> ('sr', 'foo bar'); non-commands -> (None, '')."""
    t = (text or "").strip()
    if not t.startswith("!"):
        return None, ""
    head, _, rest = t[1:].partition(" ")
    cmd = _CMDS.get(head.lower())
    return (cmd, rest.strip()) if cmd else (None, "")


_URI = re.compile(r"(?:spotify:track:|open\.spotify\.com/(?:intl-[a-z]+/)?track/)([A-Za-z0-9]{22})")


def track_id_from(q):
    m = _URI.search(q or "")
    return m.group(1) if m else None
