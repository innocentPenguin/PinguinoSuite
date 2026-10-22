"""Follow the OBS scene via Link: polls Link's read-only GET /api/obs and tells the alert engine which scene is on air.
Link (default http://127.0.0.1:7777, override with settings link_url) accepts the Suite's per-module token "module:link", derived read-only from Data/runtime/module_secret. Never writes to OBS."""
import asyncio
import os

import requests

import config
import alerts


def _fetch(url, token):
    r = requests.get(url.rstrip("/") + "/api/obs", headers={"x-link-token": token} if token else {}, timeout=3)
    r.raise_for_status()
    return str((r.json() or {}).get("scene") or "")


async def run(engine, interval=3):
    last = None
    while True:
        s = config.settings()
        url = str(s.get("link_url") or "http://127.0.0.1:7777").strip()
        if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
            try:
                scene = await asyncio.to_thread(_fetch, url, alerts.host_token(os.environ.get("PINGUINO_DATA_DIR"), "link"))
                if scene and scene != last:
                    last = scene
                    engine.on_scene(scene)
            except Exception:
                pass
        await asyncio.sleep(interval)
