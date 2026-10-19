"""Is the channel live? Public Twitch Helix /streams lookup with the app credentials you already use."""
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

ENV_FILES = [Path(__file__).resolve().parents[1] / ".env", Path(__file__).resolve().parents[2] / "PinguinoSite" / ".env"]
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
        raise RuntimeError("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not found")
    return env["TWITCH_CLIENT_ID"], env["TWITCH_CLIENT_SECRET"]


def stream_info(channel: str):
    """-> {title, game, viewers, started(epoch)} when live, else None."""
    cid, secret = _creds()
    if time.time() > _tok["exp"]:
        r = requests.post("https://id.twitch.tv/oauth2/token", data={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}, timeout=15)
        r.raise_for_status()
        _tok.update(v=r.json()["access_token"], exp=time.time() + r.json()["expires_in"] - 60)
    r = requests.get("https://api.twitch.tv/helix/streams", params={"user_login": channel}, headers={"Client-Id": cid, "Authorization": "Bearer " + _tok["v"]}, timeout=15)
    r.raise_for_status()
    d = r.json()["data"]
    if not d or d[0].get("type") != "live":
        return None
    s = d[0]
    return {"title": s["title"], "game": s.get("game_name", ""), "viewers": s["viewer_count"],
            "started": datetime.fromisoformat(s["started_at"].replace("Z", "+00:00")).timestamp()}
