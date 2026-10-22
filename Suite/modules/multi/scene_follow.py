"""Follow the OBS scene via Link: polls Link's read-only GET /api/obs and tells the alert engine which scene is on air.
Off until settings link_url is set (e.g. http://127.0.0.1:<Link port>); the Link token is the secret 'link_token'. Never writes to OBS."""
import asyncio

import requests

import config
import secrets_store


def _fetch(url, token):
    r = requests.get(url.rstrip("/") + "/api/obs", headers={"x-link-token": token} if token else {}, timeout=3)
    r.raise_for_status()
    return str((r.json() or {}).get("scene") or "")


async def run(engine, interval=3):
    last = None
    while True:
        s = config.settings()
        url = str(s.get("link_url") or "").strip()
        if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
            try:
                scene = await asyncio.to_thread(_fetch, url, secrets_store.get("link_token") or "")
                if scene and scene != last:
                    last = scene
                    engine.on_scene(scene)
            except Exception:
                pass
        await asyncio.sleep(interval)
