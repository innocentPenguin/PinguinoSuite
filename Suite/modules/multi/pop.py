"""Chat pop: a short sound for every chat message (Streamer.bot's 'chat' / 'chat (yt louder)' actions).

Per platform on/off and volume (YouTube louder by default, as in Streamer.bot: Twitch 50 %, YouTube 76 %), times the master
volume. One pop per pop_cooldown_s with a tiny queue so bursts do not pile up. Local, master PC only, never into chat. Off by default."""
import os
import queue
import threading
import time

import config
import console_log
import ding

PLATFORMS = ("twitch", "youtube", "discord")


class Pop:
    def __init__(self, player=None, clock=time.time, master=ding.is_master, start_worker=True):
        self.player, self.clock, self.master = player or ding.Mci(), clock, master
        self.q = queue.Queue(maxsize=3)
        self.stats = {"played": 0, "dropped": 0, "errors": 0}
        self._master = (0.0, True)
        if start_worker:
            threading.Thread(target=self._worker, daemon=True).start()

    def _master_cached(self):
        t, v = self._master
        if self.clock() - t > 10:
            v = bool(self.master())
            self._master = (self.clock(), v)
        return v

    def volume_for(self, platform):
        st = config.settings()
        base = st["pop_volume"].get(platform, st["pop_volume"].get("twitch", 50))
        return max(0, min(100, base * st["ding_master_volume"] / 100))

    def observe(self, m):
        """Called for every new message. Never blocks, never raises."""
        try:
            st = config.settings()
            if m.platform not in st["pop_platforms"]:
                return False
            who = (m.user or "").lower()
            if m.is_bot or who in {b.lower() for b in st["bot_accounts"]}:
                return False
            if (m.is_self or who in {n.lower() for n in st["my_names"]}) and not st["pop_own"]:
                return False
            if not self._master_cached():
                return False
            try:
                self.q.put_nowait(m.platform)
                return True
            except queue.Full:
                self.stats["dropped"] += 1
                return False
        except Exception as e:
            console_log.error("pop", f"observe failed: {e}", dedupe_s=60)
            return False

    def test(self, platform="twitch"):
        if not self.q.full():
            self.q.put_nowait(platform)

    def play_one(self, platform):
        path = config.settings()["pop_sound"]
        if not path or not os.path.isfile(path):
            self.stats["errors"] += 1
            console_log.warn("pop", "chat pop sound file not found - pick one in Multi setup", dedupe_s=300)
            return False
        try:
            self.player.play(path, self.volume_for(platform))
            self.stats["played"] += 1
            if self.stats["played"] in (1, 100) or self.stats["played"] % 1000 == 0:
                console_log.info("pop", f"{self.stats['played']} chat pops played since Multi started")
            return True
        except Exception as e:
            self.stats["errors"] += 1
            console_log.error("pop", f"play failed: {e}", dedupe_s=120)
            return False

    def _worker(self):
        while True:
            platform = self.q.get()
            t0 = time.time()
            self.play_one(platform)
            gap = max(0.1, float(config.settings()["pop_cooldown_s"]))
            time.sleep(max(0, gap - (time.time() - t0)))

    def info(self):
        st = config.settings()
        return {"enabled": bool(st["pop_platforms"]), "platforms": st["pop_platforms"], "sound": st["pop_sound"],
                "sound_exists": bool(st["pop_sound"]) and os.path.isfile(st["pop_sound"]), "volume": st["pop_volume"],
                "master_volume": st["ding_master_volume"], "cooldown_s": st["pop_cooldown_s"], "own": st["pop_own"],
                "master": self._master_cached(), **self.stats}
