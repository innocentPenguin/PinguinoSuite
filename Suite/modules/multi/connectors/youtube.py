"""YouTube Live Chat connector (official Data API v3). Read + send; no reply threading on YouTube.

Quota-aware: polls liveChat/messages at the server-suggested pollingIntervalMillis (min 5 s). Needs a Google OAuth
access token with the youtube scope in Credential Manager ('youtube_token'; write-only endpoint). Without it the
connector sits in needs_auth and the rest of Multi is unaffected.
"""
import asyncio
import time

import requests

import config
import secrets_store
from connectors import youtube_auth, youtube_innertube
import xplat
from connectors.base import Connector, SendRejected, refused
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
        self.reader = None
        self.fail_since = None
        self.video_id = None
        self.on_cleared = None
        self.send_id = self.send_title = ""            # the signed-in (SEND) account; reading never depends on it
        self._id_tok = None
        self._id_try = 0.0
        self._sent = []                               # [(normalized text, ts)] of lines we sent: their read-back echo is dropped (server.send already shows them once)
        self._send_chat = (None, None)                # (video id, liveChatId) of the read side's live video

    def _h(self):
        return {"Authorization": f"Bearer {youtube_auth.access_token()}"}

    def _find_chat(self):
        r = requests.get(f"{API}/liveBroadcasts", params={"part": "snippet", "broadcastStatus": "active", "mine": "true"},
                         headers=self._h(), timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None, None
        self.video_id = items[0].get("id")
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
        return j.get("items", []), max(float(config.settings().get("youtube_min_poll_s", 10)), j.get("pollingIntervalMillis", 6000) / 1000)   # 5 quota units per poll of 10,000/day

    @staticmethod
    def failure_plan(e):
        """Exception from an API call -> (status, detail, sleep_s). 401: token dead (needs sign-in); 429/403 quota: back off hard so we never hammer; else retry in 20 s."""
        r = getattr(e, "response", None)
        code = getattr(r, "status_code", None)
        if code == 401:
            return "needs_auth", "YouTube token rejected: sign in again", 60
        if code in (429, 403):
            ra = 0
            try:
                ra = float((getattr(r, "headers", None) or {}).get("Retry-After") or 0)
            except (TypeError, ValueError):
                pass
            return "reconnecting", f"YouTube {code} (quota/rate limit): backing off", min(max(ra, 600 if code == 403 else 120), 3600)
        return "reconnecting", str(e)[:120], 20

    def _cleared(self, video, cleared):
        for scope, ident in cleared:
            try:
                if self.on_cleared:
                    if scope == "message":
                        self.on_cleared("message", "delete", platform="youtube", channel=video, ids=[ident])
                    else:
                        self.on_cleared("user", "ban", platform="youtube", channel=video, user_id=ident)
                else:
                    self.emit({"type": "message.cleared", "ids": [ident] if scope == "message" else [], "scope": scope,
                               "user_id": ident if scope == "user" else "", "reason": "delete" if scope == "message" else "ban"})
            except Exception:
                pass

    def _put(self, m):
        """inbox.put, except the read-back of a line WE just sent (send account, same text, <= 30 s): the sender already ingested it,
        and YouTube's API id differs from the reader's id so the pipeline dedupe cannot catch it."""
        now = time.time()
        self._sent = [(t, ts) for t, ts in self._sent if now - ts <= 30]
        if m.is_bot or (self.send_id and m.user_id == self.send_id):
            key = " ".join(str(m.text).lower().split())
            for i, (t, ts) in enumerate(self._sent):
                if t == key:
                    del self._sent[i]
                    return
        self.inbox.put(m)

    def _mine(self):
        """Own accounts for self-echo marking: the streamer (owner badge / read channel id) and the send account."""
        return {"read": [], "send": [self.send_id] if self.send_id else [], "send_names": [self.send_title.lower()] if self.send_title else []}

    def _identity_sync(self):
        r = requests.get(f"{API}/channels", params={"part": "snippet", "mine": "true"}, headers=self._h(), timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return "", ""
        return str(items[0].get("id", "")), str((items[0].get("snippet") or {}).get("title", ""))

    async def _identity(self):
        """Who the saved sign-in is ("sending as ..."). Throttled; never raises; cleared when the sign-in is removed."""
        tok = secrets_store.get("youtube_token")
        if not tok:
            if self.send_id or self.state.get("send_as"):
                self.send_id = self.send_title = ""
                self.state["send_as"] = ""
                self._id_tok = None
            return
        if tok == self._id_tok and self.send_id:
            return
        if time.time() - self._id_try < 60:
            return
        self._id_try = time.time()
        try:
            self.send_id, self.send_title = await asyncio.to_thread(self._identity_sync)
            self._id_tok = tok
            self.state["send_as"] = self.send_title
            if self.reader:
                self.reader.my_channel = self._mine()
        except Exception:
            pass

    def _live_chat_for(self, video):
        r = requests.get(f"{API}/videos", params={"part": "liveStreamingDetails", "id": video}, headers=self._h(), timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        return ((items[0].get("liveStreamingDetails") or {}).get("activeLiveChatId") if items else None) or None

    def _read_video(self):
        """The live video the READ side watches (None if unknown): the running reader, else the pinned video id."""
        if self.reader:
            return self.reader.video
        vid = str(config.settings().get("youtube_video_id") or "").strip()
        return youtube_innertube.watch_target(vid)[0] or vid or None

    def _send_chat_id(self):
        """liveChatId to send into. Fast read mode: the read video's chat, looked up with the SEND account's token (public data, any live video).
        Falls back to the send account's own broadcast only when no read-side video is known."""
        if str(config.settings().get("youtube_read_mode", "innertube")).lower() != "api":
            vid = self._read_video()
            if not vid and str(config.settings().get("youtube_channel") or "").strip():
                try:
                    vid = youtube_innertube.Reader.resolve(config.settings().get("youtube_channel"))
                except Exception:
                    vid = None
            if vid:
                if self._send_chat[0] != vid:
                    self._send_chat = (vid, self._live_chat_for(vid))
                return self._send_chat[1]
        if self.chat_id:
            return self.chat_id
        self.chat_id, self.me = self._find_chat()
        return self.chat_id

    def _video_source(self):
        """Which live video to read in innertube mode: setting video id > setting channel's /live page. The signed-in account is the SEND account and never decides what is read."""
        s = config.settings()
        vid = str(s.get("youtube_video_id") or "").strip()
        ch = str(s.get("youtube_channel") or "").strip()
        if vid or ch:
            return youtube_innertube.Reader.resolve(ch, vid)
        raise LookupError("setup")

    async def _api_step(self):
        """One cycle of the official-API reader (also the fallback)."""
        if not secrets_store.get("youtube_token"):
            self.set_status("needs_auth", "Add a YouTube OAuth token")
            await asyncio.sleep(15)
            return
        try:
            if not self.chat_id:
                self.chat_id, self.me = await asyncio.to_thread(self._find_chat)
                if not self.chat_id:
                    self.set_status("waiting", "no active YouTube broadcast")
                    await asyncio.sleep(30)
                    return
                self.page = None
                self.set_status("connected", "live chat found (official API)")
            items, wait = await asyncio.to_thread(self._poll)
            for it in items:
                m = normalize_item(it, self.chat_id, self.me) or xplat.youtube_event(it, self.chat_id)
                if m:
                    self.state["last_message"] = time.time()
                    self._put(m)
            await asyncio.sleep(wait)
        except Exception as e:
            self.state["reconnects"] += 1
            self.chat_id = None
            st, detail, wait = self.failure_plan(e)
            self.set_status(st, detail)
            await asyncio.sleep(wait)

    async def _innertube_step(self):
        try:
            if not self.reader:
                video = await asyncio.to_thread(self._video_source)
                if not video:
                    self.set_status("waiting", "not live on YouTube right now")
                    await asyncio.sleep(20)
                    return
                rd = youtube_innertube.Reader(video, self._mine())
                for m in (await asyncio.to_thread(rd.fetch))[0]:
                    self.state["last_message"] = time.time()
                    self._put(m)
                self.reader, self.fail_since = rd, None
                self.set_status("connected", f"live chat {video} (fast mode)")
                await asyncio.sleep(rd.wait)
                return
            msgs, cleared = await asyncio.to_thread(self.reader.poll)
            for m in msgs:
                self.state["last_message"] = time.time()
                self._put(m)
            if cleared:
                self._cleared(self.reader.video, cleared)
            self.fail_since = None
            await asyncio.sleep(self.reader.wait)
        except LookupError:
            self.set_status("needs_setup", "Set your YouTube channel (@handle) in Multi's settings, or sign in to YouTube")
            await asyncio.sleep(15)
        except youtube_innertube.NotLive as e:
            self.reader = None
            self.set_status("waiting", "not live on YouTube right now")
            await asyncio.sleep(20)
        except youtube_innertube.Expired:
            self.reader = None                              # next round fetches a fresh continuation
            await asyncio.sleep(1)
        except Exception as e:
            self.state["reconnects"] += 1
            self.reader = None
            self.fail_since = self.fail_since or time.time()
            self.set_status("reconnecting", f"fast mode: {str(e)[:100]}")
            fb = float(config.settings().get("youtube_innertube_fallback_min", 5) or 0) * 60
            if fb and secrets_store.get("youtube_token") and time.time() - self.fail_since >= fb:
                self.set_status("reconnecting", "fast mode down: reading through the official API (slow) until it is back")
                await self._api_step()
                self.reader = None
            else:
                await asyncio.sleep(5)

    async def run(self):
        while not self.stop:
            await self._identity()
            if str(config.settings().get("youtube_read_mode", "innertube")).lower() == "api":
                await self._api_step()
            else:
                await self._innertube_step()

    def _send_sync(self, text):
        chat = self._send_chat_id()
        if not chat:
            raise SendRejected("YouTube has no live chat to send to yet (is the stream live?)")
        r = requests.post(f"{API}/liveChat/messages?part=snippet", headers=self._h(), timeout=10,
                          json={"snippet": {"liveChatId": chat, "type": "textMessageEvent", "textMessageDetails": {"messageText": text}}})
        if r.status_code != 200:
            if r.status_code in (403, 404):
                self._send_chat = (None, None)
            raise refused(r.status_code, f"send failed {r.status_code}: {r.text[:160]}")
        self._sent.append((" ".join(text.lower().split()), time.time()))
        vid = self._send_chat[0] if self._send_chat[1] == chat else None       # same id prefix as the reader's lines (video id) where known
        return f"youtube:{vid or chat}:{r.json()['id']}"

    async def send(self, text, reply_to=None):
        if not secrets_store.get("youtube_token"):
            raise SendRejected("YouTube send account not signed in")
        return await self.send_once(text, reply_to, lambda: asyncio.to_thread(self._send_sync, text))
