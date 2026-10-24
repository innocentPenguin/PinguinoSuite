"""YouTube live chat through the UNOFFICIAL InnerTube endpoint (what pytchat / chat-downloader use): no OAuth, no quota, 1-3 s latency.

Flow: live video id (setting, or the channel's /live page) -> https://www.youtube.com/live_chat?v=ID gives the api key, client version and
the first continuation -> POST youtubei/v1/live_chat/get_live_chat with the continuation, again and again, each answer carrying the next
continuation and the delay YouTube wants (timeoutMs). The parsing functions are pure (tests feed hand-made payloads); the Reader class
holds the little state and does the HTTP. It can break whenever YouTube changes its pages: connectors/youtube.py falls back to the
official API (setting youtube_read_mode) and never lets a malformed payload end the loop.
"""
import json
import re
import time
from collections import OrderedDict
from urllib.parse import quote

import requests

import xplat
from models import ChatMessage

WATCH = "https://www.youtube.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
COOKIES = {"CONSENT": "YES+1", "SOCS": "CAI"}              # skips the EU consent interstitial
MIN_WAIT, MAX_WAIT = 0.5, 5.0
BADGE_ICONS = {"MODERATOR": "moderator", "OWNER": "owner", "VERIFIED": "verified"}
CONT_KEYS = ("invalidationContinuationData", "timedContinuationData", "reloadContinuationData")


class Expired(Exception):
    """The continuation is no longer valid (or the chat ended): fetch the live_chat page again."""


class NotLive(Exception):
    """The video has no live chat (not live, ended, chat disabled)."""


# pure parsing ------------------------------------------------------------------------------------------
def _txt(node):
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return str(node["simpleText"])
    return "".join(str(r.get("text", "")) for r in node.get("runs", []) if isinstance(r, dict))


def _runs(node):
    """message runs -> (text, emotes). Unicode emoji stay as characters, custom emoji become their :shortcut: and are listed in emotes."""
    out, emotes = [], []
    for r in (node or {}).get("runs", []) if isinstance(node, dict) else []:
        if not isinstance(r, dict):
            continue
        if "text" in r:
            out.append(str(r["text"]))
        elif isinstance(r.get("emoji"), dict):
            e = r["emoji"]
            sc = (e.get("shortcuts") or [""])[0]
            if e.get("isCustomEmoji") or not e.get("emojiId") or len(str(e.get("emojiId"))) > 8:
                label = sc or str(e.get("emojiId", ""))
                out.append(label)
                emotes.append({"id": str(e.get("emojiId", ""))[:80], "text": label})
            else:
                out.append(str(e["emojiId"]))
    return "".join(out), emotes


def _ts(usec):
    now = time.time()
    try:
        t = int(usec) / 1e6
    except (TypeError, ValueError):
        return now
    return min(t, now) if t > now - 86400 else now


def _avatar(r):
    th = ((r.get("authorPhoto") or {}).get("thumbnails") or [])
    return str(th[-1].get("url", ""))[:300] if th and isinstance(th[-1], dict) else ""


def _badges(r):
    out = []
    for b in r.get("authorBadges") or []:
        br = (b.get("liveChatAuthorBadgeRenderer") if isinstance(b, dict) else None) or {}
        icon = ((br.get("icon") or {}).get("iconType") or "").upper()
        if icon in BADGE_ICONS:
            out.append(BADGE_ICONS[icon])
        elif br.get("customThumbnail") or str(br.get("tooltip", "")).lower().startswith("member"):
            out.append("subscriber")
    return out


def parse_amount(text):
    """'$5.00' / '€2,50' / 'CA$1,000.00' / '¥500' -> (5, '$')... whole units, at least 1. Junk -> (1, '')."""
    t = str(text or "")
    m = re.search(r"\d[\d.,\s]*", t)
    if not m:
        return 1, t.strip()[:5]
    num = m.group(0).strip().replace(" ", "")
    if "," in num and "." not in num and re.search(r",\d{1,2}$", num):
        num = num.replace(",", ".")
    else:
        num = num.replace(",", "")
    try:
        v = round(float(num))
    except ValueError:
        v = 1
    return max(1, min(v, 10**7)), (t[:m.start()] + t[m.end():]).strip()[:5]


def _text_message(r, video, my_channel):
    uid = str(r.get("authorExternalChannelId") or "")
    name = _txt(r.get("authorName"))
    if not (r.get("id") and uid):
        return None
    text, emotes = _runs(r.get("message"))
    badges = _badges(r)
    return ChatMessage(id=f"youtube:{video}:{r['id']}", platform="youtube", channel=video, user_id=uid, user=name.lower(), display=name,
                       text=text, ts=_ts(r.get("timestampUsec")), badges=badges, emotes=emotes,
                       is_self="owner" in badges or (bool(my_channel) and uid == my_channel))


