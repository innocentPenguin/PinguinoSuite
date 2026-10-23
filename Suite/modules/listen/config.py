"""Paths + settings for the PinguinoBot ears (listen-only speech-to-text)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ["LISTEN_DATA_DIR"]) if os.environ.get("LISTEN_DATA_DIR") else ROOT / "data"
AUDIO = DATA / "audio"
LIVE_AUDIO = AUDIO / "live"
SOURCES = DATA / "sources"
for _p in (DATA, AUDIO, LIVE_AUDIO, SOURCES):
    _p.mkdir(parents=True, exist_ok=True)

MODEL = os.environ.get("EARS_MODEL", "large-v3-turbo")
LANGUAGE = os.environ.get("EARS_LANG", "en")  # "auto" to detect
PORT = int(os.environ.get("EARS_PORT", "8765"))
COMMON_WORDS = ROOT.parents[2] / "Data" / "common-words.txt"  # shared with the chat bot pipeline (D:\PinguinoSuite\Data)
SETTINGS_FILE = DATA / "settings.json"

DEFAULTS = {
    "channel": "innocentpenguin_",
    "autolearn": False,
    "autolearn_vods": 3,       # newest N VODs
    "autolearn_clips": 15,     # newest N clips
    "autolearn_clip_days": 30,
    "yellow": 0.75,            # word probability below this -> yellow (unsure)
    "red": 0.45,               # word probability below this -> red (very unsure)
    "device": None,            # legacy sounddevice index; indexes shift when devices come and go, so the NAME below wins
    "device_name": None,       # the chosen mic by name (+ host API), resolved to the current index at every start
    "device_hostapi": None,
}


def settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text("utf8")))
    except Exception:
        pass
    return s


def save_settings(patch: dict) -> dict:
    s = settings()
    s.update({k: v for k, v in patch.items() if k in DEFAULTS})
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), "utf8")
    return s
