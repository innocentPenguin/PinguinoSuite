"""New-chatter / returning-chatter ding: plays a sound on a chatter's first message, locally, never into chat.

Three rows (config.ding_rows), exactly one fires per message, priority 1>2>3:
        "first"      never seen by Multi, or Twitch's first-message flag
        "new_stream" known from an earlier stream, first message this stream
        "returning"  already counted this stream, but the message carries the pipeline flag "returning" (silent >= gap_h)
Final volume = row volume * ding_master_volume / 100. All settings live in Multi's settings.json (survive restarts).
Plays only on the master device, one ding per ding_cooldown_s (short queue, extras dropped). Off by default."""
import json
import os
import queue
import re
import threading
import time
import urllib.request
from collections import deque

import config
import console_log

SEEN_MAX = 20000
KNOWN_MAX = 100000


BOT_NAMES = {"pinguinob0t", "pinguinobot", "chattypinguino", "pinguinohelper", "soundalerts", "sery_bot", "nightbot", "streamelements", "streamlabs",
             "moobot", "fossabot", "wizebot"}
BOT_RE = re.compile(r"b[o0]t$")             # anything ending in bot / b0t


def is_bot(m, st=None):
    """ONE bot test for every local sound (chatter dings, chat pop): flagged bot, built-in bot names, *bot / *b0t names, the settings' bot list."""
    st = st or config.settings()
    who = (getattr(m, "user", "") or "").lower()
    return bool(getattr(m, "is_bot", False) or who in BOT_NAMES or BOT_RE.search(who) or who in {b.lower() for b in st.get("bot_accounts", [])})


class Mci:
    """Windows MCI player (mp3/wav, with volume). Replaceable in tests. Thread-safe: every sound uses its own alias, so sounds can overlap."""
    def __init__(self):
        self.n = 0
        self._lk = threading.Lock()

    def play(self, path, volume):
        import ctypes
        mci = ctypes.windll.winmm.mciSendStringW
        if path.lower().endswith(".mp3") and os.path.isfile(path[:-4] + ".wav"):
            path = path[:-4] + ".wav"              # a trimmed .wav twin (no leading/trailing silence, opens instantly) wins over the mp3
        with self._lk:
            self.n += 1
            alias = f"pgding{self.n}"
        kind = "waveaudio" if path.lower().endswith(".wav") else "mpegvideo"
        buf = ctypes.create_unicode_buffer(255)
        if mci(f'open "{path}" type {kind} alias {alias}', buf, 254, 0):
            raise RuntimeError("Windows could not open the sound file")
        try:
            mci(f"setaudio {alias} volume to {int(max(0, min(100, volume)) * 10)}", buf, 254, 0)
            if mci(f"play {alias} wait", buf, 254, 0):
                raise RuntimeError("Windows could not play the sound")
        finally:
            mci(f"close {alias}", buf, 254, 0)


def is_master():
    """True unless the core says this device is an auxiliary (a lone device is always master)."""
    tok = os.environ.get("PINGUINO_API_TOKEN", "")
    if not tok:
        return True
    base = os.environ.get("PINGUINO_CORE_URL", "http://127.0.0.1:8760").rstrip("/")
    try:
        req = urllib.request.Request(base + "/api/device/lease", headers={"Authorization": "Bearer " + tok})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("is_master", True))
    except Exception:
        return True