def _paid(r, video, kind):
    uid, name, nid = str(r.get("authorExternalChannelId") or ""), _txt(r.get("authorName")), str(r.get("id") or "")
    if not (uid and nid):
        return None
    shown = _txt(r.get("purchaseAmountText"))
    amt, cur = parse_amount(shown)
    what = "Super Chat" if kind == "chat" else "Super Sticker"
    return xplat._event("youtube", video, "cheer", uid, name, name, f"{name} sent a {what} {shown}".strip(), _ts(r.get("timestampUsec")), amount=amt,
                        native=nid, currency=cur, message=xplat._s(_runs(r.get("message"))[0], 200), avatar=_avatar(r))


def _member(r, video):
    uid, name, nid = str(r.get("authorExternalChannelId") or ""), _txt(r.get("authorName")), str(r.get("id") or "")
    if not (uid and nid):
        return None
    head = _txt(r.get("headerPrimaryText"))
    mo = re.search(r"(\d+)\s*(year|month)", head, re.I)
    ts = _ts(r.get("timestampUsec"))
    if mo:
        n = int(mo.group(1)) * (12 if mo.group(2).lower() == "year" else 1)
        return xplat._event("youtube", video, "resub", uid, name, name, f"{name} member for {n} months", ts, amount=n, native=nid, months=n, tier="1",
                            message=xplat._s(_runs(r.get("message"))[0], 200), avatar=_avatar(r))
    return xplat._event("youtube", video, "sub", uid, name, name, f"{name} became a member", ts, amount=1, native=nid, months=1, tier="1", avatar=_avatar(r))


def _gift(r, video):
    h = ((r.get("header") or {}).get("liveChatSponsorshipsHeaderRenderer")) or {}
    uid, name, nid = str(r.get("authorExternalChannelId") or ""), _txt(h.get("authorName")), str(r.get("id") or "")
    if not (uid and nid):
        return None
    m = re.search(r"\d+", _txt(h.get("primaryText")))
    n = max(1, int(m.group(0))) if m else 1
    return xplat._event("youtube", video, "gift", uid, name, name, f"{name} gifted {n} membership{'s' if n != 1 else ''}", _ts(r.get("timestampUsec")),
                        amount=n, native=nid, avatar=_avatar(r))


def parse_item(item, video, my_channel=""):
    """One addChatItemAction item -> ChatMessage | None (unknown renderers are ignored)."""
    if not isinstance(item, dict):
        return None
    if "liveChatTextMessageRenderer" in item:
        return _text_message(item["liveChatTextMessageRenderer"], video, my_channel)
    if "liveChatPaidMessageRenderer" in item:
        return _paid(item["liveChatPaidMessageRenderer"], video, "chat")
    if "liveChatPaidStickerRenderer" in item:
        return _paid(item["liveChatPaidStickerRenderer"], video, "sticker")
    if "liveChatMembershipItemRenderer" in item:
        return _member(item["liveChatMembershipItemRenderer"], video)
    if "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer" in item:
        return _gift(item["liveChatSponsorshipsGiftPurchaseAnnouncementRenderer"], video)
    return None


def parse_actions(actions, video, my_channel=""):
    """liveChatContinuation.actions -> (messages, cleared) where cleared = [("message", id) | ("user", channelId)]. Never raises."""
    msgs, cleared = [], []
    for a in actions if isinstance(actions, list) else []:
        try:
            if not isinstance(a, dict):
                continue
            if "addChatItemAction" in a:
                m = parse_item((a["addChatItemAction"] or {}).get("item"), video, my_channel)
                if m:
                    msgs.append(m)
            elif "markChatItemAsDeletedAction" in a:
                cleared.append(("message", f"youtube:{video}:{a['markChatItemAsDeletedAction']['targetItemId']}"))
            elif "removeChatItemByAuthorAction" in a:
                cleared.append(("user", str(a["removeChatItemByAuthorAction"]["externalChannelId"])))
        except Exception:
            continue
    return msgs, cleared


def next_continuation(lcc):
    """liveChatContinuation(-like) -> (continuation, wait_seconds) | (None, 0). The wait is YouTube's timeoutMs clamped to 0.5-5 s."""
    for c in (lcc or {}).get("continuations", []) if isinstance(lcc, dict) else []:
        for k in CONT_KEYS:
            d = c.get(k) if isinstance(c, dict) else None
            if isinstance(d, dict) and d.get("continuation"):
                try:
                    ms = float(d.get("timeoutMs", 1500))
                except (TypeError, ValueError):
                    ms = 1500.0
                if ms != ms:
                    ms = 1500.0
                return str(d["continuation"]), max(MIN_WAIT, min(MAX_WAIT, ms / 1000.0))
    return None, 0


def _initial_data(html):
    m = re.search(r"ytInitialData[\"'\]]*\s*=\s*", html)
    if not m:
        return None
    try:
        return json.JSONDecoder().raw_decode(html[m.end():])[0]
    except ValueError:
        return None


