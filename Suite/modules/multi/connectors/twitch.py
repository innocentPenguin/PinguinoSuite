"""Twitch connector: EventSub WebSocket `channel.chat.message` (read) + Helix `POST /chat/messages` (send/reply).

Official API. Scopes: user:read:chat user:write:chat. Tokens come from Credential Manager (secrets_store),
placed there by the site's broadcaster-only "Connect Multi" flow (see Docs/PinguinoMulti/CONTRACTS.md) or
pasted manually for development. Refresh goes through the site (it holds the client secret).
"""
import asyncio
import json
import time
from collections import OrderedDict
from datetime import datetime, timezone

import requests
import websockets

import config
import console_log
import secrets_store
from connectors.base import Connector
from models import ChatMessage

EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"
HELIX = "https://api.twitch.tv/helix"
VALIDATE = "https://id.twitch.tv/oauth2/validate"


class TwitchAuthError(RuntimeError):
    """The token is dead or lacks permission: the card shows 'needs_auth' (Ivan must reconnect), not a retry loop."""


class TwitchBusy(RuntimeError):
    """Helix 429. `wait` = seconds Twitch asked us to hold off."""
    def __init__(self, wait):
        super().__init__(f"Twitch rate limit: try again in {int(wait)} s")
        self.wait = wait


def retry_after(r, now=None):
    """Seconds to wait after a 429: Retry-After (seconds), else Ratelimit-Reset (epoch), else 30. Clamped 1..300; junk headers fall back."""
    h = getattr(r, "headers", None) or {}
    try:
        w = float(h.get("Retry-After"))
    except (TypeError, ValueError):
        try:
            w = float(h.get("Ratelimit-Reset")) - (now if now is not None else time.time())
        except (TypeError, ValueError):
            w = 30.0
    if w != w:                                           # NaN
        w = 30.0
    return max(1.0, min(w, 300.0))


def event_ts(stamp, now=None):
    """EventSub metadata.message_timestamp (RFC3339, nanoseconds) -> epoch; never in the future (clock skew), junk or older than a day -> now."""
    now = time.time() if now is None else now
    try:
        txt = str(stamp).strip().replace("Z", "+00:00")
        if "." in txt:                                   # fromisoformat takes at most 6 fractional digits
            head, rest = txt.split(".", 1)
            digits = ""
            for ch in rest:
                if not ch.isdigit():
                    break
                digits += ch
            txt = head + "." + digits[:6].ljust(6, "0") + rest[len(digits):]
        t = datetime.fromisoformat(txt)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        t = t.timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return now
    return min(t, now) if t > now - 86400 else now


NOTICE_EVENT = {"sub": "sub", "resub": "resub", "sub_gift": "gift", "community_sub_gift": "gift", "gift_paid_upgrade": "gift",
                "prime_paid_upgrade": "sub", "raid": "raid", "announcement": "announcement", "bits_badge_tier": "cheer"}


def normalize_notice(ev, ts=None):
    """Twitch channel.chat.notification event (sub, resub, gift, raid, announcement) -> ChatMessage with .event. Pure."""
    chan, nt = ev["broadcaster_user_login"], ev.get("notice_type", "")
    if nt == "sub_gift" and (ev.get("sub_gift") or {}).get("community_gift_id"):
        return None          # one per recipient of a community gift: the community_sub_gift notice already carries the total (counting both doubled gifts)
    amount = 0
    if nt == "raid":
        amount = int((ev.get("raid") or {}).get("viewer_count", 0))
    elif nt == "resub":
        amount = int((ev.get("resub") or {}).get("cumulative_months", 0))
    elif nt == "community_sub_gift":
        amount = int((ev.get("community_sub_gift") or {}).get("total", 0))
    text = ev.get("system_message") or (ev.get("message") or {}).get("text", "") or nt
    user = ev.get("chatter_user_login") or "anonymous"
    return ChatMessage(
        id=f"twitch:{chan}:{ev['message_id']}", platform="twitch", channel=chan, user_id=ev.get("chatter_user_id") or "0",
        user=user, display=ev.get("chatter_user_name") or user, text=text, ts=ts or time.time(),
        badges=[b["set_id"] for b in ev.get("badges", [])], raw_type=nt, color=ev.get("color") or "",
        event=NOTICE_EVENT.get(nt, "announcement"), amount=amount)


