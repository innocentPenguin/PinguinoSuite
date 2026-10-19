"""Song-request rules, settings merge and chat command parsing. Pure functions, no network."""
import math
import re
import time

import config_schema as cs

DEFAULTS = cs.DEFAULTS
TIER_REDEEM, TIER_SUB, TIER_NORMAL = 2, 1, 0


def _type_ok(default, v):
    if isinstance(default, bool):
        return isinstance(v, bool)
    if isinstance(default, (int, float)):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, type(default))


def _clean_word(w):
    return re.sub(r"[^a-z0-9_]", "", str(w).lower())


def merged(saved):
    """Defaults overlaid with saved values. Unknown keys / wrong types are dropped; dict settings merge per entry."""
    s = {k: (list(v) if isinstance(v, list) else {a: (list(b) if isinstance(b, list) else b) for a, b in v.items()} if isinstance(v, dict) else v)
         for k, v in DEFAULTS.items()}
    if not isinstance(saved, dict):
        return s
    for k, v in saved.items():
        if k not in DEFAULTS:
            continue
        if k == "msgs" and isinstance(v, dict):
            for mk, mv in v.items():
                if mk in cs.MSGS and isinstance(mv, str):
                    s["msgs"][mk] = mv[:300]
        elif k == "cmd_aliases" and isinstance(v, dict):
            for ck, cv in v.items():
                if ck in cs.COMMANDS:
                    words = cv.split(",") if isinstance(cv, str) else cv if isinstance(cv, list) else []
                    words = [w for w in (_clean_word(x) for x in words) if w]
                    if words:
                        s["cmd_aliases"][ck] = words
        elif k == "ov_accent":
            if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                s[k] = v
        elif k == "approval_for":
            if v in ("everyone", "non_subs", "non_staff"):
                s[k] = v
        elif k == "ov_theme":
            if v in ("dark", "light", "glass", "minimal"):
                s[k] = v
        elif k == "prefix":
            if isinstance(v, str) and 0 < len(v.strip()) <= 3:
                s[k] = v.strip()
        elif _type_ok(DEFAULTS[k], v):
            s[k] = v[:500] if isinstance(v, list) else v
    return s


def is_staff(roles):
    return bool(set(roles) & {"broadcaster", "mod"})


def is_sub(roles):
    return bool(set(roles) & {"sub", "vip"})


def tier_for(settings, roles, redeem=False, user=""):
    if redeem and settings["redeem_priority"]:
        return TIER_REDEEM
    if settings["sub_priority"] and (is_sub(roles) or _listed(settings["priority_users"], user)):
        return TIER_SUB
    return TIER_NORMAL


def _listed(names, user):
    u = _norm(user)
    return bool(u) and u in {_norm(n) for n in names}


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


def limit_for(settings, roles):
    """Pending-request limit for this viewer (0 = unlimited)."""
    roles = set(roles)
    if is_staff(roles) and settings["mods_bypass_limits"]:
        return 0
    base = settings["per_user_limit"]
    if base == 0:
        return 0
    best = base
    for role, key in (("vip", "limit_vip"), ("sub", "limit_sub")):
        if role in roles:
            v = settings[key]
            best = max(best, base + settings["sub_extra"] if v < 0 else v)
    return best


def cooldown_for(settings, roles):
    if is_staff(roles) and settings["mods_bypass_limits"]:
        return 0
    if is_sub(roles) and settings["cooldown_sub_s"] >= 0:
        return settings["cooldown_sub_s"]
    return settings["cooldown_s"]


