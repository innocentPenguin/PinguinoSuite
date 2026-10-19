"""Twitch connector: EventSub WebSocket `channel.chat.message` (read) + Helix `POST /chat/messages` (send/reply).

Official API. Scopes: user:read:chat user:write:chat. Tokens come from Credential Manager (secrets_store),
placed there by the site's broadcaster-only "Connect Multi" flow (see Docs/PinguinoMulti/CONTRACTS.md) or
pasted manually for development. Refresh goes through the site (it holds the client secret).
"""
import asyncio
import json
import time

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


NOTICE_EVENT = {"sub": "sub", "resub": "resub", "sub_gift": "gift", "community_sub_gift": "gift", "gift_paid_upgrade": "gift",
                "prime_paid_upgrade": "sub", "raid": "raid", "announcement": "announcement", "bits_badge_tier": "cheer"}


def normalize_notice(ev):
    """Twitch channel.chat.notification event (sub, resub, gift, raid, announcement) -> ChatMessage with .event. Pure."""
    chan, nt = ev["broadcaster_user_login"], ev.get("notice_type", "")
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
        user=user, display=ev.get("chatter_user_name") or user, text=text, ts=time.time(),
        badges=[b["set_id"] for b in ev.get("badges", [])], raw_type=nt, color=ev.get("color") or "",
        event=NOTICE_EVENT.get(nt, "announcement"), amount=amount)


def normalize_event(ev):
    """Twitch channel.chat.message event -> ChatMessage. Pure, unit-tested."""
    chan = ev["broadcaster_user_login"]
    reply = ev.get("reply") or {}
    badges = [b["set_id"] for b in ev.get("badges", [])]
    return ChatMessage(
        id=f"twitch:{chan}:{ev['message_id']}", platform="twitch", channel=chan,
        user_id=ev["chatter_user_id"], user=ev["chatter_user_login"],
        display=ev.get("chatter_user_name") or ev["chatter_user_login"],
        text=(ev.get("message") or {}).get("text", ""), ts=time.time(), badges=badges,
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

    # auth ------------------------------------------------------------
    def tokens(self):
        return secrets_store.get("twitch_tokens")

    def _headers(self, tok):
        return {"Authorization": f"Bearer {tok['access_token']}", "Client-Id": tok.get("client_id") or
                config.settings()["twitch_client_id"]}

    def validate(self, tok):
        r = requests.get(VALIDATE, headers={"Authorization": f"OAuth {tok['access_token']}"}, timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        tok["client_id"] = d.get("client_id", tok.get("client_id"))
        return d

    def refresh(self, tok):
        site = secrets_store.get("site_url") or "https://innocentpenguin.com"
        r = requests.post(f"{site}/api/multi/refresh", json={"refresh_token": tok.get("refresh_token")}, timeout=10)
        if r.status_code != 200:
            return None
        new = r.json()
        tok.update({k: new[k] for k in ("access_token", "refresh_token", "client_id") if k in new})
        secrets_store.put("twitch_tokens", tok)
        return tok

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
        r = requests.get(f"{HELIX}/users", params={"login": login}, headers=self._headers(tok), timeout=10)
        data = r.json().get("data", []) if r.status_code == 200 else []
        return data[0]["id"] if data else None

    # reading ---------------------------------------------------------
    def _subscribe(self, tok):
        cond = {"broadcaster_user_id": self.broadcaster_id, "user_id": self.user["user_id"]}
        for typ in ("channel.chat.message", "channel.chat.notification"):
            body = {"type": typ, "version": "1", "condition": cond,
                    "transport": {"method": "websocket", "session_id": self.session_id}}
            r = requests.post(f"{HELIX}/eventsub/subscriptions", json=body, headers=self._headers(tok), timeout=10)
            if r.status_code not in (200, 202):
                if typ == "channel.chat.message":
                    raise RuntimeError(f"subscribe failed {r.status_code}: {r.text[:200]}")
                console_log.warn("twitch", f"could not subscribe to stream events ({r.status_code}); chat still works", dedupe_s=600)

    async def handle_frame(self, frame, tok):
        """Process one EventSub frame. Returns a reconnect URL when Twitch asks for it."""
        meta, payload = frame.get("metadata", {}), frame.get("payload", {})
        t = meta.get("message_type")
        if t == "session_welcome":
            self.session_id = payload["session"]["id"]
            await asyncio.to_thread(self._subscribe, tok)
            self.set_status("connected", f"as {self.user['login']}")
        elif t == "session_reconnect":
            return payload["session"]["reconnect_url"]
        elif t == "notification" and meta.get("subscription_type") == "channel.chat.message":
            msg = normalize_event(payload["event"])
            msg.is_self = msg.user_id == self.user["user_id"]
            self.state["last_message"] = time.time()
            self.inbox.put(msg)
        elif t == "notification" and meta.get("subscription_type") == "channel.chat.notification":
            msg = normalize_notice(payload["event"])
            self.state["last_message"] = time.time()
            self.inbox.put(msg)
        elif t == "revocation":
            self.set_status("needs_auth", "subscription revoked; reconnect Twitch")
        return None

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
                url = EVENTSUB_URL
                while url and not self.stop:
                    async with websockets.connect(url, max_size=2**20) as ws:
                        backoff, url = 1, None
                        while True:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)   # keepalive is ~10 s
                            url = await self.handle_frame(json.loads(raw), tok)
                            if url:
                                break
            except Exception as e:
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(min(backoff, 60))
                backoff *= 2

    # sending ---------------------------------------------------------
    def _send_sync(self, text, reply_to):
        tok = self.tokens()
        body = {"broadcaster_id": self.broadcaster_id, "sender_id": self.user["user_id"], "message": text}
        if reply_to:
            body["reply_parent_message_id"] = reply_to.split(":")[-1]
        r = requests.post(f"{HELIX}/chat/messages", json=body, headers=self._headers(tok), timeout=10)
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
            r = requests.delete(f"{HELIX}/moderation/chat", params=dict(base, message_id=message_id),
                                headers=self._headers(tok), timeout=10)
        else:
            data = {"user_id": user_id, "reason": (reason or "Multi quick action")[:100]}
            if action == "timeout":
                data["duration"] = max(1, min(int(seconds), 1209600))
            r = requests.post(f"{HELIX}/moderation/bans", params=base, json={"data": data},
                              headers=self._headers(tok), timeout=10)
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
        mid = await asyncio.to_thread(self._send_sync, text, reply_to)
        self.sent_ids.add(mid)
        return f"twitch:{config.settings()['channel']}:{mid}"
