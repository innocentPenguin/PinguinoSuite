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
    "tiktok_enabled": False,         # UNOFFICIAL, read-only; needs optional TikTokLive package
    "tiktok_user": "",
    "ding_platforms": [],            # new-chatter ding: platforms it is ON for (twitch, youtube); empty = off
    "ding_first_ever": False,        # Twitch "first message ever" gets its own (optional) sound
    "ding_sound": r"D:\PinguinoSuite\Data\sounds\new-chatter-bell.wav",   # = Streamer.bot "First TIme System (Bell)" sound
    "ding_first_sound": "",
    "ding_returning": True,         # a different ding for someone who chatted in an earlier stream
    "ding_returning_sound": r"D:\PinguinoSuite\Data\sounds\first-today-ding.mp3",   # = Streamer.bot "chat (first time today)" at 50 %
    "ding_returning_volume": 50,
    "ding_master_volume": 100,       # multiplies both ding volumes
    "ding_volume": 24,                # Streamer.bot used 0.24
    "ding_scope": "stream",           # stream = once per person per stream; ever = once per person, forever (Streamer.bot bell)
    "ding_cooldown_s": 1.5,
    "ding_session_gap_h": 6,
    "pop_platforms": [],             # chat pop (a sound on every message): platforms it is ON for; empty = off
    "pop_sound": r"D:\PinguinoSuite\Data\sounds\chat-pop.mp3",   # = Streamer.bot "chat" / "chat (yt louder)"
    "pop_volume": {"twitch": 50, "youtube": 76, "discord": 50},   # Streamer.bot: 0.5 Twitch, 0.76 YouTube
    "pop_cooldown_s": 0.35,
    "pop_roles": [],                 # chat pop only for these roles (mod, vip, sub, viewer); empty = everyone
    "pop_own": False,                # also pop for my own messages
    "chat_style": None,              # chat look (fonts, backgrounds, highlights); None = defaults, see chatstyle.py
    "discord_channels": [],          # channel ids Multi reads/sends in (bot token is in Credential Manager)
    "priority_mode": "local",        # local | ai | auto  (AI arrives in M3; local always works)
    "ai_provider": "anthropic",      # anthropic | openai | ollama (key in Credential Manager as ai_key)
    "ai_model": "claude-haiku-5-5",
    "ai_daily_cap_usd": 0.5,
    "ai_timeout_s": 2.0,
    "ai_margin": 8,                  # only ask AI when the local score is within this of a tier threshold
    "host_feed_enabled": True,       # show Host follows / channel point redeems as event rows in chat
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
