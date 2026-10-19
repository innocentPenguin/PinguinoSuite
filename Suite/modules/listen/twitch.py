"""Read-only Twitch lookups (public VODs + clips) using the same app credentials as the chat-log scripts."""
import os
import re
import time
from pathlib import Path

import requests

ENV_FILES = [Path(__file__).parent / ".env", Path(__file__).resolve().parents[3] / "PinguinoSite" / ".env"]
_tok = {"v": None, "exp": 0}


def _creds():
    env = dict(os.environ)
    for f in ENV_FILES:
        try:
            for line in f.read_text("utf8").splitlines():
                m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
                if m:
                    env.setdefault(m.group(1), m.group(2).strip("'\""))
        except Exception:
            pass
    if not env.get("TWITCH_CLIENT_ID") or not env.get("TWITCH_CLIENT_SECRET"):
        raise RuntimeError("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not found (environment, modules\\listen\\.env or D:\\PinguinoSuite\\PinguinoSite\\.env)")
    return env["TWITCH_CLIENT_ID"], env["TWITCH_CLIENT_SECRET"]


def _helix(path, params=None):
    cid, secret = _creds()
    if time.time() > _tok["exp"]:
        r = requests.post("https://id.twitch.tv/oauth2/token", data={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}, timeout=20)
        r.raise_for_status()
        _tok.update(v=r.json()["access_token"], exp=time.time() + r.json()["expires_in"] - 60)
    r = requests.get("https://api.twitch.tv/helix/" + path, params=params, headers={"Client-Id": cid, "Authorization": "Bearer " + _tok["v"]}, timeout=20)
    r.raise_for_status()
    return r.json()


def _secs(d: str) -> int:
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", d or "")
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0) if m else 0


def user_id(channel: str) -> str:
    d = _helix("users", {"login": channel.lower()})["data"]
    if not d:
        raise RuntimeError(f"no Twitch user '{channel}'")
    return d[0]["id"]


def vods(channel: str, n: int = 10) -> list:
    d = _helix("videos", {"user_id": user_id(channel), "type": "archive", "first": min(n, 100)})["data"]
    return [{"kind": "vod", "source_id": "vod:" + v["id"], "title": v["title"], "url": v["url"], "created": v["created_at"], "duration": _secs(v["duration"])} for v in d]


def clips(channel: str, days: int = 30, n: int = 20) -> list:
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))
    d = _helix("clips", {"broadcaster_id": user_id(channel), "first": min(n, 100), "started_at": start})["data"]
    return [{"kind": "clip", "source_id": "clip:" + c["id"], "title": c["title"], "url": c["url"], "created": c["created_at"], "duration": int(c["duration"])} for c in d]
