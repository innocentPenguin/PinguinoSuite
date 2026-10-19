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
    def __init__(self, player=None, sapi=None, now=time.time, rng=None):
        self.cfg = cfg.load()
        self.player = player or engine.Player(enabled=True)
        self.sapi = sapi or engine.sapi
        self.now = now
        self.rng = rng or random.Random()
        self.q = []                       # waiting items
        self.cv = threading.Condition()
        self.current = None
        self.history = deque(maxlen=500)
        self.stats = {"spoken": 0, "dropped": 0, "blocked": 0, "errors": 0}
        self.recent = deque(maxlen=400)   # timestamps of spoken lines (rate limit)
        self.last_kind = {}               # event -> time (cooldown)
        self.last_user = {}               # user -> time
        self.last_error = ""
        self.stop_flag = False
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

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
                     c["users"].get((user or "").lower()), c["roles"].get(role or ""), c["platforms"].get(platform or ""), c["default_persona"]):
            if cand and cand in c["personas"]:
                return cand
        return next(iter(c["personas"]))

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
    def handle(self, ev):
        """ev: {kind, user, amount, viewers, bits, tier, what, message, role, platform, text(raw, only for kind=say), priority, live}. Returns a result dict."""
        c = self.cfg
        kind = ev.get("kind") or "chat"
        user = str(ev.get("user") or "")
        base = {"kind": kind, "user": user}
        if kind not in c["events"] and kind != "say":
            return self._log({**base, "outcome": "ignored", "detail": "unknown event kind"})
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
        if ecfg["read_message"] or kind in ("say", "chat", "command"):
            raw = ev.get("message") if ev.get("message") is not None else ev.get("text")
            if raw:
                msg, why = textproc.clean_message(raw, c)
                if msg is None:
                    self.stats["blocked"] += 1
                    return self._log({**base, "outcome": "blocked", "detail": ", ".join(why)})
        if kind == "say":
            text = msg
        else:
            opts = persona["templates"].get(kind) or ecfg["templates"]
            tpl = textproc.pick_template(opts, amount, self.rng) or textproc.pick_template(ecfg["templates"], amount, self.rng)
            if kind == "command" and not persona["templates"].get(kind):
                tpl = "{message}"
            if not ecfg["read_message"] and kind not in ("chat", "command"):
                tpl = tpl.replace("{message}", "")
            vars_ = {"user": textproc.clean_name(user, L["clean_names"]) or "someone", "amount": amount, "viewers": ev.get("viewers") or amount, "bits": ev.get("bits") or amount,
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
                                          normalize=c["output"]["normalize"], whisper=item["whisper"])
                if self.state() in ("off", "muted", "quiet-mute"):      # switched off while synthesising
                    raise _Silenced()
                done = self.player.play(wav, secs)
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
        wav, secs = engine.render(text, persona, sting=persona["stinger"], sapi_obj=self.sapi, output_volume=c["output"]["volume"], normalize=c["output"]["normalize"])
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
