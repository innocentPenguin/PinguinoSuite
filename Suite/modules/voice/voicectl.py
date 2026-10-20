"""Spoken control: "pinguinobot change the game to ...", "... change the title to ...", "... timeout <user> for 5 minutes".

Reads Ivan's lines from Listen (GET /api/segments of the live session - Listen is not changed) and acts through the Host.
OFF by default. Every action is parsed strictly, checked (caps, protected people, bad words, secrets), asked back
("I heard: ... say pinguinobot confirm") unless confirmation is switched off, and logged. Nothing here ever posts to chat by itself.
"""
import difflib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque

import config as cfg
import console_log
import textproc

NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
             "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100}
UNITS = {"second": 1, "seconds": 1, "sec": 1, "secs": 1, "minute": 60, "minutes": 60, "min": 60, "mins": 60, "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600}
ACTIONS = ("game", "title", "timeout")


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9_@' ]+", " ", (text or "").lower().replace("’", "'"))).strip()


def strip_wake(text, wake_words):
    """Return the words after a leading wake word (fuzzy: 'pinguino bot', 'penguino but'), or None."""
    toks = norm(text).split()
    while toks and toks[0] in ("hey", "ok", "okay", "yo", "alright"):
        toks = toks[1:]
    want = [w.replace(" ", "") for w in wake_words if w.strip()]
    for n, need in ((2, 0.8), (1, 0.86)):   # longest first so 'pinguino bot' eats both words
        if len(toks) < n:
            continue
        cand = "".join(toks[:n])
        if any(cand == w or (abs(len(cand) - len(w)) <= 2 and difflib.SequenceMatcher(None, cand, w).ratio() >= need) for w in want):
            return toks[n:]
    return None


def parse_duration(toks):
    """['5','minutes'] / ['a','minute'] / ['thirty','seconds'] -> seconds, tokens used; or (None, 0)."""
    if not toks:
        return None, 0
    n, used = None, 0
    if toks[0].isdigit():
        n, used = int(toks[0]), 1
    elif toks[0] in NUM_WORDS:
        n, used = NUM_WORDS[toks[0]], 1
        if len(toks) > 1 and toks[1] in NUM_WORDS and NUM_WORDS[toks[0]] >= 20 and NUM_WORDS[toks[1]] < 10:
            n, used = n + NUM_WORDS[toks[1]], 2
    if n is None or len(toks) <= used or toks[used] not in UNITS:
        return None, 0
    return n * UNITS[toks[used]], used + 1


def parse(rest, text_orig=""):
    """Words after the wake word -> {'action': ..., ...}, {'control': 'confirm'|'cancel'} or None."""
    if not rest:
        return None
    head = " ".join(rest)
    if head in ("confirm", "yes", "yes do it", "do it", "confirmed", "go ahead"):
        return {"control": "confirm"}
    if head in ("cancel", "no", "never mind", "nevermind", "stop", "forget it", "abort"):
        return {"control": "cancel"}
    m = re.match(r"^(?:please )?(?:change|set|switch|update)(?: the| my| our)? (game|category)(?: to| into)? (.+)$", head)
    if m:
        return {"action": "game", "value": m.group(2).strip()}
    m = re.match(r"^(?:please )?(?:change|set|update)(?: the| my| our)?(?: stream)? title(?: to| into)? (.+)$", head)
    if m:
        return {"action": "title", "value": m.group(1).strip()}
    m = re.match(r"^(?:please )?(?:time ?out|timeout|time him out|time out user) (?:user )?(@?[a-z0-9_ ]{2,40}?) for (.+)$", head)
    if m:
        secs, used = parse_duration(m.group(2).split())
        if secs:
            return {"action": "timeout", "user": m.group(1).replace(" ", "").lstrip("@"), "seconds": secs}
        return {"action": "timeout", "user": m.group(1).replace(" ", "").lstrip("@"), "seconds": 0, "bad": "I did not catch how long"}
    return None


def recent_chatters(limit=400):
    """Names seen in today's chat log (newest last), for fuzzy name matching of a spoken name."""
    names = []
    try:
        import datetime
        p = cfg.data_dir().parent / "chat_logs" / (datetime.date.today().isoformat() + ".jsonl")
        with open(p, encoding="utf-8-sig") as f:
            lines = f.readlines()[-3000:]
        for ln in lines:
            try:
                u = json.loads(ln).get("u")
            except ValueError:
                continue
            if u:
                names.append(u.lower())
    except Exception:
        pass
    seen, out = set(), []
    for n in reversed(names):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:limit]