def parse_page(html):
    """live_chat page HTML -> {key, version, continuation, wait, actions}. Raises NotLive when there is no live chat on it."""
    html = html if isinstance(html, str) else ""
    data = _initial_data(html)
    lcr = ((data or {}).get("contents") or {}).get("liveChatRenderer") if isinstance(data, dict) else None
    if not isinstance(lcr, dict):
        raise NotLive("no live chat on the page")
    cont, wait = next_continuation(lcr)
    key = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION"\s*:\s*"([^"]+)"', html) or re.search(r'"clientVersion"\s*:\s*"([^"]+)"', html)
    if not (cont and key):
        raise NotLive("live chat page has no continuation (stream ended or chat off)")
    return {"key": key.group(1), "version": ver.group(1) if ver else "2.20240101.00.00", "continuation": cont, "wait": wait,
            "actions": lcr.get("actions") or []}


def watch_target(channel):
    """Setting youtube_channel (@handle, UC... id, or any youtube URL) -> (video_id, live_page_url). One of them is None."""
    c = str(channel or "").strip()
    if not c:
        return None, None
    m = re.search(r"(?:[?&]v=|youtu\.be/|/live/)([\w-]{11})(?![\w-])", c)
    if m:
        return m.group(1), None
    if re.fullmatch(r"UC[\w-]{22}", c):
        return None, f"{WATCH}/channel/{c}/live"
    m = re.search(r"youtube\.com/(@[\w.\-%]+|channel/UC[\w-]{22}|c/[\w.\-%]+|user/[\w.\-%]+)", c)
    path = m.group(1) if m else (c if c.startswith("@") else "@" + c.lstrip("/@"))
    return None, f"{WATCH}/{quote(path, safe='@/%')}/live"


def live_video_from_page(html):
    """channel /live page -> the video id when it is live right now, else None."""
    html = html if isinstance(html, str) else ""
    if not re.search(r'"isLiveNow"\s*:\s*true|"isLive"\s*:\s*true', html):
        return None
    m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})"', html) or \
        re.search(r'"videoDetails"\s*:\s*\{"videoId"\s*:\s*"([\w-]{11})"', html)
    return m.group(1) if m else None


# network + state ---------------------------------------------------------------------------------------
class Reader:
    """One watched video. fetch() starts/restarts the chat session, poll() returns the next batch."""
    def __init__(self, video, my_channel=""):
        self.video, self.my_channel = video, my_channel
        self.key = self.version = self.cont = None
        self.wait = 1.5
        self.seen = OrderedDict()
        self.attached = False

    @staticmethod
    def resolve(channel, video_id=""):
        """-> live video id | None. A configured video id is used as given (fetch() finds out whether it has chat)."""
        if str(video_id or "").strip():
            return watch_target(video_id)[0] or str(video_id).strip()
        vid, url = watch_target(channel)
        if vid or not url:
            return vid
        r = requests.get(url, headers=UA, cookies=COOKIES, timeout=10)
        r.raise_for_status()
        return live_video_from_page(r.text)

    def _remember(self, mid):
        if mid in self.seen:
            return False
        self.seen[mid] = 1
        if len(self.seen) > 2000:
            self.seen.popitem(last=False)
        return True

    def _fresh(self, msgs, first):
        """Dedupe by id. On the very first attach the page shows the recent backlog: remember it, only emit what is under 30 s old."""
        out = []
        for m in msgs:
            if self._remember(m.id) and (not first or time.time() - m.ts < 30):
                out.append(m)
        return out

    def fetch(self):
        r = requests.get(f"{WATCH}/live_chat", params={"is_popout": "1", "v": self.video}, headers=UA, cookies=COOKIES, timeout=10)
        r.raise_for_status()
        p = parse_page(r.text)
        self.key, self.version, self.cont, self.wait = p["key"], p["version"], p["continuation"], p["wait"]
        first, self.attached = not self.attached, True
        msgs, cleared = parse_actions(p["actions"], self.video, self.my_channel)
        return self._fresh(msgs, first), []

    def poll(self):
        """-> (messages, cleared). Raises Expired when the continuation is dead, requests/ValueError errors for the caller's backoff."""
        body = {"context": {"client": {"clientName": "WEB", "clientVersion": self.version, "hl": "en", "gl": "US"}}, "continuation": self.cont}
        r = requests.post(f"{WATCH}/youtubei/v1/live_chat/get_live_chat", params={"key": self.key, "prettyPrint": "false"}, json=body,
                          headers=UA, cookies=COOKIES, timeout=10)
        if r.status_code in (400, 404):
            raise Expired(f"continuation rejected ({r.status_code})")
        r.raise_for_status()
        j = r.json()
        lcc = ((j or {}).get("continuationContents") or {}).get("liveChatContinuation") if isinstance(j, dict) else None
        if not isinstance(lcc, dict):
            raise Expired("no liveChatContinuation in the answer")
        cont, wait = next_continuation(lcc)
        if not cont:
            raise Expired("no continuation: chat ended")
        self.cont, self.wait = cont, wait
        msgs, cleared = parse_actions(lcc.get("actions"), self.video, self.my_channel)
        return self._fresh(msgs, False), cleared
