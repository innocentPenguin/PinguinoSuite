"""YouTube Live Chat connector (official Data API v3). Read + send; no reply threading on YouTube.

Quota-aware: polls liveChat/messages at the server-suggested pollingIntervalMillis (min 5 s). Needs a Google OAuth
access token with the youtube scope in Credential Manager ('youtube_token'; write-only endpoint). Without it the
connector sits in needs_auth and the rest of Multi is unaffected.
"""
import asyncio
import time

import requests

import secrets_store
from connectors.base import Connector
from models import ChatMessage

API = "https://www.googleapis.com/youtube/v3"


def normalize_item(it, chat_id, my_channel_id=None):
    sn, au = it.get("snippet", {}), it.get("authorDetails", {})
    if sn.get("type") != "textMessageEvent":
        return None
    d = sn.get("textMessageDetails", {}).get("messageText", "") or sn.get("displayMessage", "")
    badges = [b for b, k in (("moderator", "isChatModerator"), ("owner", "isChatOwner"), ("subscriber", "isChatSponsor"))
              if au.get(k)]
    ts = time.time()
    return ChatMessage(id=f"youtube:{chat_id}:{it['id']}", platform="youtube", channel=chat_id,
                       user_id=au.get("channelId", ""), user=(au.get("displayName") or "").lower(),
                       display=au.get("displayName", ""), text=d, ts=ts, badges=badges,
                       is_self=bool(my_channel_id) and au.get("channelId") == my_channel_id)


class YouTube(Connector):
    platform, label, official = "youtube", "YouTube", True
    capabilities = {"read": True, "send": True, "reply": False, "badges": True, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.stop = False
        self.chat_id = None
        self.me = None
        self.page = None

    def _h(self):
        return {"Authorization": f"Bearer {secrets_store.get('youtube_token')}"}

    def _find_chat(self):
        r = requests.get(f"{API}/liveBroadcasts", params={"part": "snippet", "broadcastStatus": "active", "mine": "true"},
                         headers=self._h(), timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None, None
        sn = items[0]["snippet"]
        return sn.get("liveChatId"), sn.get("channelId")

    def _poll(self):
        p = {"liveChatId": self.chat_id, "part": "snippet,authorDetails", "maxResults": 200}
        if self.page:
            p["pageToken"] = self.page
        r = requests.get(f"{API}/liveChat/messages", params=p, headers=self._h(), timeout=10)
        r.raise_for_status()
        j = r.json()
        self.page = j.get("nextPageToken")
        return j.get("items", []), max(5.0, j.get("pollingIntervalMillis", 6000) / 1000)

    async def run(self):
        while not self.stop:
            if not secrets_store.get("youtube_token"):
                self.set_status("needs_auth", "Add a YouTube OAuth token")
                await asyncio.sleep(15)
                continue
            try:
                if not self.chat_id:
                    self.chat_id, self.me = await asyncio.to_thread(self._find_chat)
                    if not self.chat_id:
                        self.set_status("waiting", "no active YouTube broadcast")
                        await asyncio.sleep(30)
                        continue
                    self.page = None
                    self.set_status("connected", "live chat found")
                items, wait = await asyncio.to_thread(self._poll)
                for it in items:
                    m = normalize_item(it, self.chat_id, self.me)
                    if m:
                        self.state["last_message"] = time.time()
                        self.inbox.put(m)
                await asyncio.sleep(wait)
            except Exception as e:
                self.state["reconnects"] += 1
                self.chat_id = None
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(20)

    def _send_sync(self, text):
        r = requests.post(f"{API}/liveChat/messages?part=snippet", headers=self._h(), timeout=10,
                          json={"snippet": {"liveChatId": self.chat_id, "type": "textMessageEvent",
                                            "textMessageDetails": {"messageText": text}}})
        if r.status_code != 200:
            raise RuntimeError(f"send failed {r.status_code}: {r.text[:160]}")
        return f"youtube:{self.chat_id}:{r.json()['id']}"

    async def send(self, text, reply_to=None):
        if not self.chat_id:
            raise RuntimeError("YouTube is not connected to a live chat")
        return await asyncio.to_thread(self._send_sync, text)