def resolve_user(spoken, chatters):
    """Spoken name ('snowy roses') -> exact recent chatter, or None. Never guesses below 0.82 similarity."""
    s = re.sub(r"[^a-z0-9]", "", spoken.lower())
    if not s:
        return None
    flat = {re.sub(r"[^a-z0-9]", "", c): c for c in chatters}
    if s in flat:
        return flat[s]
    best = difflib.get_close_matches(s, list(flat), n=2, cutoff=0.82)
    if len(best) == 1 or (len(best) == 2 and difflib.SequenceMatcher(None, s, best[0]).ratio() - difflib.SequenceMatcher(None, s, best[1]).ratio() > 0.08):
        return flat[best[0]]
    return None


def fmt_dur(s):
    if s % 3600 == 0:
        return f"{s // 3600} hour{'s' if s // 3600 != 1 else ''}"
    if s % 60 == 0:
        return f"{s // 60} minute{'s' if s // 60 != 1 else ''}"
    return f"{s} seconds"


class Control:
    def __init__(self, get_cfg, host_post, speak=None, chatters=recent_chatters, now=time.time, overlaps=lambda s, e: False):
        self.get_cfg, self.host_post, self.speak, self.chatters, self.now = get_cfg, host_post, speak, chatters, now
        self.overlaps = overlaps   # (start, end) epoch -> True when the bot was talking then (never obey its own voice)
        self.pending = None
        self.log = deque(maxlen=200)
        self.last_fire = {}
        self.lock = threading.Lock()
        self.src = {"ok": None, "err": "", "session": None, "after": None, "heard": 0}

    def c(self):
        return self.get_cfg().get("control", {})

    # ------------------------------------------------------------ audit trail
    def _log(self, outcome, detail="", **kw):
        rec = {"ts": self.now(), "outcome": outcome, "detail": detail, **kw}
        self.log.append(rec)
        try:
            with open(cfg.path("control.jsonl"), "a", encoding="utf8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
        console_log.log("warn" if outcome in ("failed", "unsupported") else "info", "control", f"{outcome}: {detail}" + (f" [{kw.get('action')}]" if kw.get("action") else ""))
        return rec

    def _say(self, text):
        if self.speak and self.c().get("readback", True):
            try:
                self.speak(text)
            except Exception:
                pass

    # ------------------------------------------------------------ input
    def hear(self, text, unsure=0.0, at=None):
        """One transcribed line of Ivan. Returns a log record or None when it was not for us."""
        c = self.c()
        if not c.get("enabled"):
            return None
        rest = strip_wake(text, c.get("wake_words", []))
        if rest is None:
            return None
        if at and self.overlaps(at[0] - 1.0, at[1] + 1.0):
            return self._log("ignored", "the bot was speaking at that moment, so I did not obey it", text=text[:120])
        self.src["heard"] += 1
        if unsure > c.get("max_unsure", 0.5):
            return self._log("ignored", "heard it but Listen was not sure enough", text=text[:120])
        if textproc.scrub_secrets(text)[1]:
            self._say("That looked like a secret, I will not act on it")
            return self._log("refused", "the line looked like it contained a secret", text="[hidden]")
        intent = parse(rest)
        if intent is None:
            return self._log("unknown", "no command I know", text=" ".join(rest)[:120])
        if intent.get("control") == "confirm":
            return self.confirm(by="voice")
        if intent.get("control") == "cancel":
            return self.cancel(by="voice")
        return self.propose(intent, text)

    def propose(self, intent, heard=""):
        c = self.c()
        act = intent["action"]
        if not c.get("allow", {}).get(act):
            return self._log("blocked", f"{act} by voice is switched off", action=act)
        last = self.last_fire.get(act, 0)
        if self.now() - last < c.get("cooldown_s", 5):
            return self._log("blocked", "too soon after the last one", action=act)
        ok, why, intent = self.check(intent)
        if not ok:
            self._say(why)
            return self._log("refused", why, action=act, heard=heard[:120])
        summary = self.summary(intent)
        with self.lock:
            self.pending = {"intent": intent, "summary": summary, "expires": self.now() + c.get("expire_s", 25), "heard": heard[:160]}
        if not c.get("require_confirm", True):
            return self.confirm(by="auto")
        self._say(f"I heard: {summary}. Confirm, or cancel?")
        return self._log("pending", summary, action=act)

    def summary(self, i):
        if i["action"] == "game":
            return f"change the game to {i['value']}"
        if i["action"] == "title":
            return f"change the title to {i['value']}"
        return f"time out {i['user']} for {fmt_dur(i['seconds'])}"

    # ------------------------------------------------------------ safety checks
    def check(self, i):
        c, extra = self.c(), self.get_cfg().get("limits", {}).get("bad_words", [])
        if i.get("bad"):
            return False, i["bad"], i
        if i["action"] in ("game", "title"):
            v = i["value"].strip()
            cap = 140 if i["action"] == "title" else 80
            if len(v) < 2:
                return False, "I did not catch that", i
            if len(v) > cap:
                return False, f"That {i['action']} is too long", i
            if textproc.scrub_secrets(v)[1]:
                return False, "That looked like a secret, I will not set it", i
            if textproc.profane(v, extra) or any(b in v.lower() for b in set(cfg.BAD_WORDS) | set(extra)):   # strict: it goes on the public channel page
                return False, "That has a word I will not put on the channel", i
            i = {**i, "value": self.pretty(v, c)}
            return True, "", i
        user = resolve_user(i["user"], self.chatters())
        if not user:
            return False, f"I could not find {i['user']} in chat today", i
        if user in [p.lower() for p in c.get("protected", [])]:
            return False, f"{user} is protected", i
        mx = c.get("max_timeout_s", 600)
        secs = i["seconds"]
        if secs < 1:
            return False, "I did not catch how long", i
        if secs > mx:
            return False, f"The longest I will time out is {fmt_dur(mx)}", i
        return True, "", {**i, "user": user}

    @staticmethod
    def pretty(v, c):
        return v if not c.get("title_case", True) else " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in v.split())

    # ------------------------------------------------------------ decide / run
    def confirm(self, by="page"):
        with self.lock:
            p, self.pending = self.pending, None
        if not p:
            return self._log("ignored", "nothing was waiting for a confirm")
        if self.now() > p["expires"]:
            return self._log("expired", p["summary"], action=p["intent"]["action"])
        return self.run(p["intent"], by)

    def cancel(self, by="page"):
        with self.lock:
            p, self.pending = self.pending, None
        return self._log("cancelled", p["summary"] if p else "nothing was waiting", by=by)

    def run(self, i, by):
        act = i["action"]
        self.last_fire[act] = self.now()
        try:
            if act == "timeout":
                res = self.host_post("/api/mod/timeout", {"user": i["user"], "seconds": i["seconds"], "reason": "voice command by the streamer"})
            else:
                res = self.host_post("/api/channel/update", {act: i["value"]})
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self._say("The Host cannot do that yet")
                return self._log("unsupported", "the Host has no endpoint for this yet (ask 02 to add it)", action=act, by=by)
            msg = ""
            try:
                msg = str(json.loads(e.read() or b"{}").get("error", ""))
            except Exception:
                pass
            self._say("That did not work")
            return self._log("failed", (msg or f"Host answered HTTP {e.code}")[:140], action=act, by=by)
        except Exception as e:
            self._say("That did not work")
            return self._log("failed", str(e)[:120], action=act, by=by)
        if res.get("ok"):
            self._say("Done")
            return self._log("done", self.summary(i), action=act, by=by)
        self._say("That did not work")
        return self._log("failed", str(res.get("error", "Host refused"))[:140], action=act, by=by)

    def expire(self):
        with self.lock:
            if self.pending and self.now() > self.pending["expires"]:
                p, self.pending = self.pending, None
                self._log("expired", p["summary"], action=p["intent"]["action"])

    def state(self):
        p = self.pending
        return {"enabled": bool(self.c().get("enabled")), "pending": {"summary": p["summary"], "left_s": max(0, int(p["expires"] - self.now())), "heard": p["heard"]} if p else None,
                "source": self.src, "recent": list(self.log)[-30:][::-1]}


# ------------------------------------------------------------------ Listen transcript reader
def _get(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def read_loop(ctl, listen_url, stop=lambda: False, sleep=time.sleep):
    """Poll Listen for new lines of the live session. Starts from now: never replays old speech."""
    src = ctl.src
    while not stop():
        try:
            if not ctl.c().get("enabled"):
                src["after"] = None
                sleep(2)
                continue
            st = _get(listen_url + "/api/status")
            sid = st.get("live_session") if st.get("listening") else None
            if not sid:
                src.update(ok=True, err="Listen is not recording", session=None)
                sleep(2)
                continue
            if sid != src["session"] or src["after"] is None:
                rows = _get(f"{listen_url}/api/segments?session={sid}&after=0&limit=1000")
                made = next((x.get("created") for x in _get(listen_url + "/api/sessions") if x.get("id") == sid), None)
                src.update(session=sid, after=max([r["id"] for r in rows] + [0]), created=made)
            rows = _get(f"{listen_url}/api/segments?session={sid}&after={src['after']}&limit=50")
            for r in rows:
                src["after"] = max(src["after"], r["id"])
                at = (src["created"] + r["start"], src["created"] + r["end"]) if src.get("created") is not None else None
                ctl.hear(r.get("text") or "", r.get("unsure") or 0, at)
            ctl.expire()
            src.update(ok=True, err="")
        except Exception as e:
            src.update(ok=False, err=str(e)[:100])
        sleep(1.5)
