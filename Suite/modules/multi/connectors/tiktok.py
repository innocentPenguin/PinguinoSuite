"""TikTok LIVE connector — UNOFFICIAL and READ-ONLY.

TikTok has no official live-chat API. This uses the optional third-party `TikTokLive` package (reverse-engineered,
can break or violate ToS). It is OFF by default (setting tiktok_enabled + tiktok_user) and never sends.
Event mapping and the import guard live in connectors/tiktok_live.py.
"""
import asyncio
import time

import config
import secrets_store
from connectors import tiktok_live
from connectors.base import Connector
from models import ChatMessage


def normalize_comment(ev, unique_id):
    """TikTokLive CommentEvent-like object -> ChatMessage. Pure, unit-tested with a fake event."""
    u = ev.user
    uid = str(getattr(u, "user_id", "") or getattr(u, "unique_id", ""))
    return ChatMessage(
        id=f"tiktok:{unique_id}:{getattr(ev, 'msg_id', '') or uid + str(int(time.time() * 1000))}", platform="tiktok",
        channel=unique_id, user_id=uid, user=(getattr(u, "unique_id", "") or "").lower(),
        display=getattr(u, "nickname", "") or getattr(u, "unique_id", ""), text=ev.comment, ts=time.time(),
        badges=[], reply_to="", reply_to_user="", raw_type="text")


def backoff(n, offline=False):
    """Seconds to wait before the next connect attempt. Offline streamer: 30 s, creeping to 60 s (never hammer TikTok). Errors: 10 s doubling, cap 300 s."""
    if offline:
        return min(60, 30 + 5 * max(0, n))
    return min(300, 10 * 2 ** max(0, n))


def backoff_badjson(n):
    """Blocked/empty answers from TikTok: 60 s doubling, cap 600 s (never hammer an endpoint that is refusing us)."""
    return min(600, 60 * 2 ** max(0, n))


def classify(e):
    """connect exception -> (kind, detail). kinds: offline | notfound | ratelimit | error. By class name so a library drift never breaks the guard."""
    name = type(e).__name__
    if name == "JSONDecodeError" or isinstance(e, ValueError) and "Expecting value" in str(e):
        return "badjson", "TikTok answered with a page that is not data (empty or a block/captcha page), so the live lookup failed before connecting"
    if name == "UserOfflineError":
        return "offline", ""
    if name == "UserNotFoundError":
        return "notfound", "TikTok user not found: check the @handle"
    if name == "SignatureRateLimitError" or "RATE_LIMIT" in str(e):
        return "ratelimit", "TikTok sign server rate limit: waiting"
    if name.startswith("Sign") or "sign" in str(e).lower():
        return "error", "TikTok sign server problem: " + str(e)[:80]
    return "error", (name + ": " + str(e))[:120]


def body_of(e):
    """First 200 characters of the non-JSON body a JSONDecodeError was parsing (json puts the text in .doc). Body only: never headers, cookies or tokens."""
    doc = getattr(e, "doc", None)
    if not isinstance(doc, str):
        return ""
    return " ".join(doc[:200].split())


def make_client(user, s):
    """Build a TikTokLiveClient (7.x). Tests replace this. Own sign server / key are optional."""
    from TikTokLive import TikTokLiveClient
    try:
        from TikTokLive.client.web.web_settings import WebDefaults
        if s.get("tiktok_sign_url"):
            WebDefaults.tiktok_sign_url = str(s["tiktok_sign_url"])
        key = secrets_store.get("tiktok_sign_key")
        if key:
            WebDefaults.tiktok_sign_api_key = key
    except Exception:
        pass
    return TikTokLiveClient(unique_id="@" + user)


class TikTok(Connector):
    platform, label, official = "tiktok", "TikTok (unofficial)", False
    capabilities = {"read": True, "send": False, "reply": False, "badges": True, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.stop = False
        self.client = None
        self.fails = 0
        self.live_since = None
        self._bodies = set()                       # distinct non-JSON bodies already logged (log each kind once)

    def _wire(self, client, tev, user):
        tiktok_live.attach(client, tev, user, self.inbox.put, self.state)

        def on(name, fn):
            cls = getattr(tev, name, None)
            if cls is not None:
                client.add_listener(cls, fn)

        async def on_room(ev):
            try:
                n = getattr(ev, "total", None) or getattr(ev, "total_user", None)
                if n is not None:
                    self.state["viewers"] = int(n)
            except Exception:
                pass

        async def on_connect(ev):
            self.live_since = time.time()
            self.set_status("connected", f"@{user} (unofficial)")

        async def on_end(ev):
            self.set_status("waiting", f"@{user} is not live (stream ended)")
            try:
                await client.disconnect()
            except Exception:
                pass
        on("RoomUserSeqEvent", on_room)
        on("ConnectEvent", on_connect)
        on("LiveEndEvent", on_end)

    async def _once(self, s, user):
        """One connect attempt; returns when the connection ends (blocking client.connect). Raises on failures."""
        import TikTokLive.events as tev
        client = self.client = make_client(user, s)
        self._wire(client, tev, user)
        self.set_status("connecting", f"@{user}")
        await client.connect()

    async def run(self):
        while not self.stop:
            s = config.settings()
            user = tiktok_live.handle(s)
            if not s.get("tiktok_enabled"):
                self.set_status("disabled", "Off by default (unofficial). Enable in settings and set the @handle.")
                await asyncio.sleep(10)
                continue
            if not user:
                self.set_status("needs_setup", "Set the TikTok @handle you stream from")
                await asyncio.sleep(10)
                continue
            ok, why = tiktok_live.available()
            if not ok:
                self.set_status("needs_auth", why + " (optional package; ask to install)")
                await asyncio.sleep(60)
                continue
            wait = 5
            try:
                await self._once(s, user)
                if self.live_since and time.time() - self.live_since > 60:
                    self.fails = 0                                  # it ran a while: not a flapping failure
                if self.state.get("status") != "waiting":
                    self.set_status("reconnecting", f"@{user} disconnected, retrying")
                    self.state["reconnects"] += 1
                    wait = backoff(self.fails)
                    self.fails += 1
                else:
                    wait = backoff(0, True)
            except Exception as e:
                kind, detail = classify(e)
                if kind == "offline":
                    self.set_status("waiting", f"@{user} is not live yet")
                    wait = backoff(self.fails, True)
                    self.fails = min(self.fails + 1, 6)
                elif kind == "notfound":
                    self.set_status("needs_setup", detail)
                    wait = 60
                elif kind == "badjson":
                    self.state["reconnects"] += 1
                    body = body_of(e)
                    if body not in self._bodies:
                        self._bodies.add(body)
                        detail += f" (first 200 characters: {body!r})" if body else " (empty body)"
                    if not secrets_store.get("tiktok_sign_key"):
                        detail += ". No tiktok_sign_key set: a free Euler Stream key may help"
                    self.set_status("reconnecting", detail)
                    wait = backoff_badjson(self.fails)                  # starts at 60 s, not 10: this does not fix itself in seconds
                    self.fails += 1
                else:
                    self.state["reconnects"] += 1
                    self.set_status("reconnecting", detail)
                    wait = backoff(self.fails)
                    self.fails += 1
            finally:
                self.live_since = None
                c, self.client = self.client, None
                if c is not None:
                    try:
                        await c.disconnect()
                    except Exception:
                        pass
            await asyncio.sleep(wait)
