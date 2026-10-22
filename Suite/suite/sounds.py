"""Your own notification sounds: mp3 / wav / ogg files kept under <data dir>/sounds. Only the Settings > Personalize page adds or removes them.
Safety: the file type is checked by its first bytes (not the name), size and count are capped, files are stored under a generated id (the
user's file name is only a label), and "remove" moves the file to sounds/removed/ instead of deleting it."""
import hashlib
import json
import re
import threading
import time
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024   # a notification sound is a second or two; 2 MB is already generous
MAX_FILES = 24
ID = re.compile(r"^u:[0-9a-f]{10}$")
_lock = threading.Lock()


def kind_of(b):
    """'mp3' | 'wav' | 'ogg' from the magic bytes, else None."""
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "wav"
    if b[:4] == b"OggS":
        return "ogg"
    if b[:3] == b"ID3" or (len(b) > 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg"}


class Sounds:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.index = self.dir / "sounds.json"

    def _load(self):
        try:
            d = json.loads(self.index.read_text("utf8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, d):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.index.with_name("sounds.json.tmp")
        tmp.write_text(json.dumps(d, indent=1), "utf8")
        tmp.replace(self.index)

    def list(self):
        d = self._load()
        return [{"id": k, "name": v.get("name", k), "kind": v.get("kind"), "bytes": v.get("bytes", 0)} for k, v in d.items() if (self.dir / v.get("file", "?")).is_file()]

    def add(self, name, data):
        """-> (ok, entry-or-message)"""
        if not data:
            return False, "the file is empty"
        if len(data) > MAX_BYTES:
            return False, f"the file is too big (max {MAX_BYTES // 1024 // 1024} MB)"
        k = kind_of(data)
        if not k:
            return False, "only mp3, wav or ogg files can be added"
        label = re.sub(r"[\x00-\x1f<>]", "", Path(str(name or "sound")).stem).strip()[:40] or "My sound"
        with _lock:
            d = self._load()
            if len([1 for v in d.values() if (self.dir / v.get("file", "?")).is_file()]) >= MAX_FILES:
                return False, f"you can keep up to {MAX_FILES} sounds; remove one first"
            sid = "u:" + hashlib.sha256(data).hexdigest()[:10]
            if sid in d and (self.dir / d[sid]["file"]).is_file():
                return True, {"id": sid, "name": d[sid]["name"], "kind": d[sid]["kind"], "bytes": d[sid]["bytes"], "duplicate": True}
            fname = sid[2:] + "." + k
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / fname).write_bytes(data)
            d[sid] = {"name": label, "kind": k, "file": fname, "bytes": len(data), "added": time.strftime("%Y-%m-%dT%H:%M:%S")}
            self._save(d)
        return True, {"id": sid, "name": label, "kind": k, "bytes": len(data)}

    def get(self, sid):
        """-> (bytes, mime) or None"""
        if not ID.match(sid or ""):
            return None
        v = self._load().get(sid)
        f = self.dir / v["file"] if v and re.match(r"^[0-9a-f]{10}\.(mp3|wav|ogg)$", v.get("file", "")) else None
        if not f or not f.is_file():
            return None
        return f.read_bytes(), MIME.get(v.get("kind"), "application/octet-stream")

    def remove(self, sid):
        """Moves the file to sounds/removed/ (nothing is deleted)."""
        if not ID.match(sid or ""):
            return False
        with _lock:
            d = self._load()
            v = d.pop(sid, None)
            if not v:
                return False
            src = self.dir / v.get("file", "?")
            if src.is_file():
                (self.dir / "removed").mkdir(parents=True, exist_ok=True)
                src.replace(self.dir / "removed" / f"{int(time.time())}-{src.name}")
            self._save(d)
        return True
