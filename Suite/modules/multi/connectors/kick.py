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
import secrets_store
import xplat
from connectors import kick_auth
from connectors.base import Connector, SendRejected, refused

PUSHER = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
PUBKEY_URL = "https://api.kick.com/public/v1/public-key"
API = "https://api.kick.com/public/v1"


class Kick(Connector):
    platform, label, official = "kick", "Kick", False
    capabilities = {"read": True, "send": False, "reply": False, "badges": True, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.stop = False
        self._key, self._key_ts = None, 0
        self.state["webhooks"] = 0
        self.broadcaster_id = None
        self.sent_ids = set()

    # sending (official API, off until a token with chat:write exists) --------------------------
    def refresh_caps(self):
        """Send is offered only when the stored Kick token was granted chat:write. Cheap; called from the run loop and before each send."""
        rec = secrets_store.get("kick_oauth")
        scopes = str((rec or {}).get("scope", "") if isinstance(rec, dict) else "").replace(",", " ").split()
        ok = bool(secrets_store.get("kick_token")) and "chat:write" in scopes
        self.capabilities = dict(self.capabilities, send=ok, reply=ok)
        return ok

    def describe(self):
        self.refresh_caps()
        return super().describe()

    def _headers(self):
        return {"Authorization": f"Bearer {kick_auth.access_token()}"}

    def _my_id(self):
        if self.broadcaster_id is None:
            r = requests.get(f"{API}/channels", headers=self._headers(), timeout=10)
            if r.status_code != 200:
                raise RuntimeError(f"Kick channel lookup failed {r.status_code}: {r.text[:120]}")
            try:
                self.broadcaster_id = int(((r.json().get("data") or [{}])[0]).get("broadcaster_user_id"))
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                raise RuntimeError("Kick channel lookup returned an unexpected body")
        return self.broadcaster_id

    def _send_sync(self, text, reply_to):
        body = {"content": str(text)[:500], "type": "user", "broadcaster_user_id": self._my_id()}
        if reply_to:
            body["reply_to_message_id"] = str(reply_to).split(":")[-1]
        r = requests.post(f"{API}/chat", json=body, headers=self._headers(), timeout=10)
        if r.status_code != 200:
            raise refused(r.status_code, f"Kick send failed {r.status_code}: {r.text[:160]}")
        d = r.json().get("data") or {}
        if not d.get("is_sent"):
            raise SendRejected("Kick did not send the message")
        return d.get("message_id", "")

    async def send(self, text, reply_to=None):
        if not self.refresh_caps():
            raise SendRejected("Kick send is not authorised (sign in to Kick with the chat:write scope)")
        mid = await self.send_once(text, reply_to, lambda: asyncio.to_thread(self._send_sync, text, reply_to))
        self.sent_ids.add(mid)
        return f"kick:{config.settings().get('kick_channel') or 'kick'}:{mid}"

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
            self.refresh_caps()
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
                        try:
                            fr = json.loads(raw)
                            ev = fr.get("event", "")
                        except (ValueError, AttributeError):
                            continue                 # one bad frame must not drop the connection
                        if ev == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        elif ev == "pusher_internal:subscription_succeeded":
                            self.set_status("connected", f"chatroom {room} (unofficial)")
                        elif ev.endswith("ChatMessageEvent"):
                            data = fr.get("data")
                            try:
                                data = json.loads(data) if isinstance(data, str) else data
                            except ValueError:
                                continue
                            m = xplat.kick_pusher(ev, data, chan or "kick")
                            if m:
                                self.state["last_message"] = time.time()
                                self.inbox.put(m)
            except Exception as e:
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(20)
