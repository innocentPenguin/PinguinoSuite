"""Stream title / description / tags for the platforms Multi owns (YouTube, Kick). Edits and SCHEDULING only:
nothing here ever calls liveBroadcasts.transition or starts a stream. TikTok is manual (the app shows a copy block)."""
from datetime import datetime, timezone

import requests

import secrets_store

YT = "https://www.googleapis.com/youtube/v3"
KICK = "https://api.kick.com/public/v1"
PRIVACY = ("public", "unlisted", "private")


def _clean_tags(tags):
    out, seen = [], set()
    for t in (tags if isinstance(tags, list) else []):
        t = str(t).strip().lstrip("#")[:60]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:30]


def _err(r):
    try:
        e = r.json().get("error")
        return (e.get("message") if isinstance(e, dict) else str(e))[:200]
    except Exception:
        return f"HTTP {r.status_code}"


def _yh():
    return {"Authorization": f"Bearer {secrets_store.get('youtube_token')}"}


def _yt_current():
    """-> (broadcast_id, state) of the active broadcast, else the next upcoming one; (None, '') when there is none"""
    for state in ("active", "upcoming"):
        r = requests.get(f"{YT}/liveBroadcasts", params={"part": "id,snippet", "broadcastStatus": state, "mine": "true", "maxResults": 5}, headers=_yh(), timeout=10)
        if r.status_code in (401, 403):
            raise PermissionError(_err(r))
        r.raise_for_status()
        items = r.json().get("items") or []
        if items:
            return items[0]["id"], state
    return None, ""


def _yt_video(vid):
    r = requests.get(f"{YT}/videos", params={"part": "snippet", "id": vid}, headers=_yh(), timeout=10)
    r.raise_for_status()
    it = (r.json().get("items") or [None])[0]
    return (it or {}).get("snippet") or {}


def youtube_get():
    if not secrets_store.get("youtube_token"):
        return {"connected": False, "canSchedule": False, "title": "", "description": "", "tags": [], "error": "no YouTube token (Multi settings)"}
    try:
        vid, state = _yt_current()
        base = {"connected": True, "canSchedule": True, "title": "", "description": "", "tags": []}
        if not vid:
            return {**base, "error": "no live or upcoming broadcast"}
        sn = _yt_video(vid)
        return {**base, "broadcastId": vid, "state": state, "title": sn.get("title", ""), "description": sn.get("description", ""), "tags": sn.get("tags") or []}
    except Exception as e:
        return {"connected": False, "canSchedule": False, "title": "", "description": "", "tags": [], "error": str(e)[:200]}


def _put_snippet(vid, sn, **over):
    """videos.update replaces the whole snippet, so start from the current one"""
    new = {"title": sn.get("title", ""), "description": sn.get("description", ""), "categoryId": sn.get("categoryId", "20"), "tags": sn.get("tags") or []}
    new.update(over)
    return requests.put(f"{YT}/videos", params={"part": "snippet"}, json={"id": vid, "snippet": new}, headers=_yh(), timeout=10)


def youtube_update(title=None, description=None, tags=None):
    if not secrets_store.get("youtube_token"):
        return {"ok": False, "error": "no YouTube token"}
    try:
        vid, _ = _yt_current()
        if not vid:
            return {"ok": False, "error": "no live or upcoming YouTube broadcast"}
        over = {}
        if title is not None:
            over["title"] = str(title).strip()[:100]
            if not over["title"]:
                return {"ok": False, "error": "title is empty"}
        if description is not None:
            over["description"] = str(description)[:5000]
        if tags is not None:
            over["tags"] = _clean_tags(tags)
        r = _put_snippet(vid, _yt_video(vid), **over)
        return {"ok": True, "broadcastId": vid} if r.ok else {"ok": False, "error": _err(r)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def youtube_schedule(title, description="", tags=None, starts_at="", privacy="private"):
    """liveBroadcasts.insert (autoStart/autoStop OFF) + bind to the channel's existing reusable stream key. Never transitions the broadcast."""
    if not secrets_store.get("youtube_token"):
        return {"ok": False, "error": "no YouTube token"}
    title = str(title or "").strip()[:100]
    if not title:
        return {"ok": False, "error": "title is required"}
    privacy = privacy if privacy in PRIVACY else "private"
    try:
        when = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.astimezone()
        when = when.astimezone(timezone.utc)
    except ValueError:
        return {"ok": False, "error": "startsAt must be ISO-8601"}
    try:
        body = {"snippet": {"title": title, "description": str(description or "")[:5000], "scheduledStartTime": when.strftime("%Y-%m-%dT%H:%M:%SZ")},
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
                "contentDetails": {"enableAutoStart": False, "enableAutoStop": False}}
        r = requests.post(f"{YT}/liveBroadcasts", params={"part": "snippet,status,contentDetails"}, json=body, headers=_yh(), timeout=15)
        if not r.ok:
            return {"ok": False, "error": _err(r)}
        bid = r.json()["id"]
        out = {"ok": True, "broadcastId": bid, "url": f"https://www.youtube.com/watch?v={bid}", "bound": False}
        s = requests.get(f"{YT}/liveStreams", params={"part": "id", "mine": "true", "maxResults": 1}, headers=_yh(), timeout=10)
        sid = ((s.json().get("items") or [{}])[0].get("id")) if s.ok else None
        if sid:
            b = requests.post(f"{YT}/liveBroadcasts/bind", params={"id": bid, "part": "id,contentDetails", "streamId": sid}, headers=_yh(), timeout=10)
            out["bound"] = b.ok
            if not b.ok:
                out["warning"] = "scheduled but not bound to a stream key: " + _err(b)
        else:
            out["warning"] = "scheduled; no reusable stream key found to bind"
        t = _clean_tags(tags)
        if t:
            try:
                if not _put_snippet(bid, _yt_video(bid), tags=t).ok:
                    out["warning"] = (out.get("warning", "") + " tags not set").strip()
            except Exception:
                out["warning"] = (out.get("warning", "") + " tags not set").strip()
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# Kick: PATCH /public/v1/channels needs channel:write on Ivan's Kick app login (stored as secret 'kick_token'; no OAuth flow in Multi yet) ----------
def _kh():
    return {"Authorization": f"Bearer {secrets_store.get('kick_token')}"}


def kick_get():
    if not secrets_store.get("kick_token"):
        return {"connected": False, "title": "", "error": "Kick login not set up (needs Ivan's Kick app, scope channel:write)"}
    try:
        r = requests.get(f"{KICK}/channels", headers=_kh(), timeout=10)
        if not r.ok:
            return {"connected": False, "title": "", "error": _err(r)}
        d = ((r.json().get("data") or [{}])[0])
        return {"connected": True, "title": d.get("stream_title", ""), "category": (d.get("category") or {}).get("name", "")}
    except Exception as e:
        return {"connected": False, "title": "", "error": str(e)[:200]}


def kick_update(title=None):
    if not secrets_store.get("kick_token"):
        return {"ok": False, "error": "Kick login not set up"}
    if title is None:
        return {"ok": False, "error": "Kick only supports the title (no description or tags)"}
    try:
        r = requests.patch(f"{KICK}/channels", json={"stream_title": str(title)[:140]}, headers=_kh(), timeout=10)
        return {"ok": True} if r.ok else {"ok": False, "error": _err(r)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