class Ding:
    def __init__(self, store, player=None, clock=time.time, master=is_master, start_worker=True):
        self.store, self.player, self.clock, self.master = store, player or Mci(), clock, master
        self.q = queue.Queue(maxsize=5)
        self.stats = {"played": 0, "dropped": 0, "errors": 0}
        self.recent = deque(maxlen=200)             # for GET /api/newchatters (other modules may react, e.g. a welcome bot)
        self._master = (0.0, True)
        s = store.kv_get("ding_seen") or {}
        self.started, self.last, self.users = s.get("started", 0), s.get("last", 0), set(s.get("users", []))
        self.known = set(store.kv_get("ding_known") or [])
        if start_worker:
            threading.Thread(target=self._worker, daemon=True).start()

    # session ----------------------------------------------------------
    def _save(self):
        self.store.kv_set("ding_seen", {"started": self.started, "last": self.last, "users": sorted(self.users)[-SEEN_MAX:]})
        self.store.kv_set("ding_known", sorted(self.known)[-KNOWN_MAX:])

    def new_stream(self, reason="reset"):
        """A new stream starts: everyone who chatted so far becomes 'known' (a returning chatter next time)."""
        self.known |= self.users
        self.started, self.last, self.users = self.clock(), self.clock(), set()
        self._save()
        console_log.info("ding", f"new-chatter list cleared ({reason})")

    def _master_cached(self):
        t, v = self._master
        if self.clock() - t > 10:
            v = bool(self.master())
            self._master = (self.clock(), v)
        return v

    # input ------------------------------------------------------------
    def observe(self, m):
        """Called for every new stored message. Never blocks and never raises. Returns the ding kind queued, or False."""
        try:
            st = config.settings()
            if m.platform not in st["ding_platforms"] or m.is_self or m.is_bot or not m.user_id:
                return False
            who = (m.user or "").lower()
            if is_bot(m, st) or who in {n.lower() for n in st["my_names"]}:
                return False                                     # bots and the streamer never ding
            now = self.clock()
            if not self.started:
                self.new_stream("first message")
            elif st["ding_scope"] != "ever" and now - self.last > st["ding_session_gap_h"] * 3600:
                self.new_stream("quiet for a long time")
            self.last = now
            key = f"{m.platform}:{m.user_id}"
            if key in self.users:
                kind = "returning" if "returning" in (m.flags or []) else None     # row 3 only for someone already counted this stream
                if not kind:
                    return False
            else:
                self.users.add(key)
                known = key in self.known
                self.known.add(key)
                self._save()
                kind = "first" if (not known or (m.platform == "twitch" and m.first_time)) else "new_stream"
            row = config.ding_rows(st)[kind]
            if not (row["on"] or row["notify"]):
                return False
            self.recent.append({"ts": now, "platform": m.platform, "user": m.user, "display": m.display, "kind": kind, "notify": bool(row["notify"])})
            return kind if row["on"] and self._enqueue(kind) else False
        except Exception as e:
            console_log.error("ding", f"observe failed: {e}", dedupe_s=60)
            return False

    def _enqueue(self, kind):
        if not self._master_cached():
            return False
        try:
            self.q.put_nowait(kind)
            return True
        except queue.Full:
            self.stats["dropped"] += 1
            return False

    def test(self, kind="first"):
        if kind in config.DING_ROWS and not self.q.full():
            self.q.put_nowait(kind)

    # playback ---------------------------------------------------------
    def sound_for(self, kind):
        st = config.settings()
        return config.ding_rows(st).get(kind, {}).get("sound") or st["ding_sound"]

    def volume_for(self, kind):
        st = config.settings()
        base = config.ding_rows(st).get(kind, {}).get("volume", st["ding_volume"])
        return max(0, min(100, base * st["ding_master_volume"] / 100))

    def play_one(self, kind):
        path = self.sound_for(kind)
        if not path or not os.path.isfile(path):
            self.stats["errors"] += 1
            console_log.warn("ding", "sound file not found - pick one in Multi setup", dedupe_s=300)
            return False
        try:
            self.player.play(path, self.volume_for(kind))
            self.stats["played"] += 1
            if self.stats["played"] in (1, 25, 100) or self.stats["played"] % 250 == 0:
                console_log.info("ding", f"{self.stats['played']} chatter dings played since Multi started")
            return True
        except Exception as e:
            self.stats["errors"] += 1
            console_log.error("ding", f"play failed: {e}", dedupe_s=120)
            return False

    def _worker(self):
        while True:
            kind = self.q.get()
            t0 = time.time()
            threading.Thread(target=self.play_one, args=(kind,), daemon=True).start()     # never wait for a sound to end: the next one may overlap
            gap = max(0.2, float(config.settings()["ding_cooldown_s"]))
            time.sleep(max(0, gap - (time.time() - t0)))

    # info -------------------------------------------------------------
    def info(self):
        st = config.settings()
        exists = lambda p: bool(p) and os.path.isfile(p)
        rows = {n: dict(r, sound_exists=exists(r["sound"] or st["ding_sound"])) for n, r in config.ding_rows(st).items()}
        return {"enabled": bool(st["ding_platforms"]), "rows": rows, "gap_h": st["ding_session_gap_h"], "platforms": st["ding_platforms"], "scope": st["ding_scope"],
                "first_ever": st["ding_first_ever"], "returning": st["ding_returning"],
                "sound": st["ding_sound"], "sound_exists": exists(st["ding_sound"]),
                "first_sound": st["ding_first_sound"], "returning_sound": st["ding_returning_sound"],
                "returning_sound_exists": exists(st["ding_returning_sound"] or st["ding_sound"]),
                "volume": st["ding_volume"], "returning_volume": st["ding_returning_volume"], "master_volume": st["ding_master_volume"],
                "cooldown_s": st["ding_cooldown_s"], "chatters_this_stream": len(self.users), "known_chatters": len(self.known),
                "master": self._master_cached(), **self.stats}
