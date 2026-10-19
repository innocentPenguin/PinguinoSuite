"""New-chatter ding: plays a sound on the first message from each chatter, once per user per stream.

Plays locally on this PC only (and only when this device is the Suite master), never into chat. Off by default.
Per platform on/off, optional separate sound for Twitch 'first message ever', volume, and a gap between dings so a raid
cannot machine-gun (extra dings wait in a short queue, the rest are dropped)."""
import json
import os
import queue
import threading
import time
import urllib.request

import config
import console_log

SEEN_MAX = 20000


class Mci:
    """Windows MCI player (mp3/wav, with volume). Replaceable in tests."""
    def __init__(self):
        self.n = 0

    def play(self, path, volume):
        import ctypes
        mci = ctypes.windll.winmm.mciSendStringW
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
        self._master = (0.0, True)
        s = store.kv_get("ding_seen") or {}
        self.started, self.last, self.users = s.get("started", 0), s.get("last", 0), set(s.get("users", []))
        if start_worker:
            threading.Thread(target=self._worker, daemon=True).start()

    # session ----------------------------------------------------------
    def _save(self):
        self.store.kv_set("ding_seen", {"started": self.started, "last": self.last, "users": sorted(self.users)[-SEEN_MAX:]})

    def new_stream(self, reason="reset"):
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
        """Called for every new stored message. Never blocks and never raises."""
        try:
            st = config.settings()
            if m.platform not in st["ding_platforms"] or m.is_self or m.is_bot or not m.user_id:
                return False
            if (m.user or "").lower() in {b.lower() for b in st["bot_accounts"]}:
                return False
            now = self.clock()
            if not self.started or now - self.last > st["ding_session_gap_h"] * 3600:
                self.new_stream("quiet for a long time" if self.started else "first message")
            self.last = now
            key = f"{m.platform}:{m.user_id}"
            if key in self.users:
                return False
            self.users.add(key)
            self._save()
            first_ever = bool(st["ding_first_ever"]) and m.platform == "twitch" and m.first_time
            return self._enqueue("first" if first_ever else "new")
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

    def test(self):
        self.q.put_nowait("new") if not self.q.full() else None

    # playback ---------------------------------------------------------
    def sound_for(self, kind):
        st = config.settings()
        p = (st["ding_first_sound"] if kind == "first" else "") or st["ding_sound"]
        return p

    def play_one(self, kind):
        st = config.settings()
        path = self.sound_for(kind)
        if not path or not os.path.isfile(path):
            self.stats["errors"] += 1
            console_log.warn("ding", "sound file not found - pick one in Multi setup", dedupe_s=300)
            return False
        try:
            self.player.play(path, st["ding_volume"])
            self.stats["played"] += 1
            if self.stats["played"] in (1, 25, 100) or self.stats["played"] % 250 == 0:
                console_log.info("ding", f"{self.stats['played']} new-chatter dings played since Multi started")
            return True
        except Exception as e:
            self.stats["errors"] += 1
            console_log.error("ding", f"play failed: {e}", dedupe_s=120)
            return False

    def _worker(self):
        while True:
            kind = self.q.get()
            t0 = time.time()
            self.play_one(kind)
            gap = max(0.2, float(config.settings()["ding_cooldown_s"]))
            time.sleep(max(0, gap - (time.time() - t0)))

    # info -------------------------------------------------------------
    def info(self):
        st = config.settings()
        return {"enabled": bool(st["ding_platforms"]), "platforms": st["ding_platforms"], "first_ever": st["ding_first_ever"],
                "sound": st["ding_sound"], "sound_exists": bool(st["ding_sound"]) and os.path.isfile(st["ding_sound"]),
                "first_sound": st["ding_first_sound"], "volume": st["ding_volume"], "cooldown_s": st["ding_cooldown_s"],
                "chatters_this_stream": len(self.users), "master": self._master_cached(), **self.stats}
