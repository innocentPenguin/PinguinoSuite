"""TikTok LIVE connector — UNOFFICIAL and READ-ONLY.

TikTok has no official live-chat API. This uses the optional third-party `TikTokLive` package (reverse-engineered,
can break or violate ToS). It is OFF by default (setting tiktok_enabled + tiktok_user) and never sends.
Event mapping and the import guard live in connectors/tiktok_live.py.
"""
import asyncio
import time

import config
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


class TikTok(Connector):
    platform, label, official = "tiktok", "TikTok (unofficial)", False
    capabilities = {"read": True, "send": False, "reply": False, "badges": False, "history": False}

    def __init__(self, inbox, emit):
        super().__init__(inbox, emit)
        self.stop = False

    async def run(self):
        while not self.stop:
            s = config.settings()
            user = tiktok_live.handle(s)
            if not (s.get("tiktok_enabled") and user):
                self.set_status("disabled", "Off by default (unofficial). Enable in settings and set the @handle.")
                await asyncio.sleep(10)
                continue
            ok, why = tiktok_live.available()
            if not ok:
                self.set_status("needs_auth", why + " (optional package; ask to install)")
                await asyncio.sleep(60)
                continue
            try:
                from TikTokLive import TikTokLiveClient
                import TikTokLive.events as tev
                kw = {"tiktok_sign_url": s["tiktok_sign_url"]} if s.get("tiktok_sign_url") else {}
                try:
                    client = TikTokLiveClient(unique_id="@" + user, **kw)
                except TypeError:                     # option names differ between library versions
                    client = TikTokLiveClient(unique_id="@" + user)
                tiktok_live.attach(client, tev, user, self.inbox.put, self.state)
                if hasattr(tev, "RoomUserSeqEvent"):                 # room viewer count (field names differ between versions)
                    async def on_room(ev):
                        n = getattr(ev, "total", None) or getattr(ev, "m_total", None) or getattr(ev, "viewer_count", None)
                        if n is not None:
                            self.state["viewers"] = int(n)
                    client.add_listener(tev.RoomUserSeqEvent, on_room)
                if hasattr(tev, "ConnectEvent"):
                    async def on_connect(ev):
                        self.set_status("connected", f"@{user} (unofficial)")
                    client.add_listener(tev.ConnectEvent, on_connect)
                self.set_status("connecting")
                await client.start()
            except Exception as e:
                self.state["reconnects"] += 1
                self.set_status("reconnecting", str(e)[:120])
                await asyncio.sleep(30)
