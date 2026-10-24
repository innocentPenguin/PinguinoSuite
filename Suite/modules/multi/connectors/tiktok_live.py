"""TikTok LIVE adapter around the optional, UNOFFICIAL `TikTokLive` package (7.x). Import-guarded: Multi runs fine without it and reports "not installed".
Pure mapping lives here (unit-tested with fake events); connectors/tiktok.py runs the client with it. Docs: Docs/PinguinoMulti/PLATFORMS.md (TikTok section).

Config: tiktok_enabled, tiktok_user (the @handle, with or without @). Optional: tiktok_sign_url (own sign server instead of the default Euler Stream).
Mapping -> xplat events: comment -> chat line | gift -> cheer (amount = coins = diamonds x streak count, final streak frame only) | follow -> follow |
subscribe (SubNotifyEvent / SuperFanEvent) -> sub | share -> share row (no alert) | like -> counted in state["likes"], no row (too noisy).
"""
import re
import time

import xplat
from models import ChatMessage

EVENT_CLASSES = {"comment": ("CommentEvent",), "gift": ("GiftEvent",), "follow": ("FollowEvent",), "share": ("ShareEvent",),
                 "like": ("LikeEvent",), "subscribe": ("SubNotifyEvent", "SuperFanEvent", "SubscribeEvent")}
_HANDLE = re.compile(r"^[A-Za-z0-9_.]{2,24}$")


def available():
    """-> (ok, reason). Never raises."""
    try:
        import TikTokLive  # noqa: F401
        return True, ""
    except ImportError:
        return False, "TikTokLive is not installed"
    except Exception as e:                                   # a broken install must not take Multi down
        return False, f"TikTokLive failed to import: {str(e)[:80]}"


def handle(settings):
    """-> clean handle without '@' or ''. Accepts tiktok_user (current key) or tiktok_handle."""
    h = str(settings.get("tiktok_user") or settings.get("tiktok_handle") or "").strip().lstrip("@")
    return h if _HANDLE.match(h) else ""


def _user(ev):
    """-> (stable id, @handle, nickname). TikTokLive 7: user.id is the stable number, user.unique_id is a property over display_id (6.x had user_id)."""
    u = getattr(ev, "user", None)
    handle_ = str(getattr(u, "unique_id", "") or getattr(u, "display_id", "") or "")
    return str(getattr(u, "id", "") or getattr(u, "user_id", "") or handle_), handle_, str(getattr(u, "nickname", "") or handle_)


def map_event(kind, ev, handle_):
    """TikTokLive event-like object -> ChatMessage | None. kind: comment | gift | follow | share | like | subscribe. Pure."""
    uid, login, nick = _user(ev)
    if kind == "comment":
        text = str(getattr(ev, "content", "") or getattr(ev, "comment", "") or "")
        if not (uid or login) or not text.strip():
            return None
        badges = ["subscriber"] if getattr(ev, "user_is_super_fan", False) is True else []
        return ChatMessage(id=f"tiktok:{handle_}:{xplat._msg_id(ev) or uid + str(int(time.time() * 1000))}", platform="tiktok", channel=handle_,
                           user_id=uid, user=login.lower(), display=nick, text=text[:500], ts=time.time(), badges=badges, raw_type="text", is_self=bool(login) and login.lower() == str(handle_).lower())
    if kind == "share":
        if not (uid or login):
            return None
        now = time.time()
        return xplat._event("tiktok", handle_, "share", uid, login, nick, f"{nick} shared the stream", now, native=f"share:{uid}:{int(now // 60)}")
    if kind in ("gift", "follow", "subscribe"):
        return xplat.tiktok_event(kind, ev, handle_)
    return None


def attach(client, events_module, handle_, put, state):
    """Register listeners on a TikTokLiveClient. Missing event classes (version drift) are skipped. -> names registered."""
    done = []

    def mk(kind):
        async def on_x(ev):
            try:
                if kind == "like":
                    state["likes"] = state.get("likes", 0) + max(1, int(getattr(ev, "count", 1) or 1))
                    return
                m = map_event(kind, ev, handle_)
            except Exception:
                return
            if m:
                state["last_message"] = time.time()
                put(m)
        return on_x
    for kind, names in EVENT_CLASSES.items():
        for n in names:
            cls = getattr(events_module, n, None)
            if cls is not None:
                client.add_listener(cls, mk(kind))
                done.append(n)
    return done
