"""Read-only client of the Suite key vault: GET {PINGUINO_CORE_URL}/api/vault/<NAME> with this module's token.
Values stay in memory (short TTL cache); never written to disk, logs or status. Any failure just means 'not available'."""
import json
import os
import time
import urllib.error
import urllib.request

# local secret name -> vault name (declare these under "secrets" in the module manifest)
NAMES = {"twitch_tokens": "MULTI_TWITCH_TOKENS", "discord_token": "MULTI_DISCORD_TOKEN",
         "youtube_token": "MULTI_YOUTUBE_TOKEN", "ai_key": "MULTI_AI_KEY"}
TTL = 30
_cache = {}


def fetch(name):
    """Raw string value or None (404/403/409/503/unreachable all -> None)."""
    base = os.environ.get("PINGUINO_CORE_URL", "http://127.0.0.1:8760").rstrip("/")
    tok = os.environ.get("PINGUINO_API_TOKEN", "")
    if not tok:
        return None
    req = urllib.request.Request(f"{base}/api/vault/{name}", headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("value")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def get(local_name):
    name = NAMES.get(local_name)
    if not name:
        return None
    hit = _cache.get(name)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    v = fetch(name)
    _cache[name] = (time.time(), v)
    return v


def clear_cache():
    _cache.clear()