def normalize_event(ev, ts=None):
    """Twitch channel.chat.message event -> ChatMessage. Pure, unit-tested."""
    chan = ev["broadcaster_user_login"]
    reply = ev.get("reply") or {}
    badges = [b["set_id"] for b in ev.get("badges", [])]
    return ChatMessage(
        id=f"twitch:{chan}:{ev['message_id']}", platform="twitch", channel=chan,
        user_id=ev["chatter_user_id"], user=ev["chatter_user_login"],
        display=ev.get("chatter_user_name") or ev["chatter_user_login"],
        text=(ev.get("message") or {}).get("text", ""), ts=ts or time.time(), badges=badges,
        reply_to=f"twitch:{chan}:{reply['parent_message_id']}" if reply.get("parent_message_id") else "",
        reply_to_user=reply.get("parent_user_login", ""),
        first_time=ev.get("message_type") == "user_intro",
        raw_type=ev.get("message_type", "text"), color=ev.get("color") or "",
        event="cheer" if (ev.get("cheer") or {}).get("bits") else ("highlighted" if ev.get("message_type") == "channel_points_highlighted" else ""),
        amount=int((ev.get("cheer") or {}).get("bits") or 0),
        emotes=[{"id": f["emote"]["id"], "text": f.get("text", "")} for f in (ev.get("message") or {}).get("fragments", [])
                if f.get("type") == "emote" and f.get("emote")])


