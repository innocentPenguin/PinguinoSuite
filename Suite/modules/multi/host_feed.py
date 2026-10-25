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
from connectors.base import send_disabled
from models import ChatMessage

HOST = os.environ.get("MULTI_HOST_URL") or "http://127.0.0.1:8770"
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
        user = str((item.get("target") if t == "raid_out" else None) or item.get("user") or channel or "channel")[:60]     # raid_out: the alert and the row name the TARGET channel
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


STATE = {"up": None, "last_ok": 0.0, "error": ""}      # reachability of the Host as last seen by any GET (None = not tried yet)


def status():
    return {"up": STATE["up"], "url": HOST, "last_ok": STATE["last_ok"], "error": STATE["error"]}


def _get(path):
    try:
        with urllib.request.urlopen(HOST + path, timeout=3) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:                  # the Host answered (even with 404/500): it is reachable
        STATE.update(up=True, last_ok=time.time(), error=f"HTTP {e.code} on {path.split('?')[0]}")
        raise
    except Exception as e:
        STATE.update(up=False, error=type(e).__name__)
        raise
    STATE.update(up=True, last_ok=time.time(), error="")
    return d


def _say_sync(text):
    if send_disabled():
        return {"ok": False, "via": "sending is switched off (MULTI_NO_SEND)"}
    tok = os.environ.get("PINGUINO_MODULE_TOKEN") or os.environ.get("PINGUINO_API_TOKEN") or ""
    req = urllib.request.Request(HOST + "/api/say", data=json.dumps({"text": text, "bot": "core"}).encode(), method="POST",
                                 headers={"content-type": "application/json", "Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code >= 500:                                # the Host may have processed it before failing: never repeated
            return {"ok": True, "via": f"Host error {e.code} (may have gone out, not repeated)"}
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


# ---- YouTube chat -> Host -------------------------------------------------------------------------------------------------------------
# The Host cannot read YouTube chat, so Multi hands every NEW youtube chat line to it (POST /api/chat-in). Best effort: it never blocks
# ingestion, a line is tried once (never repeated), and a Host that is down or does not have the endpoint yet is left alone for 60 s.
CHAT_IN_MAX_AGE = 30.0                                  # older lines are history backfill, never pushed
CHAT_IN_BACKOFF = 60.0


def _role(m):
    b = {str(x).lower() for x in (m.badges or [])}
    if b & {"owner", "broadcaster"}:
        return "broadcaster"
    if "moderator" in b:
        return "mod"
    if b & {"member", "sponsor", "subscriber"}:
        return "sub"
    return "viewer"


def chat_in_body(m, own_bot):
    b = {str(x).lower() for x in (m.badges or [])}
    role = _role(m)
    return {"platform": "youtube", "user": m.display or m.user, "userId": m.user_id, "text": m.text, "msgId": m.id, "role": role,
            "isSub": role == "sub" or bool(b & {"member", "sponsor", "subscriber"}), "ownBot": bool(own_bot), "isBot": bool(own_bot)}


def _chat_in_url():
    from scene_follow import _local
    url = str(config.settings().get("host_url") or HOST).strip().rstrip("/")
    return url if _local(url) else ""


def _chat_in_post(body):
    """POST one line to the Host. Returns the HTTP status (0 = unreachable / timed out). Never logs the token."""
    url = _chat_in_url()
    if not url:
        return 0
    tok = os.environ.get("PINGUINO_MODULE_TOKEN") or os.environ.get("PINGUINO_API_TOKEN") or ""
    if not tok:
        import alerts
        tok = alerts.host_token(os.environ.get("PINGUINO_DATA_DIR"), "host")
    req = urllib.request.Request(url + "/api/chat-in", data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", "Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


class ChatIn:
    def __init__(self, post=None, now=time.time, cap=200):
        import collections
        import threading
        self.post, self.now = post or _chat_in_post, now
        self.q = collections.deque(maxlen=cap)           # full: the oldest line makes room
        self.seen = collections.OrderedDict()
        self.cv = threading.Condition()
        self.thread = None
        self.backoff_until = 0.0
        self.stats = {"sent": 0, "dropped": 0, "failed": 0}

    def offer(self, m):
        """Queue one stored message if it qualifies. Returns True when queued."""
        import ding
        if m.platform != "youtube" or m.event or (m.meta or {}).get("notice") or not (m.text or "").strip():
            return False
        st = config.settings()
        if not st.get("host_chat_in", True) or send_disabled():
            return False
        if self.now() - float(m.ts or 0) > CHAT_IN_MAX_AGE or m.id in self.seen:
            return False
        self.seen[m.id] = 1
        while len(self.seen) > 2000:
            self.seen.popitem(last=False)
        body = chat_in_body(m, m.is_self or ding.is_bot(m, st))
        with self.cv:
            if len(self.q) == self.q.maxlen:
                self.stats["dropped"] += 1
            self.q.append((m.ts, body))
            if self.thread is None:
                import threading
                self.thread = threading.Thread(target=self._loop, name="host-chat-in", daemon=True)
                self.thread.start()
            self.cv.notify()
        return True

    def step(self):
        """Send the oldest queued line once. Returns False when the queue is empty."""
        with self.cv:
            if not self.q:
                return False
            ts, body = self.q.popleft()
        if self.now() < self.backoff_until or self.now() - float(ts or 0) > CHAT_IN_MAX_AGE:
            self.stats["dropped"] += 1                    # Host asleep or the line went stale while waiting: not sent, not retried
            return True
        code = self.post(body)
        if 200 <= code < 300:
            self.stats["sent"] += 1
        else:
            self.stats["failed"] += 1
            if code in (0, 404):
                self.backoff_until = self.now() + CHAT_IN_BACKOFF
                console_log.warn("host-chat-in", "the Host is not taking YouTube chat yet (not running or no /api/chat-in); trying again in 60 s", dedupe_s=3600)
        return True

    def _loop(self):
        while True:
            with self.cv:
                while not self.q:
                    self.cv.wait()
            try:
                self.step()
            except Exception as e:
                console_log.warn("host-chat-in", f"push failed: {type(e).__name__}", dedupe_s=600)


CHAT_IN = ChatIn()
