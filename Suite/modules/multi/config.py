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
    "kick_enabled": False,            # Kick: UNOFFICIAL read-only chat feed (public Pusher socket); official events come by webhook (POST /hook/kick)
    "kick_channel": "",               # channel slug
    "link_url": "",                   # blank = http://127.0.0.1:7777 (Link): follow the OBS scene for alert profiles (scene_follow.py)
    "feed_hype_alerts": False,        # hype-train alerts from the Host activity feed (OFF: the Host fires them directly on /api/alerts/fire)
    "intro_enabled": True,            # play viewers' approved intros (Host) for first-time / returning chatters
    "kick_client_id": "",             # Kick developer app client id (secret goes to Credential Manager as kick_client_secret)
    "kick_redirect_uri": "http://127.0.0.1:8766/auth/kick/callback",
    "kick_scopes": "user:read channel:read channel:write chat:write events:subscribe",
    "youtube_client_id": "",          # Google OAuth Desktop-app client id (secret: Credential Manager youtube_client_secret)
    "youtube_redirect_uri": "http://127.0.0.1:8766/auth/youtube/callback",
    "youtube_min_poll_s": 10,         # liveChat poll floor (api mode only): 5 quota units per poll of 10,000/day
    "youtube_read_mode": "innertube", # "innertube" = unofficial live-chat endpoint, 1-3 s, no OAuth; "api" = official Data API (>= 10 s, quota)
    "youtube_channel": "",            # your channel for innertube mode: @handle, UC... id or a youtube URL ("" = use the signed-in account)
    "youtube_video_id": "",           # optional: pin one live video id / watch URL instead of looking up the channel's live stream
    "youtube_innertube_fallback_min": 5,   # innertube failing this many minutes AND a YouTube token present -> read through the official API meanwhile
    "tiktok_sign_url": "",            # optional own sign server for TikTokLive ("" = library default)
    "kick_chatroom_id": "",           # numeric chatroom id (kick.com/api/v2/channels/<slug> -> chatroom.id; pasted once)
    "ding_platforms": [],            # new-chatter ding: platforms it is ON for (twitch, youtube); empty = off
    "ding_first_ever": True,         # Twitch "first message ever" gets its own (optional) sound
    "ding_sound": r"D:\PinguinoSuite\Data\sounds\new-chatter-bell.wav",   # = Streamer.bot "First TIme System (Bell)" sound
    "ding_first_sound": r"D:\PinguinoSuite\Data\sounds\chat-pop.mp3",   # brand-new chatter (first message ever)
    "ding_returning": True,         # a different ding for someone who chatted in an earlier stream
    "ding_returning_sound": r"D:\PinguinoSuite\Data\sounds\first-today-ding.mp3",   # = Streamer.bot "chat (first time today)" at 50 %
    "ding_returning_volume": 50,
    "ding_master_volume": 100,       # multiplies both ding volumes
    "ding_volume": 24,                # Streamer.bot used 0.24
    "ding_scope": "stream",           # stream = once per person per stream; ever = once per person, forever (Streamer.bot bell)
    "ding_cooldown_s": 1.5,
    "ding_session_gap_h": 6,          # = gap_h: silent this long = a new stream, and a chatter silent this long gets the "returning" flag
    "ding_rows": None,                # saved per-row overrides {first|new_stream|returning: {on,sound,volume,notify}}; None/missing fields derive from the old keys
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
    "my_names": ["innocentpenguin", "innocentpenguin_", "penguin"],
}


def settings():
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
    except Exception:
        pass
    return s


def platforms_for(st, key):
    """ding_platforms / pop_platforms with tiktok added automatically while tiktok_enabled (so its chatters ding like Twitch's)."""
    out = list(st.get(key) or [])
    if st.get("tiktok_enabled") and "tiktok" not in out:
        out.append("tiktok")
    return out


def save_settings(patch):
    s = settings()
    s.update({k: v for k, v in patch.items() if k in DEFAULTS})
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), "utf-8")
    return s


DING_ROWS = ("first", "new_stream", "returning")


HARP = ROOT.parents[2] / "Data" / "sounds" / "harp.wav"      # the old page "harp" tone: default sound of the first row


def ding_rows(s=None):
    """The three chatter-sound rows. A row (or field) that was never saved is derived from the old ding_* keys, so nothing resets."""
    s = s if s is not None else settings()
    rows = {"first": {"on": True, "sound": str(HARP) if HARP.is_file() else s["ding_sound"], "volume": 90, "notify": True},
            "new_stream": {"on": True, "sound": s["ding_sound"], "volume": s["ding_volume"], "notify": False},
            "returning": {"on": True, "sound": s.get("ding_returning_sound") or s["ding_sound"], "volume": s["ding_returning_volume"], "notify": False}}
    saved = s.get("ding_rows")
    if isinstance(saved, dict):
        for name, row in rows.items():
            sv = saved.get(name)
            if isinstance(sv, dict):
                row.update({k: v for k, v in sv.items() if k in row})
    return rows
