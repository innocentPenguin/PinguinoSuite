"""Follow the OBS scene via Link: polls Link's read-only GET /api/obs and tells the alert engine which scene is on air.
Link (default http://127.0.0.1:7777, override with settings link_url) accepts the Suite's per-module token "module:link", derived read-only from Data/runtime/module_secret. Never writes to OBS."""
import asyncio
import os

from urllib.parse import urlparse

import requests

import alerts
import config
import console_log


def _local(url):
    """Only a loopback host may receive the module token. startswith("http://127.0.0.1") also accepted http://127.0.0.1.evil.com."""
    try:
        u = urlparse(url)
        return u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")
    except ValueError:
        return False


def _fetch(url, token):
    r = requests.get(url.rstrip("/") + "/api/obs", headers={"x-link-token": token} if token else {}, timeout=3)
    r.raise_for_status()
    j = r.json()
    return str(j.get("scene") or "")[:200] if isinstance(j, dict) else ""


async def run(engine, interval=3):
    last, fails = None, 0
    while True:
        s = config.settings()
        url = str(s.get("link_url") or "http://127.0.0.1:7777").strip()
        if _local(url):
            token = alerts.host_token(os.environ.get("PINGUINO_DATA_DIR"), "link")
            if not token:                            # no module_secret in this process's data dir (a throwaway / test run): never knock on Link without a token (a wall of 401s)
                console_log.warn("scene_follow", "no Link token (PINGUINO_DATA_DIR unset or module_secret unreadable): scene following is off", dedupe_s=3600)
                await asyncio.sleep(30)
                continue
            try:
                scene = await asyncio.to_thread(_fetch, url, token)
                fails = 0
                if scene and scene != last:
                    engine.on_scene(scene)
                    last = scene                     # only after on_scene worked: a failure is retried on the next poll
            except Exception as e:
                fails += 1
                if fails == 3:                       # Link not running is normal; a wrong token or a broken alert config deserves one line
                    console_log.warn("scene_follow", f"cannot follow the OBS scene: {type(e).__name__}: {str(e)[:100]}", dedupe_s=1800)
        else:
            console_log.warn("scene_follow", "link_url must be http://127.0.0.1 or http://localhost: scene following is off", dedupe_s=1800)
        await asyncio.sleep(min(interval * (1 + fails // 10), 30))       # back off to 30 s while Link stays down
