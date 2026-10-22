"""Alert media library (sounds, images, gifs, videos) + one-time import of the Host's alerts_settings.json sounds.
Files live in <multi data>/alert_media and are served at /alert-media/<name>; alert configs only ever hold that URL."""
import json
import re
import shutil
from pathlib import Path

import config

DIR = config.DATA / "alert_media"
EXT = {".mp3", ".wav", ".ogg", ".m4a", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".webm", ".mp4"}
KIND = {".mp3": "sound", ".wav": "sound", ".ogg": "sound", ".m4a": "sound", ".webm": "video", ".mp4": "video"}
MAX_BYTES = 25 * 1024 * 1024
HOST_SOUND_TYPES = ("follow", "sub", "resub", "gift", "cheer", "raid")


def safe_name(name):
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(name or "")).name).strip("._")[:80]
    ext = Path(base).suffix.lower()
    return base if base and ext in EXT else ""


def save(name, data):
    n = safe_name(name)
    if not n:
        raise ValueError("unsupported file type (use mp3 wav ogg m4a png jpg gif webp webm mp4)")
    if len(data) > MAX_BYTES:
        raise ValueError("file too large (max 25 MB)")
    if not data:
        raise ValueError("empty file")
    DIR.mkdir(parents=True, exist_ok=True)
    p, stem, i = DIR / n, Path(n).stem, 1
    while p.exists():                                  # never overwrite a file an alert may be using
        p = DIR / f"{stem}_{i}{Path(n).suffix}"
        i += 1
    p.write_bytes(data)
    return p.name


def listing():
    if not DIR.exists():
        return []
    return [{"name": f.name, "url": "/alert-media/" + f.name, "kind": KIND.get(f.suffix.lower(), "image"), "bytes": f.stat().st_size}
            for f in sorted(DIR.iterdir(), key=lambda x: x.name.lower()) if f.is_file()]


def delete(name):
    p = DIR / safe_name(name)
    if p.is_file() and p.parent == DIR:
        p.unlink()
        return True
    return False


def host_runtime():
    r"""the Host's data folder: the Suite hands every module PINGUINO_DATA_DIR (= Data\runtime) and Multi lives in <that>\multi; standalone it is Data\runtime next to the repo"""
    for c in (config.DATA.parent, config.DATA.parent / "runtime", config.ROOT.parent.parent.parent / "Data" / "runtime"):
        if (c / "alerts_settings.json").is_file() or (c / "alert_bridge.json").is_file():
            return c
    return config.DATA.parent


def import_host(profile_types, apply=True, overwrite=False):
    """Map Host alerts_settings.json sounds onto an alert profile (dict of type cfgs). Returns [{type, from, url, volume, status}].
    Only wav/mp3/ogg files that sit inside the Host runtime folder are copied; nothing is ever changed on the Host side."""
    rt = host_runtime()
    f = rt / "alerts_settings.json"
    if not f.is_file():
        return [{"status": "no Host alerts_settings.json found"}]
    try:
        doc = json.loads(f.read_text("utf-8-sig"))
    except Exception as e:
        return [{"status": f"unreadable: {e}"}]
    out = []
    muted = bool(doc.get("MuteSounds"))
    for t in HOST_SOUND_TYPES:
        s = (doc.get("Sounds") or {}).get(t) or {}
        src = str(s.get("File") or "")
        try:
            vol = max(0, min(100, int(round(float(s.get("Volume", 0.7)) * 100))))
        except (TypeError, ValueError, OverflowError):
            vol = 70
        row = {"type": t, "from": src, "volume": vol, "url": "", "status": ""}
        out.append(row)
        if not src:
            row["status"] = "no sound set on Host"
            continue
        try:
            p = Path(src).resolve()
            if rt.resolve() not in p.parents or p.suffix.lower() not in (".wav", ".mp3", ".ogg", ".m4a") or not p.is_file():
                row["status"] = "skipped (file missing or outside the Host runtime folder)"
                continue
        except OSError:
            row["status"] = "skipped (bad path)"
            continue
        cur = profile_types[t]["sound"]
        if cur.get("url") and not overwrite:
            row["status"] = "kept (already has a sound)"
            continue
        if not apply:
            row["status"] = "would import"
            continue
        DIR.mkdir(parents=True, exist_ok=True)
        sn = safe_name("host_" + p.name)
        if not sn:
            row["status"] = "skipped (bad file name)"
            continue
        dst = DIR / sn
        if not dst.exists():
            shutil.copyfile(p, dst)
        row["url"] = "/alert-media/" + dst.name
        cur["url"], cur["volume"] = row["url"], row["volume"]
        if muted:
            cur["enabled"] = False
        row["status"] = "imported" + (" (Host had sounds muted: left off)" if muted else "")
    return out
