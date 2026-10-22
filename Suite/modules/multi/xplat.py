"""Cross-platform event normaliser: Kick (webhook + unofficial Pusher), YouTube live-chat extras, TikTok LIVE -> ChatMessage.
Pure functions, no network. Stream events use the existing event names (follow sub resub gift cheer) + amount + meta{platform,...}
so the activity feed, alert engine and stats need no per-platform code. See Docs/MULTISTREAM_PLAN.md."""
import re
import time
from datetime import datetime

from models import ChatMessage

_EMOTE = re.compile(r"\[emote:(\d+):([^\]]{1,40})\]")
KICK_BADGES = {"broadcaster": "owner", "moderator": "moderator", "vip": "vip", "og": "og", "subscriber": "subscriber", "founder": "founder", "verified": "verified", "sub_gifter": "gifter"}


def _ts(v):
    if isinstance(v, (int, float)):
        return float(v) if v < 1e11 else v / 1000.0
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return time.time()


def _s(v, n=200):
    return str(v if v is not None else "")[:n]


def _int(v, d=0):
    try:
        return max(0, min(10**9, int(float(v))))
    except (TypeError, ValueError, OverflowError):
        return d


def _plain(content):
    """Kick sends emotes as [emote:id:name]; the chat shows the name, the ids go to emotes[]"""
    emotes = [{"id": m.group(1), "text": m.group(2)} for m in _EMOTE.finditer(content or "")]
    return _EMOTE.sub(lambda m: m.group(2), content or ""), emotes


def _badges(lst):
    out = []
    for b in lst or []:
        t = _s(b.get("type") if isinstance(b, dict) else b, 30).lower()
        if t:
            out.append(KICK_BADGES.get(t, t))
    return out


def _event(platform, channel, kind, user_id, user, display, text, ts, amount=0, native="", **meta):
    uid = _s(user_id, 60) or _s(user, 60).lower()
    return ChatMessage(id=f"{platform}:{channel}:{native or kind + ':' + uid + ':' + str(int(ts * 1000))}", platform=platform, channel=channel, user_id=uid,
                       user=_s(user, 60).lower(), display=_s(display or user, 60), text=_s(text, 300), ts=ts, raw_type=kind, event=kind, amount=_int(amount),
                       meta={"platform": platform, "notice": True, **{k: v for k, v in meta.items() if v not in (None, "")}})


# Kick -------------------------------------------------------------------------------------------
def kick_webhook(etype, p, msg_id=""):
    """etype = Kick-Event-Type header, p = JSON body, msg_id = Kick-Event-Message-Id (ULID, the idempotency key). -> ChatMessage | None"""
    if not isinstance(p, dict):
        return None
    bc = p.get("broadcaster") or {}
    ch = _s(bc.get("channel_slug") or bc.get("username"), 60).lower() or "kick"
    ts = _ts(p.get("created_at"))
    nid = _s(msg_id or p.get("message_id"), 80)
    if etype == "chat.message.sent":
        s = p.get("sender") or {}
        ident = s.get("identity") or {}
        text, emotes = _plain(_s(p.get("content"), 600))
        rt = p.get("replies_to") or {}
        return ChatMessage(id=f"kick:{ch}:{_s(p.get('message_id'), 80) or nid}", platform="kick", channel=ch, user_id=_s(s.get("user_id"), 40),
                           user=_s(s.get("username"), 60).lower(), display=_s(s.get("username"), 60), text=text, ts=ts, badges=_badges(ident.get("badges")),
                           reply_to=f"kick:{ch}:{rt['message_id']}" if rt.get("message_id") else "", reply_to_user=_s((rt.get("sender") or {}).get("username"), 60).lower(),
                           color=_s(ident.get("username_color"), 9), emotes=emotes)
    if etype == "channel.followed":
        f = p.get("follower") or {}
        return _event("kick", ch, "follow", f.get("user_id"), f.get("username"), f.get("username"), f"{f.get('username') or 'someone'} followed", ts, native=f"follow:{nid}")
    if etype in ("channel.subscription.new", "channel.subscription.renewal"):
        s = p.get("subscriber") or {}
        months = max(1, _int(p.get("duration"), 1))
        kind = "sub" if etype.endswith(".new") else "resub"
        return _event("kick", ch, kind, s.get("user_id"), s.get("username"), s.get("username"),
                      f"{s.get('username') or 'someone'} {'subscribed' if kind == 'sub' else 'resubscribed'}", ts, amount=months, native=f"{kind}:{nid}", months=months, tier="1")
    if etype == "channel.subscription.gifts":
        g = p.get("gifter") or {}
        anon = bool(g.get("is_anonymous")) or not g.get("username")
        n = len(p.get("giftees") or []) or 1
        who = "Anonymous" if anon else g["username"]
        return _event("kick", ch, "gift", g.get("user_id") if not anon else "anonymous", who, who, f"{who} gifted {n} sub{'s' if n != 1 else ''}", ts, amount=n,
                      native=f"gift:{nid}", anonymous=anon or None)
    if etype == "kicks.gifted":
        s, g = p.get("sender") or {}, p.get("gift") or {}
        n = _int(g.get("amount"))
        return _event("kick", ch, "cheer", s.get("user_id"), s.get("username"), s.get("username"), f"{s.get('username') or 'someone'} sent {n} KICKs ({_s(g.get('name'), 40)})",
                      ts, amount=n, native=f"kicks:{nid}", gift_name=_s(g.get("name"), 40), message=_s(g.get("message"), 200), currency="KICKs")
    if etype == "channel.reward.redemption.updated":
        r, u = p.get("reward") or {}, p.get("redeemer") or {}
        if p.get("status") not in (None, "", "pending", "accepted"):
            return None
        return _event("kick", ch, "redeem", u.get("user_id"), u.get("username"), u.get("username"), f"{u.get('username') or 'someone'} redeemed {_s(r.get('title'), 80)}", ts,
                      amount=_int(r.get("cost")), native=f"redeem:{_s(p.get('id'), 60) or nid}", message=_s(p.get("user_input") or r.get("title"), 200))
    return None