class Twitch(Connector):
    platform, label, official = "twitch", "Twitch", True
    capabilities = {"read": True, "send": True, "reply": True, "badges": True, "history": False}

    def __init__(self, inbox, emit, own_ids=None):
        super().__init__(inbox, emit)
        self.session_id = None
        self.user = None            # {"login","user_id"} of the authenticated account
        self.broadcaster_id = None
        self.sent_ids = set()       # messages Multi sent itself (tagged, so bots/loops can ignore them)
        self.stop = False
        self._frames = OrderedDict()   # EventSub metadata.message_id already handled: Twitch may redeliver frames around a reconnect
        self._checked = time.time()

    # auth ------------------------------------------------------------
    def tokens(self):
        return secrets_store.get("twitch_tokens")

    def _headers(self, tok):
        return {"Authorization": f"Bearer {tok['access_token']}", "Client-Id": tok.get("client_id") or
                config.settings()["twitch_client_id"]}

    def validate(self, tok):
        r = requests.get(VALIDATE, headers={"Authorization": f"OAuth {tok['access_token']}"}, timeout=10)
        if r.status_code == 401:
            return None                                  # only 401 means "token invalid"; a 5xx must not burn the refresh token
        if r.status_code != 200:
            raise RuntimeError(f"Twitch validate {r.status_code}")
        d = r.json()
        tok["client_id"] = d.get("client_id", tok.get("client_id"))
        return d

    def refresh(self, tok):
        site = secrets_store.get("site_url") or "https://innocentpenguin.com"
        r = requests.post(f"{site}/api/multi/refresh", json={"refresh_token": tok.get("refresh_token")}, timeout=10)
        if r.status_code in (400, 401, 403):
            return None                                  # refresh token rejected: Ivan has to reconnect
        if r.status_code != 200:
            raise RuntimeError(f"token refresh via site {r.status_code}")      # site down or deploying: transient, keep retrying
        new = r.json()
        tok.update({k: new[k] for k in ("access_token", "refresh_token", "client_id") if k in new})
        secrets_store.put("twitch_tokens", tok)
        return tok

    def _call(self, method, url, tok=None, **kw):
        """Helix request with one token refresh on 401 and a clear error on 429 (Retry-After)."""
        tok = tok or self.tokens()
        r = getattr(requests, method)(url, headers=self._headers(tok), timeout=10, **kw)
        if r.status_code == 401:
            try:
                new = self.refresh(tok)
            except Exception:
                new = None
            if not new:
                raise TwitchAuthError("Twitch token rejected: reconnect Twitch")
            r = getattr(requests, method)(url, headers=self._headers(new), timeout=10, **kw)
            if r.status_code == 401:
                raise TwitchAuthError("Twitch token rejected: reconnect Twitch")
        if r.status_code == 429:
            raise TwitchBusy(retry_after(r))
        return r

    async def _keep_token(self, tok):
        """Twitch wants a validate at least hourly; this also renews an access token that expired mid-stream so sending keeps working.
        A dead token ends the session (needs_auth); a network blip is ignored this round."""
        self._checked = time.time()
        try:
            info = await asyncio.to_thread(self.validate, tok)
            if info is None:
                new = await asyncio.to_thread(self.refresh, tok)
                info = new and await asyncio.to_thread(self.validate, new)
                if not info:
                    raise TwitchAuthError("token expired; reconnect Twitch")
        except TwitchAuthError:
            raise
        except Exception as e:
            console_log.warn("twitch", f"hourly token check failed ({str(e)[:80]}); will retry", dedupe_s=600)

    async def ensure_auth(self):
        tok = self.tokens()
        if not tok:
            self.set_status("needs_auth", "Connect Twitch in Settings (Connect Multi)")
            return None
        info = await asyncio.to_thread(self.validate, tok)
        if info is None:
            tok = await asyncio.to_thread(self.refresh, tok)
            info = tok and await asyncio.to_thread(self.validate, tok)
        if not info:
            self.set_status("needs_auth", "token expired; reconnect Twitch")
            return None
        scopes = set(info.get("scopes", []))
        if "user:read:chat" not in scopes:
            self.set_status("needs_auth", "token lacks user:read:chat")
            return None
        self.capabilities = dict(self.capabilities, send="user:write:chat" in scopes, reply="user:write:chat" in scopes,
                                 mod_timeout="moderator:manage:banned_users" in scopes,
                                 mod_delete="moderator:manage:chat_messages" in scopes)
        self.user = {"login": info["login"], "user_id": info["user_id"]}
        return tok

    def _resolve_broadcaster(self, tok, login):
        if login.lower() == self.user["login"].lower():
            return self.user["user_id"]
        r = self._call("get", f"{HELIX}/users", tok=tok, params={"login": login})
        data = r.json().get("data", []) if r.status_code == 200 else []
        return data[0]["id"] if data else None

    # reading ---------------------------------------------------------
    def _subscribe(self, tok):
        cond = {"broadcaster_user_id": self.broadcaster_id, "user_id": self.user["user_id"]}
        for typ in ("channel.chat.message", "channel.chat.notification"):
            body = {"type": typ, "version": "1", "condition": cond,
                    "transport": {"method": "websocket", "session_id": self.session_id}}
            try:
                r = self._call("post", f"{HELIX}/eventsub/subscriptions", tok=tok, json=body)
            except (TwitchAuthError, TwitchBusy):
                if typ == "channel.chat.message":
                    raise
                continue
            if r.status_code not in (200, 202, 409):          # 409 = already subscribed on this session (a reconnect keeps its subscriptions)
                if typ == "channel.chat.message":
                    if r.status_code in (400, 403):
                        raise TwitchAuthError(f"Twitch refused the chat subscription ({r.status_code}): reconnect Twitch with chat permissions")
                    raise RuntimeError(f"subscribe failed {r.status_code}: {r.text[:200]}")
                console_log.warn("twitch", f"could not subscribe to stream events ({r.status_code}); chat still works", dedupe_s=600)

    async def handle_frame(self, frame, tok):
        """Process one EventSub frame. Returns a reconnect URL when Twitch asks for it."""
        meta, payload = frame.get("metadata", {}), frame.get("payload", {})
        t = meta.get("message_type")
        fid = meta.get("message_id")
        if fid and t in ("notification", "revocation"):         # redelivered frame (reconnect overlap): process once
            if fid in self._frames:
                return None
            self._frames[fid] = 1
            if len(self._frames) > 500:
                self._frames.popitem(last=False)
        if t == "session_welcome":
            self.session_id = payload["session"]["id"]
            if not getattr(self, "reconnecting", False):          # after a session_reconnect the subscriptions carry over; resubscribing only gets a 409
                await asyncio.to_thread(self._subscribe, tok)
            self.reconnecting = False
            self.set_status("connected", f"as {self.user['login']}")
        elif t == "session_reconnect":
            self.reconnecting = True
            return payload["session"]["reconnect_url"]
        elif t == "notification" and meta.get("subscription_type") == "channel.chat.message":
            msg = normalize_event(payload["event"], event_ts(meta.get("message_timestamp")))
            msg.is_self = msg.user_id == self.user["user_id"]
            self.state["last_message"] = time.time()
            self.inbox.put(msg)
        elif t == "notification" and meta.get("subscription_type") == "channel.chat.notification":
            msg = normalize_notice(payload["event"], event_ts(meta.get("message_timestamp")))
            if msg:
                self.state["last_message"] = time.time()
                self.inbox.put(msg)
        elif t == "revocation":
            sub = payload.get("subscription") or {}
            if sub.get("type") == "channel.chat.notification":          # only the stream-event feed is gone: chat keeps working
                console_log.warn("twitch", f"stream-event subscription ended ({sub.get('status', '')})", dedupe_s=600)
            else:                                                       # chat itself is gone: end the session so the run loop re-validates the token
                raise TwitchAuthError(f"subscription revoked ({str(sub.get('status', 'unknown'))[:40]}): reconnect Twitch")
        return None

    async def _pump(self, ws, tok):
        """Read frames until Twitch sends session_reconnect (returns the new URL). Any close/timeout raises."""
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)   # keepalive is ~10 s
            except asyncio.TimeoutError:
                raise RuntimeError("no keepalive from Twitch for 30 s") from None
            if time.time() - self._checked > 3000:
                await self._keep_token(tok)
            url = await self.handle_frame(json.loads(raw), tok)
            if url:
                return url

    async def _session(self, tok):
        """One EventSub session, following session_reconnect hops. The old socket stays open until the new one has
        sent its welcome (Twitch docs). A fresh connect (first, or after any error) subscribes; a hop does not."""
        self.reconnecting = False
        self._checked = time.time()
        ws = await websockets.connect(EVENTSUB_URL, max_size=2**20)
        try:
            while True:
                url = await self._pump(ws, tok)
                new = await websockets.connect(url, max_size=2**20)
                try:
                    raw = await asyncio.wait_for(new.recv(), timeout=30)
                    await self.handle_frame(json.loads(raw), tok)   # welcome of the hopped socket
                except BaseException:
                    await new.close()
                    raise
                await ws.close()
                ws = new
        finally:
            await ws.close()

    async def run(self):
        backoff = 1
        while not self.stop:
            try:
                tok = await self.ensure_auth()
                if not tok:
                    await asyncio.sleep(10)
                    continue
                self.broadcaster_id = self.broadcaster_id or await asyncio.to_thread(
                    self._resolve_broadcaster, tok, config.settings()["channel"])
                if not self.broadcaster_id:
                    self.set_status("error", "channel not found")
                    await asyncio.sleep(30)
                    continue
                self.set_status("connecting")
                await self._session(tok)
            except TwitchAuthError as e:
                self.reconnecting = False
                self.state["reconnects"] += 1
                self.set_status("needs_auth", str(e)[:120])
                await asyncio.sleep(30)                      # Ivan has to act; rechecking every 30 s notices a fresh reconnect quickly
            except TwitchBusy as e:
                self.reconnecting = False
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(e.wait)
            except Exception as e:
                self.reconnecting = False                     # any failure (incl. close code 4007 "invalid reconnect") starts a clean session: full subscribe
                self.state["reconnects"] += 1
                self.set_status("reconnecting", (str(e) or type(e).__name__)[:120])
                await asyncio.sleep(min(backoff, 60))
                backoff *= 2

    # sending ---------------------------------------------------------
    def _send_sync(self, text, reply_to):
        tok = self.tokens()
        body = {"broadcaster_id": self.broadcaster_id, "sender_id": self.user["user_id"], "message": text}
        if reply_to:
            body["reply_parent_message_id"] = reply_to.split(":")[-1]
        r = self._call("post", f"{HELIX}/chat/messages", tok=tok, json=body)
        if r.status_code != 200:
            raise RuntimeError(f"send failed {r.status_code}: {r.text[:200]}")
        d = r.json()["data"][0]
        if not d.get("is_sent"):
            raise RuntimeError("Twitch dropped the message: " + json.dumps(d.get("drop_reason")))
        return d["message_id"]

    def _mod_sync(self, action, user_id="", message_id="", seconds=600, reason=""):
        tok = self.tokens()
        base = {"broadcaster_id": self.broadcaster_id, "moderator_id": self.user["user_id"]}
        if action == "delete":
            r = self._call("delete", f"{HELIX}/moderation/chat", tok=tok, params=dict(base, message_id=message_id))
        else:
            data = {"user_id": user_id, "reason": (reason or "Multi quick action")[:100]}
            if action == "timeout":
                data["duration"] = max(1, min(int(seconds), 1209600))
            r = self._call("post", f"{HELIX}/moderation/bans", tok=tok, params=base, json={"data": data})
        if r.status_code not in (200, 204):
            raise RuntimeError(f"{action} failed {r.status_code}: {r.text[:160]}")
        return True

    async def moderate(self, action, **kw):
        need = {"delete": "mod_delete", "timeout": "mod_timeout", "ban": "mod_timeout"}.get(action)
        if not need:
            raise RuntimeError("unknown moderation action")
        if not (self.user and self.capabilities.get(need)):
            raise RuntimeError("Moderation is not authorised: reconnect Twitch with moderator permissions")
        return await asyncio.to_thread(self._mod_sync, action, **kw)

    async def send(self, text, reply_to=None):
        if not (self.user and self.capabilities.get("send")):
            raise RuntimeError("Twitch send is not authorised (needs user:write:chat)")
        try:
            mid = await asyncio.to_thread(self._send_sync, text, reply_to)
        except TwitchAuthError as e:
            self.set_status("needs_auth", str(e)[:120])
            raise
        self.sent_ids.add(mid)
        return f"twitch:{config.settings()['channel']}:{mid}"