def evaluate(settings, track, user, roles, queue, now_uri, now=None, last_ts=None, session_count=0):
    """-> (ok, code, ctx). `code` is a message key (see config_schema.MSGS); ctx = placeholder values for the reply."""
    now = now or time.time()
    roles = set(roles)
    ctx = {"user": user, "title": track.get("name", ""), "artist": (track.get("artists") or [""])[0],
           "song": f"{track.get('name', '')} - {', '.join(track.get('artists', []))}"}
    if "broadcaster" in roles:
        return True, "ok", ctx
    staff = is_staff(roles)
    low = user.lower()
    if low in {_norm(u) for u in settings["blocked_users"]}:
        return False, "user_blocked", ctx
    if not settings["requests_open"] and not staff:
        return False, "closed", ctx
    if settings["mod_only"] and not staff:
        return False, "mod_only", ctx
    if settings["sub_only"] and not (staff or is_sub(roles)):
        return False, "sub_only", ctx
    if blocked_reason(settings, track):
        return False, "blocked", ctx
    if track.get("_genre"):
        return False, "genre", {**ctx, "genre": track["_genre"]}
    if (settings["block_explicit"] or settings["stream_safe"]) and track.get("explicit"):
        return False, "explicit", ctx
    dur = track.get("duration_ms", 0)
    max_s = settings["max_length_s"]
    if is_sub(roles) and settings["max_length_sub_s"]:
        max_s = settings["max_length_sub_s"]
    if max_s and dur > max_s * 1000:
        return False, "too_long", {**ctx, "max_min": max(1, max_s // 60)}
    if settings["min_length_s"] and dur < settings["min_length_s"] * 1000:
        return False, "too_short", {**ctx, "min_s": settings["min_length_s"]}
    if len(queue.items) >= settings["queue_max"] and not staff:
        return False, "full", ctx
    mm = settings["queue_max_minutes"]
    if mm and not staff and queue.total_ms() >= mm * 60000:
        return False, "full", ctx
    uri = track.get("uri")
    if queue.contains_uri(uri) or uri == now_uri:
        return False, "dup_queue", ctx
    cd = settings["dup_cooldown_min"] * 60
    if cd:
        for h in queue.history:
            if h.get("uri") == uri and now - h.get("played_at", 0) < cd:
                return False, "dup_recent", ctx
    cap = settings["max_per_artist"]
    if cap and not staff:
        a = _norm(ctx["artist"])
        if a and sum(1 for it in queue.items if it["artists"] and _norm(it["artists"][0]) == a) >= cap:
            return False, "artist_cap", ctx
    limit = limit_for(settings, roles)
    if limit and queue.pending_for(user) >= limit:
        return False, "limit", {**ctx, "limit": limit}
    sl = settings["session_limit"]
    if sl and not staff and session_count >= sl:
        return False, "session_limit", {**ctx, "limit": sl}
    cool = cooldown_for(settings, roles)
    if cool and last_ts and now - last_ts < cool:
        return False, "cooldown", {**ctx, "wait": math.ceil(cool - (now - last_ts)), "cooldown": cool}
    return True, "ok", ctx


def needs_approval(settings, roles, user=""):
    roles = set(roles)
    if "broadcaster" in roles:
        return False
    if _listed(settings["trusted_users"], user) and not settings["stream_safe"]:
        return False
    if settings["stream_safe"]:
        return True
    if not settings["require_approval"]:
        return False
    who = settings["approval_for"]
    if who == "non_staff":
        return not is_staff(roles)
    if who == "non_subs":
        return not (is_staff(roles) or is_sub(roles))
    return True


def command_map(settings):
    """word -> canonical command, from the (editable) aliases."""
    out = {}
    for cmd, words in settings["cmd_aliases"].items():
        for w in words:
            out.setdefault(w, cmd)
    return out


def parse(text, settings=None):
    """'!sr  foo bar' -> ('sr', 'foo bar'); non-commands -> (None, '')."""
    settings = settings or {"prefix": "!", "cmd_aliases": cs.COMMANDS}
    t = (text or "").strip()
    p = settings["prefix"]
    if not t.startswith(p):
        return None, ""
    head, _, rest = t[len(p):].partition(" ")
    cmd = command_map(settings).get(head.lower())
    return (cmd, rest.strip()) if cmd else (None, "")


_URI = re.compile(r"(?:spotify:track:|open\.spotify\.com/(?:intl-[a-z]+/)?track/)([A-Za-z0-9]{22})")


def track_id_from(q):
    m = _URI.search(q or "")
    return m.group(1) if m else None
