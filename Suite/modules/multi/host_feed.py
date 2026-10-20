"""Reads the PinguinoHost activity feed (Twitch follows, channel point redeems, ...) and shows them in the chat as event rows.

Polls http://127.0.0.1:8770/api/activity every few seconds. Read only; the Host is never changed. If the Host is not running we just
retry. Subs, gifts, cheers and raids already arrive through Twitch's own chat events, so they are only taken from the Host while Twitch
is not connected in Multi (never twice). Off with setting host_feed_enabled=false."""
import asyncio
import json
import time
import urllib.request

import config
import console_log
from models import ChatMessage

HOST = "http://127.0.0.1:8770"
ALWAYS = ("follow", "redeem", "ban", "unban", "unmod", "mod", "shoutout")                 # not available through the Twitch chat connection
FALLBACK = ("sub", "resub", "gift", "cheer", "raid")
MODWORDS = {"ban": "banned", "timeout": "timed out", "unban": "unbanned", "unmod": "unmodded", "mod": "modded"}
MODPASSIVE = {"ban": "banned", "timeout": "timed out", "unban": "unbanned", "unmod": "unmodded", "mod": "made a moderator"}
WORDS = {"shoutout": "{u} was given a shoutout", "follow": "{u} followed", "redeem": "{u} redeemed {d}", "sub": "{u} subscribed", "resub": "{u} resubscribed",
         "gift": "{u} gifted subs", "cheer": "{u} cheered", "raid": "{u} is raiding"}


def to_message(item, channel):
    """One Host activity item -> an event ChatMessage (or None for types Multi does not show)."""
    t = item.get("type")
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
    text = WORDS[t].format(u=user, d=detail or "a reward")
    if t == "redeem" and item.get("message"):
        text += ": " + str(item["message"])[:200]
    return ChatMessage(id=f"host:{item['seq']}", platform="twitch", channel=channel, user_id=user.lower(), user=user.lower(), display=user,
                       text=text[:300], ts=float(item.get("ts") or time.time()), raw_type=t, event=t, amount=int(item.get("amount") or 0))


def _get(path):
    with urllib.request.urlopen(HOST + path, timeout=3) as r:
        return json.loads(r.read())


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
