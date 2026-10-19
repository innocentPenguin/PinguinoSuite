"""Discord connector: Gateway v10 (read, needs the MESSAGE_CONTENT privileged intent) + REST create-message (send/reply).

Official API. Uses a BOT token kept in Credential Manager (secrets_store 'discord_token'), never in JSON or logs.
Only channel ids listed in settings `discord_channels` are read or written; a send targets exactly one channel.
"""
import asyncio
import json
import random
import time

import requests
import websockets

import config
import secrets_store
from connectors.base import Connector
from models import ChatMessage

GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
API = "https://discord.com/api/v10"
INTENTS = 1 | 512 | 32768        # GUILDS | GUILD_MESSAGES | MESSAGE_CONTENT


def normalize_message(d, channels, my_id=None):
    """MESSAGE_CREATE data -> ChatMessage, or None if the channel isn't watched. Pure, unit-tested."""
    cid = str(d.get("channel_id", ""))
    if channels and cid not in {str(c) for c in channels}:
        return None
    a = d.get("author") or {}
    ref = d.get("message_reference") or {}
    mem = d.get("member") or {}
    ref_msg = d.get("referenced_message") or {}
    return ChatMessage(
        id=f"discord:{cid}:{d['id']}", platform="discord", channel=cid, user_id=str(a.get("id", "")),
        user=(a.get("username") or "").lower(), display=mem.get("nick") or a.get("global_name") or a.get("username", ""),
        text=d.get("content", ""), ts=time.time(), badges=[],
        reply_to=f"discord:{cid}:{ref['message_id']}" if ref.get("message_id") else "",
        reply_to_user=((ref_msg.get("author") or {}).get("username") or "").lower(),
        is_bot=bool(a.get("bot")), is_self=bool(my_id) and str(a.get("id")) == str(my_id),
        raw_type="reply" if ref.get("message_id") else "text")


class Discord(Connector):
    platform, label, official = "discord", "Discord", True
    capabilities = {"read": True, "send": True, "reply": True, "badges": False, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.user = None
        self.stop = False
        self.seq = None

    def token(self):
        return secrets_store.get("discord_token")

    def channels(self):
        return config.settings().get("discord_channels", [])

    async def handle(self, ws, frame):
        op, t, d = frame.get("op"), frame.get("t"), frame.get("d")
        if frame.get("s") is not None:
            self.seq = frame["s"]
        if op == 10:
            asyncio.create_task(self._heartbeat(ws, d["heartbeat_interval"] / 1000))
            await ws.send(json.dumps({"op": 2, "d": {"token": self.token(), "intents": INTENTS,
                                                     "properties": {"os": "windows", "browser": "pinguino", "device": "pinguino"}}}))
        elif op == 7 or op == 9:
            raise RuntimeError("gateway asked to reconnect")
        elif t == "READY":
            self.user = {"login": d["user"]["username"], "user_id": d["user"]["id"]}
            self.set_status("connected", f"as {self.user['login']}; {len(self.channels())} channel(s)")
        elif t == "MESSAGE_CREATE":
            m = normalize_message(d, self.channels(), self.user and self.user["user_id"])
            if m:
                self.state["last_message"] = time.time()
                self.inbox.put(m)

    async def _heartbeat(self, ws, interval):
        await asyncio.sleep(interval * random.random())
        while True:
            try:
                await ws.send(json.dumps({"op": 1, "d": self.seq}))
            except Exception:
                return
            await asyncio.sleep(interval)

    async def run(self):
        backoff = 1
        while not self.stop:
            if not self.token():
                self.set_status("needs_auth", "Add the Discord bot token (Settings > Discord)")
                await asyncio.sleep(10)
                continue
            if not self.channels():
                self.set_status("needs_auth", "Choose at least one Discord channel id")
                await asyncio.sleep(10)
                continue
            try:
                self.set_status("connecting")
                async with websockets.connect(GATEWAY, max_size=2**22) as ws:
                    backoff = 1
                    async for raw in ws:
                        await self.handle(ws, json.loads(raw))
            except Exception as e:
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(min(backoff, 60))
                backoff *= 2

    def _send_sync(self, text, reply_to):
        chans = self.channels()
        cid = str(chans[0])
        body = {"content": text, "allowed_mentions": {"parse": []}}
        if reply_to:
            parts = reply_to.split(":")
            cid, body["message_reference"] = parts[1], {"message_id": parts[2], "channel_id": parts[1]}
        if cid not in {str(c) for c in chans}:
            raise RuntimeError("channel not in the Discord channel list")
        r = requests.post(f"{API}/channels/{cid}/messages", json=body,
                          headers={"Authorization": f"Bot {self.token()}"}, timeout=10)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"send failed {r.status_code}: {r.text[:160]}")
        return f"discord:{cid}:{r.json()['id']}"

    async def send(self, text, reply_to=None):
        if not (self.user and self.capabilities.get("send")):
            raise RuntimeError("Discord is not connected")
        return await asyncio.to_thread(self._send_sync, text, reply_to)
