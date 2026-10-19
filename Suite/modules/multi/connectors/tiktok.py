"""TikTok LIVE connector — UNOFFICIAL and READ-ONLY.

TikTok has no official live-chat API. This uses the optional third-party `TikTokLive` package (reverse-engineered,
can break or violate ToS). It is OFF by default (setting tiktok_enabled + tiktok_user) and never sends.
"""
import asyncio
import time

import config
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


class TikTok(Connector):
    platform, label, official = "tiktok", "TikTok (unofficial)", False
    capabilities = {"read": True, "send": False, "reply": False, "badges": False, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.stop = False

    async def run(self):
        while not self.stop:
            s = config.settings()
            if not (s.get("tiktok_enabled") and s.get("tiktok_user")):
                self.set_status("disabled", "Off by default (unofficial). Enable in settings.")
                await asyncio.sleep(10)
                continue
            try:
                from TikTokLive import TikTokLiveClient
                from TikTokLive.events import CommentEvent
            except ImportError:
                self.set_status("needs_auth", "Install the optional 'TikTokLive' package to use this")
                await asyncio.sleep(30)
                continue
            user = s["tiktok_user"].lstrip("@")
            try:
                client = TikTokLiveClient(unique_id="@" + user)

                async def on_comment(ev: CommentEvent):
                    self.state["last_message"] = time.time()
                    self.inbox.put(normalize_comment(ev, user))
                client.add_listener(CommentEvent, on_comment)
                self.set_status("connecting")
                await client.start()
            except Exception as e:
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(30)
