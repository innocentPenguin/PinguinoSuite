"""Paths + settings for PinguinoMulti (unified chat). Port 8766."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
DATA = (Path(os.environ["PINGUINO_DATA_DIR"]) / "multi") if os.environ.get("PINGUINO_DATA_DIR") else ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("MULTI_PORT", "8766"))
DB_FILE = Path(os.environ.get("MULTI_DB", DATA / "multi.db"))
SETTINGS_FILE = DATA / "settings.json"
RULES_FILE = DATA / "rules.json"
PROFILES_DIR = ROOT.parents[2] / "Data" / "profiles"  # shared viewer profiles (D:\PinguinoSuite\Data)

DEFAULTS = {
    "channel": "innocentpenguin_",
    "twitch_client_id": "",
    "discord_channels": [],          # channel ids Multi reads/sends in (bot token is in Credential Manager)
    "priority_mode": "local",        # local | ai | auto  (AI arrives in M3; local always works)
    "ai_provider": "anthropic",      # anthropic | openai | ollama (key in Credential Manager as ai_key)
    "ai_model": "claude-haiku-5-5",
    "ai_daily_cap_usd": 0.5,
    "ai_timeout_s": 2.0,
    "ai_margin": 8,                  # only ask AI when the local score is within this of a tier threshold
    "voice_enabled": False,          # opt-in: suggest cards answered out loud (never auto-closes)
    "claim_ttl_s": 20,               # how long a streamer-first claim holds the bots back
    "answered_fade_s": 15,
    "missed_after_s": 300,
    "max_cards": 12,
    "retention_days": 30,
    "bot_accounts": ["pinguinob0t", "nightbot", "streamelements", "moobot", "streamlabs", "fossabot"],
    "my_names": ["innocentpenguin", "penguin"],
}


def settings():
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
    except Exception:
        pass
    return s


def save_settings(patch):
    s = settings()
    s.update({k: v for k, v in patch.items() if k in DEFAULTS})
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), "utf-8")
    return s
