"""Kick connector. Two inputs, both READ-ONLY here:

1. Official webhooks (chat, follows, subs, gifts, KICKs, redeems): Kick POSTs to /hook/kick; `ingest_webhook` verifies the RSA signature with Kick's
   public key and feeds the normaliser. Needs a public HTTPS URL for Kick to reach (site relay or tunnel, see Docs/MULTISTREAM_PLAN.md) and Ivan's Kick app login.
2. UNOFFICIAL chat feed over Kick's public Pusher socket (the same one kick.com's own chat page uses). Chat only, no login, no public URL; can break any time.
   Needs settings kick_enabled + kick_chatroom_id. Off by default.
"""
import asyncio
import base64
import json
import time

import requests
import websockets

import config
import xplat
from connectors.base import Connector

PUSHER = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
PUBKEY_URL = "https://api.kick.com/public/v1/public-key"


class Kick(Connector):
    platform, label, official = "kick", "Kick", False
    capabilities = {"read": True, "send": False, "reply": False, "badges": True, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.stop = False
        self._key, self._key_ts = None, 0
        self.state["webhooks"] = 0

    # official webhook path ---------------------------------------------------------------------
    def _public_key(self, force=False):
        from cryptography.hazmat.primitives import serialization
        if self._key is None or force or time.time() - self._key_ts > 3600:
            r = requests.get(PUBKEY_URL, timeout=10)
            r.raise_for_status()
            pem = (r.json().get("data") or {}).get("public_key") or r.text
            self._key = serialization.load_pem_public_key(pem.encode())
            self._key_ts = time.time()
        return self._key

    def verify(self, msg_id, timestamp, body, signature):
        """Kick signs '<message id>.<timestamp>.<raw body>' (RSA PKCS#1 v1.5, SHA-256, base64). Refetches the key once (Kick may rotate it)."""
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        try:
            sig = base64.b64decode(signature or "")
        except Exception:
            return False
        data = f"{msg_id}.{timestamp}.".encode() + body
        for force in (False, True):
            if force and time.time() - self._key_ts < 60:        # unauthenticated endpoint: never let bad signatures trigger a key download per request
                break
            try:
                self._public_key(force).verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
                return True
            except InvalidSignature:
                continue
            except Exception:
                return False
        return False

    async def ingest_webhook(self, headers, body):
        """-> (http status, text). Signature failure = 401; unknown/ignored events are accepted (200) so Kick never unsubscribes us."""
        if not await asyncio.to_thread(self.verify, headers.get("kick-event-message-id", ""), headers.get("kick-event-message-timestamp", ""), body,
                                       headers.get("kick-event-signature", "")):
            return 401, "bad signature"
        try:
            m = xplat.kick_webhook(headers.get("kick-event-type", ""), json.loads(body), headers.get("kick-event-message-id", ""))
        except ValueError:
            return 400, "bad json"
        if m:
            self.state["webhooks"] += 1
            self.state["last_message"] = time.time()
            self.inbox.put(m)
            if self.state["status"] in ("disabled", "waiting", "disconnected"):
                self.set_status("connected", "receiving Kick webhooks")
        return 200, "ok"

    # unofficial chat feed ----------------------------------------------------------------------
    async def run(self):
        while not self.stop:
            s = config.settings()
            room, chan = str(s.get("kick_chatroom_id") or "").strip(), str(s.get("kick_channel") or "").strip().lower()
            if not (s.get("kick_enabled") and room.isdigit()):
                if self.state["status"] != "connected" or not self.state["webhooks"]:
                    self.set_status("disabled", "Off by default. Settings: kick_enabled + kick_chatroom_id (unofficial feed), or use the webhook")
                await asyncio.sleep(10)
                continue
            try:
                self.set_status("connecting")
                async with websockets.connect(PUSHER, max_size=2**20, ping_interval=None) as ws:
                    await ws.send(json.dumps({"event": "pusher:subscribe", "data": {"auth": "", "channel": f"chatrooms.{room}.v2"}}))
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=130)
                        fr = json.loads(raw)
                        ev = fr.get("event", "")
                        if ev == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        elif ev == "pusher_internal:subscription_succeeded":
                            self.set_status("connected", f"chatroom {room} (unofficial)")
                        elif ev.endswith("ChatMessageEvent"):
                            data = fr.get("data")
                            m = xplat.kick_pusher(ev, json.loads(data) if isinstance(data, str) else data, chan or "kick")
                            if m:
                                self.state["last_message"] = time.time()
                                self.inbox.put(m)
            except Exception as e:
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(20)
