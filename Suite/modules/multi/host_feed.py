"""Reads the PinguinoHost activity feed (Twitch follows, channel point redeems, ...) and shows them in the chat as event rows.

Polls http://127.0.0.1:8770/api/activity every few seconds. Read only; the Host is never changed. If the Host is not running we just
retry. Subs, gifts, cheers and raids already arrive through Twitch's own chat events, so they are only taken from the Host while Twitch
is not connected in Multi (never twice). Off with setting host_feed_enabled=false."""
import asyncio
import json
import os
import time
import urllib.error
import urllib.request

import config
import console_log
from models import ChatMessage

HOST = "http://127.0.0.1:8770"
ALWAYS = ("follow", "redeem", "ban", "unban", "unmod", "mod", "shoutout", "raid_out", "poll", "prediction", "hype", "streak")                 # not available through the Twitch chat connection
FALLBACK = ("sub", "resub", "gift", "cheer", "raid")
MODWORDS = {"ban": "banned", "timeout": "timed out", "unban": "unbanned", "unmod": "unmodded", "mod": "modded"}
MODPASSIVE = {"ban": "banned", "timeout": "timed out", "unban": "unbanned", "unmod": "unmodded", "mod": "made a moderator"}
WORDS = {"shoutout": "{u} was given a shoutout", "follow": "{u} followed", "redeem": "{u} redeemed {d}", "sub": "{u} subscribed", "resub": "{u} resubscribed",
         "gift": "{u} gifted subs", "cheer": "{u} cheered", "raid": "{u} is raiding", "streak": "{u} hit a {n}-stream watch streak"}


def _live_text(t, item):
    """Plan 5 channel events (raid out, poll, prediction, hype train) -> one short line, or None."""
    st, what, d = str(item.get("state") or ""), str(item.get("what") or "")[:100], item.get("data") if isinstance(item.get("data"), dict) else {}
    if t == "raid_out":
        return f"Raiding {item.get('target') or item.get('user')} with {int(item.get('amount') or 0)} viewers"
    if t == "poll":
        top = max((d.get("choices") or [{}]), key=lambda c: int(c.get("votes") or 0), default={})
        return f"Poll started: {what}" if st == "begin" else f"Poll ended: {what}" + (f" (top: {top.get('title')})" if top.get("title") else "")
    if t == "prediction":
        if st == "begin":
            return f"Prediction started: {what}"
        if st == "lock":
            return f"Prediction locked: {what}"
        win = next((o.get("title") for o in (d.get("outcomes") or []) if o.get("id") == d.get("winningOutcomeId")), None)
        return f"Prediction ended: {what}" + (f" (winner: {win})" if win else " (canceled)" if d.get("status") == "canceled" else "")
    if t == "hype":
        return f"Hype train started ({what})" if st == "begin" else f"Hype train ended ({what})"
    return None


def to_message(item, channel):
    """One Host activity item -> an event ChatMessage (or None for types Multi does not show)."""
    t = item.get("type")
    if t in ("raid_out", "poll", "prediction", "hype"):
        text = _live_text(t, item)
        user = str(item.get("user") or channel or "channel")[:60]
        return ChatMessage(id=f"host:{item['seq']}", platform="twitch", channel=channel, user_id=user.lower(), user=user.lower(), display=user,
                           text=text[:300], ts=float(item.get("ts") or time.time()), raw_type=t, event=t, amount=int(item.get("amount") or 0)) if text else None
    if t not in WORDS and t not in MODWORDS:
        return None
    user = str(item.get("user") or "someone")[:60]
    detail = str(item.get("detail") or "")[:120]
    if t in MODWORDS:                                  # moderation notice: "<moderator> banned <user>" (or "<user> was banned" when the Host does not say who)
        if t == "ban" and "timed" in detail:
            t = "timeout"
        mod = str(item.get("moderator") or "")[:60]
        verb = MODWORDS[t]
        shown, text = (mod, f"{mod} {verb} {user}") if mod else (user, f"{user} was {MODPASSIVE[t]}")
        if item.get("message") and t in ("ban", "timeout"):
            text += f" ({str(item['message'])[:100]})"
        return ChatMessage(id=f"host:{item['seq']}", platform="twitch", channel=channel, user_id=shown.lower(), user=shown.lower(), display=shown,
                           text=text[:300], ts=float(item.get("ts") or time.time()), raw_type=t, event=t, amount=int(item.get("amount") or 0))
    text = WORDS[t].format(u=user, d=detail or "a reward", n=int(item.get("amount") or item.get("count") or 0))
    if t == "redeem" and item.get("message"):
        text += ": " + str(item["message"])[:200]
    flags = ["refollow"] if t == "follow" and str(item.get("refollow", "")).lower() in ("true", "1") else []
    meta = {k: item[k] for k in ("tier", "months", "avatar", "level", "rank_colour", "recipient", "first_time", "anonymous", "sim", "test", "streak", "hours", "years") if item.get(k) not in (None, "")}
    meta["message"] = str(item.get("message") or (detail if t == "redeem" else ""))[:200]
    return ChatMessage(id=f"host:{item['seq']}", platform="twitch", channel=channel, user_id=user.lower(), user=user.lower(), display=user,
                       text=text[:300], ts=float(item.get("ts") or time.time()), raw_type=t, event=t, amount=int(item.get("amount") or item.get("count") or 0), flags=flags, meta=meta)


def _get(path):
    with urllib.request.urlopen(HOST + path, timeout=3) as r:
        return json.loads(r.read())


def _say_sync(text):
    tok = os.environ.get("PINGUINO_MODULE_TOKEN") or os.environ.get("PINGUINO_API_TOKEN") or ""
    req = urllib.request.Request(HOST + "/api/say", data=json.dumps({"text": text, "bot": "core"}).encode(), method="POST",
                                 headers={"content-type": "application/json", "Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "via": f"Host refused ({e.code})"}
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):
            return None                                  # Host not running: nothing was sent, caller may use the direct route
        return {"ok": True, "via": "timed out (may have gone out, not repeated)"}
    except TimeoutError:
        return {"ok": True, "via": "timed out (may have gone out, not repeated)"}


async def live_state():
    """Host GET /api/live-state -> {poll, prediction, hype}; {} when the Host is down."""
    try:
        d = await asyncio.to_thread(_get, "/api/live-state")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


async def say(text):
    """Say a line in Twitch chat through the Host (its 30 s duplicate guard applies to every bot). None = Host unreachable."""
    return await asyncio.to_thread(_say_sync, text)


async def run(inbox, twitch_connected, base=None):
    global HOST
    if base:
        HOST = base
    seq, warned = None, False
    while True:
        st = config.settings()
        if not st.get("host_feed_enabled", True):
            await asyncio.sleep(10)
            continue
        try:
            if seq is None:                               # start from "now": never replay the Host's history
                seq = int((await asyncio.to_thread(_get, "/api/activity?since=999999999&limit=1")).get("seq", 0))
            data = await asyncio.to_thread(_get, f"/api/activity?since={seq}&limit=100")
            types = set(ALWAYS) | (set() if twitch_connected() else set(FALLBACK))
            for item in data.get("items", []):
                seq = max(seq, int(item.get("seq", seq)))
                if item.get("type") in types:
                    m = to_message(item, st["channel"])
                    if m:
                        inbox.put(m)
            warned = False
            await asyncio.sleep(2.5)
        except Exception as e:
            if not warned:
                console_log.info("host-feed", f"Host activity feed not reachable yet ({type(e).__name__}); will keep trying", dedupe_s=600)
                warned = True
            await asyncio.sleep(10)
