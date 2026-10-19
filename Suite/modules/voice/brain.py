"""The decision layer: event in -> (rules, limits, wording, persona) -> queued line -> spoken, with every outcome logged.

Safety contract: while `master` is off (or muted / quiet-mute) NOTHING is synthesised or played; the attempt is only logged
with its outcome. Text from viewers is cleaned (secrets, links, profanity, repeats, length) before it can be spoken.
"""
import json
import random
import threading
import time
from collections import deque

import config as cfg
import console_log
import engine
import textproc


class Brain:
    def __init__(self, player=None, sapi=None, now=time.time, rng=None, cloud=None):
        self.cfg = cfg.load()
        self.player = player or engine.Player(enabled=True)
        self.sapi = sapi or engine.sapi
        self.cloud = cloud or engine.cloud
        self.timer_next = {}
        self.activity = 0                 # events handled since start (timers can require some)
        self.timer_seen = {}
        self.now = now
        self.rng = rng or random.Random()
        self.q = []                       # waiting items
        self.cv = threading.Condition()
        self.current = None
        self.history = deque(maxlen=500)
        self.stats = {"spoken": 0, "dropped": 0, "blocked": 0, "errors": 0}
        self.intervals = deque(maxlen=100)    # (start, end) epoch seconds of audio that was played: Listen can skip transcribing these
        self.recent = deque(maxlen=400)   # timestamps of spoken lines (rate limit)
        self.last_kind = {}               # event -> time (cooldown)
        self.last_text = {}
        self.last_user = {}               # user -> time
        self.last_error = ""
        self.stop_flag = False
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()
        threading.Thread(target=self._timers, daemon=True).start()

    # ------------------------------------------------------------ config
    def set_config(self, c):
        self.cfg = cfg.save(c)
        return self.cfg

    def reload(self):
        self.cfg = cfg.load()

    def set_master(self, on):
        c = dict(self.cfg)
        c["master"] = bool(on)
        if not on:
            self.panic()
        self.cfg = cfg.save(c, backup=False)
        console_log.info("voice", f"master switch {'ON' if on else 'OFF'}")
        return self.cfg

    def mute(self, minutes):
        c = dict(self.cfg)
        c["mute_until"] = self.now() + minutes * 60 if minutes else 0
        if minutes:
            self.panic()
        self.cfg = cfg.save(c, backup=False)
        return self.cfg

    # ------------------------------------------------------------ state
    def state(self):
        c = self.cfg
        if not c["master"]:
            return "off"
        if c["mute_until"] > self.now():
            return "muted"
        if textproc.in_quiet(c, self.now()):
            return "quiet-" + c["quiet"]["mode"]
        return "on"

    def persona_for(self, ev, kind, user, role, platform):
        c, e = self.cfg, self.cfg["events"].get(kind)
        for cand in ((e or {}).get("persona") if (e or {}).get("persona") != "default" else None,
                     c["users"].get((user or "").lower()), c["roles"].get(role or ""), c["platforms"].get(platform or ""), self._time_rule(), c["default_persona"]):
            if cand and cand in c["personas"]:
                return cand
        return next(iter(c["personas"]))

    def _time_rule(self):
        for r in self.cfg["time_rules"]:
            z = {"enabled": True, "start": r["from"], "end": r["to"]}
            if textproc.in_quiet({"quiet": z}, self.now()):
                return r["persona"]
        return None

    # ------------------------------------------------------------ counters and milestones
    def _counters(self):
        day = time.strftime("%Y-%m-%d", time.localtime(self.now()))
        if getattr(self, "_cnt", None) is None:
            try:
                self._cnt = json.loads(cfg.path("counters.json").read_text("utf8"))
            except (OSError, ValueError):
                self._cnt = {}
        c = self._cnt
        if c.get("day") != day:
            c["day"], c["daily"] = day, {}
        c.setdefault("total", {})
        c.setdefault("daily", {})
        return c

    def reset_counters(self):
        self._cnt = {}
        self._counters()
        self._save_counters()

    def _save_counters(self):
        try:
            cfg.path("counters.json").write_text(json.dumps(self._cnt), "utf8")
        except OSError:
            pass

    def _count(self, ev, kind):
        """Counts a real event and returns the milestones it crossed: [(milestone, count)]."""
        ms = [m for m in self.cfg["milestones"] if m["enabled"] and m["event"] == kind and m["lines"]]
        c = self._counters()
        try:
            amount = int(float(ev.get("amount") or ev.get("bits") or ev.get("viewers") or 1))
        except (TypeError, ValueError):
            amount = 1
        hits = []
        for scope in ("daily", "total"):
            for by in ("events", "amount"):
                k = f"{kind}:{by}"
                old = c[scope].get(k, 0)
                c[scope][k] = old + (1 if by == "events" else amount)
                for m in ms:
                    if m["scope"] == ("day" if scope == "daily" else "forever") and m["count_by"] == by and c[scope][k] // m["every"] > old // m["every"]:
                        hits.append((m, c[scope][k] // m["every"] * m["every"]))
        self._save_counters()
        return hits

    def handle(self, ev):
        res = self._handle(ev)
        kind = ev.get("kind")
        if not ev.get("manual") and kind in ("follow", "sub", "resub", "gift", "cheer", "raid", "redeem"):
            for m, n in self._count(ev, kind):
                pid = m["persona"] if m["persona"] in self.cfg["personas"] else self.persona_for(ev, kind, "", None, None)
                line = textproc.render(self.rng.choice(m["lines"]), {"count": n, "every": m["every"], "event": kind}, self.cfg["personas"][pid], self.rng)
                self._handle({"kind": "milestone", "message": line, "persona": pid, "priority": 6, "manual": True, "user": ""})
        return res

    # ------------------------------------------------------------ log
    def _log(self, rec):
        rec["ts"] = self.now()
        self.history.append(rec)
        try:
            with open(cfg.path("history.jsonl"), "a", encoding="utf8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
        lvl = "warn" if rec["outcome"] in ("error",) else "info" if rec["outcome"] in ("spoken", "queued") else "debug"
        console_log.log(lvl, "voice", f"{rec.get('kind','?')} by {rec.get('user','')}: {rec['outcome']}" + (f" - {rec['detail']}" if rec.get("detail") else ""))
        return rec

    # ------------------------------------------------------------ the pipeline
    def _handle(self, ev):
        """ev: {kind, user, amount, viewers, bits, tier, what, message, role, platform, text(raw, only for kind=say), priority, live}. Returns a result dict."""
        c = self.cfg
        kind = ev.get("kind") or "chat"
        user = str(ev.get("user") or "")
        base = {"kind": kind, "user": user}
        if kind not in c["events"] and kind not in ("say", "timer", "milestone"):
            return self._log({**base, "outcome": "ignored", "detail": "unknown event kind"})
        if kind == "voice_cmd":                                    # spoken confirmation of a fired voice command: its own switch under Words
            if not c["listen"]["confirm_commands"]:
                return self._log({**base, "outcome": "disabled", "detail": "spoken voice-command confirmation is off"})
            ev = {**ev, "kind": "voice_cmd", "manual": True, "_tpl": c["listen"]["confirm_text"]}
        ecfg = c["events"].get(kind) or {**cfg.EVENT_DEFAULTS["test"], "persona": "default", "templates": ["{message}"], "stinger": "", "only_live": False}
        st = self.state()
        manual = bool(ev.get("manual"))                         # a typed !tts or a Say button still obeys master/mute/quiet, but not event switches
        if st == "off":
            return self._log({**base, "outcome": "master_off", "detail": "Pinguino Voice is switched off, nothing was spoken"})
        if st == "muted":
            return self._log({**base, "outcome": "muted", "detail": "temporarily muted"})
        if st == "quiet-mute":
            return self._log({**base, "outcome": "quiet_hours", "detail": "inside quiet hours"})
        if not manual and not ecfg["enabled"]:
            return self._log({**base, "outcome": "disabled", "detail": f"{kind} announcements are off"})
        if ecfg.get("only_live") and ev.get("live") is False:
            return self._log({**base, "outcome": "not_live", "detail": "stream is not live"})
        L = c["limits"]
        self.activity += 1
        if user.lower() in L["blocked_users"] and ev.get("message"):
            ev = {**ev, "message": ""}
            if kind in ("chat", "command", "say"):
                self.stats["blocked"] += 1
                return self._log({**base, "outcome": "blocked_user", "detail": "this person's text is never spoken"})
        try:
            amount = int(float(ev.get("amount") or ev.get("bits") or ev.get("viewers") or 0))
        except (TypeError, ValueError):
            amount = 0
        if not manual and amount < ecfg["min_amount"]:
            return self._log({**base, "outcome": "below_min", "detail": f"{amount} is under the minimum {ecfg['min_amount']}"})
        t = self.now()
        if not manual and ecfg["cooldown_s"] and t - self.last_kind.get(kind, 0) < ecfg["cooldown_s"]:
            return self._log({**base, "outcome": "cooldown", "detail": f"{kind} cooldown"})
        if user and L["user_cooldown_s"] and kind in ("chat", "command", "say") and t - self.last_user.get(user.lower(), 0) < L["user_cooldown_s"]:
            return self._log({**base, "outcome": "user_cooldown", "detail": f"{user} spoke too recently"})
        while self.recent and t - self.recent[0] > 60:
            self.recent.popleft()
        if L["rate_per_min"] and len(self.recent) >= L["rate_per_min"] and not manual:
            return self._log({**base, "outcome": "rate_limited", "detail": f"over {L['rate_per_min']} lines a minute"})

        pid = ev.get("persona") if ev.get("persona") in c["personas"] else self.persona_for(ev, kind, user, ev.get("role"), ev.get("platform"))
        persona = c["personas"][pid]
        # wording
        msg, why = "", []
        if ecfg["read_message"] or kind in ("say", "timer", "milestone", "chat", "command"):
            raw = ev.get("message") if ev.get("message") is not None else ev.get("text")
            if raw:
                msg, why = textproc.clean_message(raw, c)
                if msg is None:
                    self.stats["blocked"] += 1
                    return self._log({**base, "outcome": "blocked", "detail": ", ".join(why)})
        if kind in ("say", "timer", "milestone"):
            text = msg
        else:
            opts = persona["templates"].get(kind) or ecfg["templates"]
            tpl = ev.get("_tpl") or textproc.pick_template(opts, amount, self.rng) or textproc.pick_template(ecfg["templates"], amount, self.rng)
            if kind == "command" and not persona["templates"].get(kind):
                tpl = "{message}"
            if not ecfg["read_message"] and kind not in ("chat", "command"):
                tpl = tpl.replace("{message}", "")
            vars_ = {"user": c["nicknames"].get(user.lower()) or textproc.clean_name(user, L["clean_names"]) or "someone", "command": ev.get("what") or "", "amount": amount, "viewers": ev.get("viewers") or amount, "bits": ev.get("bits") or amount,
                     "tier": ev.get("tier") or 1, "what": textproc.scrub_secrets(str(ev.get("what") or ""))[0], "message": msg}
            text = textproc.render(tpl, vars_, persona, self.rng)
            if "{catch}" not in tpl and persona["catchphrases"] and self.rng.random() * 100 < persona["catch_chance"]:
                text += " " + self.rng.choice(persona["catchphrases"])
            if persona["intro"]:
                text = persona["intro"] + " " + text
            if persona["outro"]:
                text += " " + persona["outro"]
        text, why2 = textproc.finish(text or "", c)
        if text is None:
            return self._log({**base, "outcome": "too_long", "detail": "skipped: over the length limit"})
        if not any(ch.isalnum() for ch in text):
            return self._log({**base, "outcome": "empty", "detail": "nothing to say"})
        if L["dedupe_s"] and not manual:
            key = text.lower()
            if t - self.last_text.get(key, 0) < L["dedupe_s"]:
                return self._log({**base, "outcome": "duplicate", "detail": "same text was just spoken", "text": text})
            self.last_text[key] = t
            if len(self.last_text) > 500:
                self.last_text = {k: v for k, v in self.last_text.items() if t - v < L["dedupe_s"]}
        prio = int(ev.get("priority") or ecfg["priority"])
        item = {"id": f"{int(t * 1000)}-{self.rng.randrange(10**4)}", "kind": kind, "user": user, "text": text, "persona": pid, "priority": prio, "t": t,
                "sting": (ecfg.get("stinger") or persona["stinger"]), "whisper": st == "quiet-whisper", "notes": why + why2, "names": [user] if user else []}
        return self._enqueue(item, ecfg)

    def _enqueue(self, item, ecfg):
        Q = self.cfg["queue"]
        with self.cv:
            busy = self.current is not None or self.player.busy
            if Q["mode"] == "drop_new" and (busy or self.q):
                self.stats["dropped"] += 1
                return self._log({"kind": item["kind"], "user": item["user"], "outcome": "dropped", "detail": "busy and queue mode is drop_new", "text": item["text"]})
            if Q["merge_similar"] and item["kind"] in ("follow", "sub", "resub") and item["user"]:
                for w in self.q:
                    if w["kind"] == item["kind"] and w["persona"] == item["persona"]:
                        w["names"].append(item["user"])
                        w["text"] = self._merged_text(w)
                        self.cv.notify()
                        return self._log({"kind": item["kind"], "user": item["user"], "outcome": "merged", "detail": f"joined {len(w['names'])} in one line", "text": w["text"]})
            self.q.append(item)
            while len(self.q) > Q["max_queue"]:
                low = min(self.q, key=lambda x: (x["priority"], -x["t"]))
                self.q.remove(low)
                self.stats["dropped"] += 1
                self._log({"kind": low["kind"], "user": low["user"], "outcome": "dropped", "detail": "queue full", "text": low["text"]})
            if Q["mode"] == "interrupt" and self.current and item["priority"] >= Q["interrupt_min_priority"] and item["priority"] > self.current["priority"]:
                self.player.stop()
            self.cv.notify()
        self.last_kind[item["kind"]] = item["t"]
        if item["user"]:
            self.last_user[item["user"].lower()] = item["t"]
        return self._log({"kind": item["kind"], "user": item["user"], "outcome": "queued", "detail": item["persona"], "text": item["text"], "persona": item["persona"]})

    def _merged_text(self, w):
        names = [textproc.clean_name(n, self.cfg["limits"]["clean_names"]) for n in w["names"]]
        if len(names) <= 3:
            who = ", ".join(names[:-1]) + " and " + names[-1]
        else:
            who = f"{names[0]}, {names[1]} and {len(names) - 2} more"
        word = {"follow": "following", "sub": "subscribing", "resub": "resubscribing"}.get(w["kind"], w["kind"])
        return f"Thank you {who} for {word}!"

    # ------------------------------------------------------------ worker
    def _run(self):
        while True:
            with self.cv:
                while not self.q:
                    self.cv.wait(1.0)
                age = self.cfg["queue"]["max_age_s"]
                t = self.now()
                for w in [w for w in self.q if t - w["t"] > age]:
                    self.q.remove(w)
                    self.stats["dropped"] += 1
                    self._log({"kind": w["kind"], "user": w["user"], "outcome": "dropped", "detail": "waited too long", "text": w["text"]})
                if not self.q:
                    continue
                item = max(self.q, key=lambda x: (x["priority"], -x["t"]))
                self.q.remove(item)
                self.current = item
            try:
                if self.state() in ("off", "muted", "quiet-mute"):
                    raise _Silenced()
                c = self.cfg
                persona = c["personas"][item["persona"]]
                wav, secs = engine.render(item["text"], persona, sting=item["sting"], sapi_obj=self.sapi, output_volume=c["output"]["volume"],
                                          normalize=c["output"]["normalize"], whisper=item["whisper"], cloud_obj=self.cloud, cloud_cfg=c["cloud"], sound_dir=cfg.path("sounds"))
                if self.state() in ("off", "muted", "quiet-mute"):      # switched off while synthesising
                    raise _Silenced()
                t0 = self.now()
                self._flag(True, t0 + secs + 0.5)
                try:
                    done = self.player.play(wav, secs, c["output"]["device"])
                finally:
                    self.intervals.append((t0 - 0.2, self.now() + 1.0))
                    self._flag(False, 0)
                self.stats["spoken"] += 1
                self.recent.append(self.now())
                self._log({"kind": item["kind"], "user": item["user"], "outcome": "spoken" if done else "interrupted", "text": item["text"], "persona": item["persona"],
                           "seconds": round(secs, 1)})
                time.sleep(c["queue"]["gap_ms"] / 1000)
            except _Silenced:
                self._log({"kind": item["kind"], "user": item["user"], "outcome": "silenced", "detail": "switched off or muted before it was played", "text": item["text"]})
            except Exception as e:
                self.stats["errors"] += 1
                self.last_error = str(e)[:200]
                self._log({"kind": item["kind"], "user": item["user"], "outcome": "error", "detail": self.last_error, "text": item["text"]})
                time.sleep(1)
            finally:
                self.current = None

    # ------------------------------------------------------------ scheduled announcements
    def _timers(self):
        while True:
            time.sleep(1.0)
            try:
                self._timer_tick()
            except Exception as e:
                console_log.warn("timers", f"timer tick failed: {str(e)[:100]}", dedupe_s=300)

    def _timer_tick(self):
        c, t = self.cfg, self.now()
        live = {x["id"] for x in c["timers"]}
        for k in [k for k in self.timer_next if k not in live]:
            self.timer_next.pop(k, None)
        for tm in c["timers"]:
            if not tm["enabled"] or not tm["lines"]:
                self.timer_next.pop(tm["id"], None)
                continue
            nxt = self.timer_next.get(tm["id"])
            if nxt is None:
                self.timer_next[tm["id"]] = t + self._gap(tm)
                continue
            if t < nxt:
                continue
            self.timer_next[tm["id"]] = t + self._gap(tm)
            if self.state() != "on" and not self.state().startswith("quiet-whisper"):
                continue                                           # silent states: do not even log every minute
            if tm["min_chat"] and self.activity - self.timer_seen.get(tm["id"], 0) < tm["min_chat"]:
                continue
            self.timer_seen[tm["id"]] = self.activity
            self.fire_timer(tm)

    def _gap(self, tm):
        g = tm["every_min"] * 60
        return g * (1 + self.rng.uniform(-tm["jitter_pct"], tm["jitter_pct"]) / 100.0)

    def fire_timer(self, tm):
        pid = tm["persona"] if tm["persona"] in self.cfg["personas"] else self.cfg["default_persona"]
        line = self.rng.choice(tm["lines"])
        return self.handle({"kind": "timer", "user": "", "message": textproc.render(line, {}, self.cfg["personas"][pid], self.rng), "persona": pid, "priority": tm["priority"], "manual": True, "_raw": True})

    def _flag(self, on, until):
        try:
            cfg.path("speaking.json").write_text(json.dumps({"speaking": on, "until": until, "ts": self.now()}), "utf8")
        except OSError:
            pass

    def soundcheck(self):
        """Explicit button only: one short line on the real output, even with the master OFF. Bypasses the queue, never triggered by events."""
        c = self.cfg
        persona = c["personas"][c["default_persona"]]
        wav, secs = engine.render("Sound check. One, two, three.", persona, sting="none", sapi_obj=self.sapi, output_volume=c["output"]["volume"], normalize=c["output"]["normalize"],
                                  cloud_obj=self.cloud, cloud_cfg=c["cloud"], sound_dir=cfg.path("sounds"))
        t0 = self.now()
        self._flag(True, t0 + secs + 0.5)
        try:
            self.player.play(wav, secs, c["output"]["device"])
        finally:
            self.intervals.append((t0 - 0.2, self.now() + 1.0))
            self._flag(False, 0)
        self._log({"kind": "soundcheck", "user": "", "outcome": "spoken", "text": "Sound check", "persona": c["default_persona"], "seconds": round(secs, 1)})
        return {"ok": True, "seconds": round(secs, 1), "device": c["output"]["device"] or "Windows default"}

    # ------------------------------------------------------------ controls
    def panic(self):
        with self.cv:
            n = len(self.q)
            self.q.clear()
        self.player.stop()
        return n

    def preview(self, pid, text, c=None):
        """WAV bytes for the page's own audio element. Never touches the PC speakers, works while the master is off."""
        c = c or self.cfg
        persona = c["personas"].get(pid) or c["personas"][c["default_persona"]]
        text, _ = textproc.clean_message(text, c)
        text, _ = textproc.finish(text or "", c) if text else (None, [])
        if not text:
            raise ValueError("nothing to say after the safety filters")
        wav, secs = engine.render(text, persona, sting=persona["stinger"], sapi_obj=self.sapi, output_volume=c["output"]["volume"], normalize=c["output"]["normalize"], cloud_obj=self.cloud, cloud_cfg=c["cloud"], sound_dir=cfg.path("sounds"))
        return wav, text

    def replay(self):
        for h in reversed(self.history):
            if h["outcome"] in ("spoken", "interrupted") and h.get("text"):
                return self.handle({"kind": "say", "message": h["text"], "user": "", "persona": h.get("persona"), "manual": True})
        return {"outcome": "nothing_to_repeat"}

    def tail(self, n=60):
        return list(self.history)[-n:][::-1]


class _Silenced(Exception):
    pass