def kick_pusher(event, data, channel="kick"):
    """Unofficial Pusher frame: event name (...ChatMessageEvent) + decoded data dict -> ChatMessage | None (chat only)"""
    if not isinstance(data, dict) or not str(event).endswith("ChatMessageEvent"):
        return None
    s = data.get("sender") or {}
    ident = s.get("identity") or {}
    text, emotes = _plain(_s(data.get("content"), 600))
    meta = data.get("metadata") or {}
    orig = meta.get("original_message") or {}
    osend = meta.get("original_sender") or {}
    return ChatMessage(id=f"kick:{channel}:{_s(data.get('id'), 80)}", platform="kick", channel=channel, user_id=_s(s.get("id"), 40), user=_s(s.get("slug") or s.get("username"), 60).lower(),
                       display=_s(s.get("username"), 60), text=text, ts=_ts(data.get("created_at")), badges=_badges(ident.get("badges")), color=_s(ident.get("color"), 9),
                       reply_to=f"kick:{channel}:{orig['id']}" if orig.get("id") else "", reply_to_user=_s(osend.get("username"), 60).lower(), emotes=emotes)


# YouTube ----------------------------------------------------------------------------------------
def youtube_event(it, chat_id):
    """liveChatMessages item that is NOT a plain text message -> event ChatMessage | None"""
    sn, au = it.get("snippet", {}), it.get("authorDetails", {})
    t, uid, name = sn.get("type"), au.get("channelId", ""), au.get("displayName", "")
    ts, nid = _ts(sn.get("publishedAt")), _s(it.get("id"), 80)
    av = _s(au.get("profileImageUrl"), 300)
    if t in ("superChatEvent", "superStickerEvent"):
        d = sn.get("superChatDetails") or sn.get("superStickerDetails") or {}
        amt = round(_int(d.get("amountMicros")) / 1e6) or 1
        what = "Super Chat" if t == "superChatEvent" else "Super Sticker"
        return _event("youtube", chat_id, "cheer", uid, name, name, f"{name} sent a {what} {_s(d.get('amountDisplayString'), 30)}", ts, amount=amt, native=nid,
                      currency=_s(d.get("currency"), 5), message=_s(d.get("userComment"), 200), avatar=av)
    if t == "newSponsorEvent":
        return _event("youtube", chat_id, "sub", uid, name, name, f"{name} became a member", ts, amount=1, native=nid, months=1, tier="1", avatar=av)
    if t == "memberMilestoneChatEvent":
        d = sn.get("memberMilestoneChatDetails") or {}
        mo = max(1, _int(d.get("memberMonth"), 1))
        return _event("youtube", chat_id, "resub", uid, name, name, f"{name} member for {mo} months", ts, amount=mo, native=nid, months=mo, tier="1",
                      message=_s(d.get("userComment"), 200), avatar=av)
    if t == "membershipGiftingEvent":
        n = max(1, _int((sn.get("membershipGiftingDetails") or {}).get("giftMembershipsCount"), 1))
        return _event("youtube", chat_id, "gift", uid, name, name, f"{name} gifted {n} membership{'s' if n != 1 else ''}", ts, amount=n, native=nid, avatar=av)
    return None


# TikTok -----------------------------------------------------------------------------------------
def tiktok_event(kind, ev, unique_id):
    """TikTokLive event-like object (duck-typed so tests use a fake) -> event ChatMessage | None. kind: follow | gift | subscribe"""
    u = getattr(ev, "user", None)
    uid = _s(getattr(u, "user_id", "") or getattr(u, "unique_id", ""), 40)
    login = _s(getattr(u, "unique_id", ""), 60)
    nick = _s(getattr(u, "nickname", "") or login, 60)
    now = time.time()
    if not uid and not login:
        return None
    if kind == "follow":
        return _event("tiktok", unique_id, "follow", uid, login, nick, f"{nick} followed", now, native=f"follow:{uid}:{int(now // 3600)}")
    if kind == "subscribe":
        return _event("tiktok", unique_id, "sub", uid, login, nick, f"{nick} subscribed", now, amount=1, native=f"sub:{uid}:{int(now // 60)}", months=1, tier="1")
    if kind == "gift":
        g = getattr(ev, "gift", None)
        if bool(getattr(g, "streakable", False)) and getattr(ev, "streaking", False):      # mid-streak frame: only the final one counts
            return None
        diamonds = _int(getattr(g, "diamond_count", 0))
        count = max(1, _int(getattr(ev, "repeat_count", 1), 1))
        name = _s(getattr(g, "name", "gift"), 40)
        gid = _s(getattr(ev, "group_id", "") or getattr(ev, "msg_id", ""), 60) or uid + str(int(now * 1000))
        return _event("tiktok", unique_id, "cheer", uid, login, nick, f"{nick} sent {count}x {name}", now, amount=diamonds * count,
                      native=f"gift:{gid}", gift_name=name, count=count, currency="coins")
    return None
