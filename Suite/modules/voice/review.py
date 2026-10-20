"""Hourly self-review: compare what Speak said with what Ivan said, what chat said and what the logs recorded.

Rule based and local (no cloud, no AI call): every finding shows its evidence and, where a safe setting would help, a one-click suggestion
that is only ever applied when Ivan presses it. Reports are kept in Data\\runtime\\voice\\reports; serious findings also go to
incidents.jsonl (one JSON per line) so a person or a helper session can watch that file and react in real time.
"""
import datetime
import json
import re
import time
import urllib.request
from collections import Counter

import config as cfg
import console_log

SPOKEN = ("spoken",)
DROPS = ("dropped", "rate_limited", "too_long", "error", "user_cooldown", "cooldown")
NEUTRAL = ("master_off", "muted", "quiet_hours", "disabled", "not_live", "below_min", "empty", "ignored", "blocked_user", "duplicate", "queued", "merged", "silenced")
BOT_WORDS = ("bot", "pinguinobot", "tts", "voice", "robot", "narrator", "announcer", "that voice", "the voice")
SEV = {"info": 0, "warn": 1, "high": 2}

# settings a suggestion may touch (dotted path -> (lo, hi)); anything else is refused
SAFE_SETS = {"output.volume": (10, 100), "limits.rate_per_min": (1, 60), "limits.user_cooldown_s": (0, 600), "limits.dedupe_s": (0, 300),
             "queue.max_queue": (1, 30), "queue.max_age_s": (5, 300), "limits.max_chars": (40, 400)}


def fmt_ts(t):
    return datetime.datetime.fromtimestamp(t).strftime("%H:%M:%S")


def read_jsonl(path, since, until, key="ts", tail=6000, scale=1.0):
    out = []
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.readlines()[-tail:]
    except OSError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        t = (r.get(key) or 0) * scale
        if since <= t <= until:
            r["_t"] = t
            out.append(r)
    return out


def _get(url, timeout=4):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


# ------------------------------------------------------------------ gathering
def gather(since, until, history, listen_url, c, now=time.time):
    """Everything the checks need. Missing sources are reported, never fatal."""
    d = {"since": since, "until": until, "speak": [h for h in history if since <= h.get("ts", 0) <= until], "lines": [], "chat": [], "console": [], "vlog": [], "control": [], "missing": []}
    base = cfg.data_dir().parent
    if c.get("use_transcript", True):
        try:
            sess = {s["id"]: s for s in _get(listen_url + "/api/sessions")}
            for sid, s in sess.items():
                if s.get("kind") != "live" or (s.get("created") or 0) > until or (s.get("created") or 0) + (s.get("duration") or 0) + 7200 < since:
                    continue
                after = 0
                while True:
                    rows = _get(f"{listen_url}/api/segments?session={sid}&after={after}&limit=1000")
                    for r in rows:
                        a0 = s["created"] + r["start"]
                        if since <= a0 <= until:
                            d["lines"].append({"s": a0, "e": s["created"] + r["end"], "text": r.get("text") or "", "unsure": r.get("unsure") or 0})
                        after = max(after, r["id"])
                    if len(rows) < 1000:
                        break
            d["vlog"] = [r for r in _get(listen_url + "/api/voice-log").get("log", []) if since <= r.get("ts", 0) <= until]
        except Exception as e:
            d["missing"].append(f"Listen transcript unavailable ({str(e)[:60]})")
    if c.get("use_chat", True):
        day = datetime.date.fromtimestamp(since)
        days = {day, datetime.date.fromtimestamp(until)}
        for dd in days:
            d["chat"] += read_jsonl(base / "chat_logs" / (dd.isoformat() + ".jsonl"), since, until, key="t", scale=0.001)
        if not d["chat"]:
            d["missing"].append("no chat messages in the window")
    if c.get("use_console", True):
        for mod in ("voice", "listen", "host", "core"):
            for r in read_jsonl(base / "console" / f"{mod}.jsonl", since, until):
                if r.get("level") in ("warn", "error"):
                    d["console"].append(r)
    d["control"] = read_jsonl(cfg.path("control.jsonl"), since, until)
    return d


# ------------------------------------------------------------------ checks
def _dur(h):
    return h.get("seconds") or max(1.5, len(h.get("text", "")) / 14.0)


def _f(id_, sev, title, detail, evidence=(), suggest=None):
    return {"id": id_, "sev": sev, "title": title, "detail": detail, "evidence": list(evidence)[:6], "suggest": suggest}


def chk_talk_over(d, c):
    spoken = [(h["ts"] - _dur(h), h["ts"], h) for h in d["speak"] if h.get("outcome") == "spoken" and h.get("kind") != "soundcheck"]
    hits = []
    for s, e, h in spoken:
        for ln in d["lines"]:
            if ln["s"] < e and ln["e"] > s and len(ln["text"].split()) >= 3:
                hits.append((fmt_ts(ln["s"]), h.get("text", "")[:60], ln["text"][:70]))
                break
    ign = [r for r in d["vlog"] if r.get("outcome") == "ignored_bot_voice"]
    n = len(hits)
    out = []
    if n >= c.get("talk_over_max", 3):
        out.append(_f("talk_over", "warn", f"The bot spoke while you were talking ({n} times)", "Its voice overlapped your speech. Best fix: play it on headphones or another output so the mic never hears it.",
                      [f"{t}: bot \"{b}\" / you \"{y}\"" for t, b, y in hits], {"label": "Lower the volume to 45%", "set": {"output.volume": 45}}))
    if ign:
        out.append(_f("ignored_cmds", "warn", f"{len(ign)} of your voice commands were ignored while the bot was speaking", "Listen skips voice commands during bot speech so the bot cannot trigger itself.",
                      [f"{fmt_ts(r['ts'])}: \"{r.get('heard', '')[:60]}\"" for r in ign]))
    return out


def chk_complaints(d, c):
    phrases = [p.lower() for p in c.get("complaint_phrases", [])]
    praise = [p.lower() for p in c.get("praise_phrases", [])]
    spoken_ts = sorted(h["ts"] for h in d["speak"] if h.get("outcome") == "spoken")
    bad, good = [], []
    for ln in d["lines"]:
        t = ln["text"].lower()
        near = any(0 <= ln["s"] - ts <= c.get("complaint_window_s", 45) for ts in spoken_ts)
        about = near or any(w in t for w in BOT_WORDS)
        if about and any(p in t for p in phrases):
            bad.append(f"{fmt_ts(ln['s'])} you: \"{ln['text'][:90]}\"")
        elif about and any(p in t for p in praise):
            good.append(f"{fmt_ts(ln['s'])} you: \"{ln['text'][:90]}\"")
    for m in d["chat"]:
        t = (m.get("m") or "").lower()
        if any(w in t for w in BOT_WORDS):
            if any(p in t for p in phrases):
                bad.append(f"{fmt_ts(m['_t'])} {m.get('u')}: \"{m.get('m', '')[:90]}\"")
            elif any(p in t for p in praise):
                good.append(f"{fmt_ts(m['_t'])} {m.get('u')}: \"{m.get('m', '')[:90]}\"")
    out = []
    if bad:
        out.append(_f("complaints", "high" if len(bad) >= 2 else "warn", f"{len(bad)} sign(s) the voice annoyed you or chat", "Phrases like \"too loud\" or \"shut up\" right after the bot spoke, or chat saying the same.",
                      bad, {"label": "Slow it down: 8 lines/min, 30 s per person", "set": {"limits.rate_per_min": 8, "limits.user_cooldown_s": 30}}))
    if good:
        out.append(_f("praise", "info", f"{len(good)} nice thing(s) said about the voice", "Keep doing what works.", good))
    return out


def chk_pronounce(d, c):
    hits = [ln for ln in d["lines"] if re.search(r"pronounc|say it like|say (his|her|their) name|said (it|that) wrong|mispronounc", ln["text"].lower())]
    return [_f("pronounce", "warn", f"{len(hits)} time(s) you corrected how something was said", "Add the right spelling to Words > Pronunciation so it is said properly next time.",
               [f"{fmt_ts(h['s'])}: \"{h['text'][:90]}\"" for h in hits])] if hits else []


def chk_repeats(d, c):
    cnt = Counter(h.get("text", "") for h in d["speak"] if h.get("outcome") == "spoken" and h.get("text") and h.get("kind") != "soundcheck")
    rep = [(t, n) for t, n in cnt.most_common(5) if n >= c.get("repeat_max", 3)]
    return [_f("repeats", "warn", "The same line was said several times", "Add more wording variants to that event or raise the repeat-suppression window.",
               [f"{n}x \"{t[:80]}\"" for t, n in rep], {"label": "Suppress repeats for 60 s", "set": {"limits.dedupe_s": 60}})] if rep else []


def chk_drops(d, c):
    tries = [h for h in d["speak"] if h.get("outcome") in SPOKEN + DROPS]
    drops = [h for h in tries if h.get("outcome") in DROPS]
    errs = [h for h in drops if h.get("outcome") == "error"]
    out = []
    if len(drops) >= 5 and len(drops) / max(1, len(tries)) > 0.25:
        why = Counter(h.get("outcome") for h in drops)
        out.append(_f("drops", "warn", f"{len(drops)} of {len(tries)} lines were dropped or held back", ", ".join(f"{k}: {v}" for k, v in why.most_common()),
                      [f"{fmt_ts(h['ts'])} {h.get('kind')} {h.get('user')}: {h.get('outcome')} ({h.get('detail', '')[:50]})" for h in drops[-5:]],
                      {"label": "Allow 18 lines/min", "set": {"limits.rate_per_min": 18}} if why.get("rate_limited") else None))
    if errs:
        out.append(_f("play_errors", "high", f"{len(errs)} line(s) failed to play", "The voice engine or the output device refused. Check Overview > Errors.", [f"{fmt_ts(h['ts'])}: {h.get('detail', '')[:80]}" for h in errs]))
    return out


def chk_silent(d, c):
    off = [h for h in d["speak"] if h.get("outcome") == "master_off"]
    return [_f("silent_master", "info", f"{len(off)} event(s) arrived while the master switch was OFF", "Nothing was spoken for them, as designed. Switch the master ON if you wanted announcements.",
               [f"{fmt_ts(h['ts'])} {h.get('kind')} {h.get('user')}" for h in off[-4:]])] if off else []


def chk_console(d, c):
    if not d["console"]:
        return []
    g = Counter((r.get("module"), (r.get("msg") or "")[:90]) for r in d["console"])
    errs = sum(1 for r in d["console"] if r.get("level") == "error")
    return [_f("console", "high" if errs else "warn", f"{len(d['console'])} warning/error line(s) in the logs ({errs} errors)", "Grouped by source and message.",
               [f"{n}x [{m}] {t}" for (m, t), n in g.most_common(6)])]


def chk_control(d, c):
    rows = d["control"]
    bad = [r for r in rows if r.get("outcome") in ("failed", "unsupported", "refused", "unknown", "ignored")]
    return [_f("control", "warn", f"{len(bad)} of {len(rows)} spoken control command(s) did not work", "Refused, not understood, failed, or the Host cannot do it yet.",
               [f"{fmt_ts(r['ts'])} {r.get('outcome')}: {r.get('detail', '')[:80]}" for r in bad[-5:]])] if bad else []


CHECKS = [("talk_over", chk_talk_over), ("complaints", chk_complaints), ("pronounce", chk_pronounce), ("repeats", chk_repeats), ("drops", chk_drops),
          ("silent_master", chk_silent), ("console", chk_console), ("control", chk_control)]


def stats(d):
    sp = [h for h in d["speak"] if h.get("outcome") == "spoken"]
    return {"spoken": len(sp), "events": len(d["speak"]), "by_kind": dict(Counter(h.get("kind") for h in sp)), "chat_messages": len(d["chat"]),
            "your_lines": len(d["lines"]), "your_words": sum(len(ln["text"].split()) for ln in d["lines"]), "console_problems": len(d["console"]), "control_commands": len(d["control"])}


def analyse(d, c, now=time.time):
    findings = []
    for cid, fn in CHECKS:
        if c.get("checks", {}).get(cid, True):
            findings += fn(d, c)
    findings.sort(key=lambda f: -SEV[f["sev"]])
    score = max(0, 100 - sum({"info": 0, "warn": 8, "high": 20}[f["sev"]] for f in findings))
    return {"id": time.strftime("%Y%m%d-%H%M%S", time.localtime(now())), "ts": now(), "since": d["since"], "until": d["until"], "minutes": round((d["until"] - d["since"]) / 60),
            "score": score, "stats": stats(d), "findings": findings, "missing": d["missing"]}


# ------------------------------------------------------------------ storage + incidents
def _rdir():
    p = cfg.path("reports")
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_report(rep, keep=48):
    (_rdir() / (rep["id"] + ".json")).write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf8")
    files = sorted(_rdir().glob("*.json"))
    for f in files[:-keep]:
        f.unlink(missing_ok=True)
    with open(cfg.path("incidents.jsonl"), "a", encoding="utf8") as f:
        for fd in rep["findings"]:
            if fd["sev"] == "high":
                f.write(json.dumps({"ts": rep["ts"], "report": rep["id"], "id": fd["id"], "title": fd["title"], "evidence": fd["evidence"][:4]}, ensure_ascii=False) + "\n")
    for fd in rep["findings"]:
        if fd["sev"] != "info":
            console_log.log("warn" if fd["sev"] == "high" else "info", "review", f"{fd['title']}")


def list_reports():
    out = []
    for f in sorted(_rdir().glob("*.json"), reverse=True):
        try:
            r = json.loads(f.read_text("utf8"))
            out.append({"id": r["id"], "ts": r["ts"], "minutes": r["minutes"], "score": r["score"], "findings": len(r["findings"]), "high": sum(1 for x in r["findings"] if x["sev"] == "high")})
        except (OSError, ValueError, KeyError):
            pass
    return out


def get_report(rid):
    if not re.fullmatch(r"[0-9-]{15}", rid or ""):
        raise ValueError("bad report id")
    try:
        return json.loads((_rdir() / (rid + ".json")).read_text("utf8"))
    except OSError:
        raise ValueError("no such report")


def apply_suggestion(sset, cur):
    """Validate a {'path': value} suggestion against SAFE_SETS and return a patched copy of the config (caller saves)."""
    import copy
    new = copy.deepcopy(cur)
    for p, v in sset.items():
        if p not in SAFE_SETS:
            raise ValueError(f"not allowed to change {p}")
        lo, hi = SAFE_SETS[p]
        a, b = p.split(".")
        new[a][b] = max(lo, min(hi, int(v)))
    return new


# ------------------------------------------------------------------ scheduler
class Reviewer:
    def __init__(self, get_cfg, history, listen_url, is_live, now=time.time):
        self.get_cfg, self.history, self.listen_url, self.is_live, self.now = get_cfg, history, listen_url, is_live, now
        self.last_end = None
        self.was_live = False
        self.live_since = None
        self.last = {"ts": 0, "id": None, "err": ""}

    def c(self):
        return self.get_cfg().get("review", {})

    def run(self, minutes=None, reason="manual"):
        c = self.c()
        until = self.now()
        since = until - (minutes or c.get("interval_min", 60)) * 60 if minutes or self.last_end is None else self.last_end
        rep = analyse(gather(since, until, list(self.history()), self.listen_url, c, self.now), c, self.now)
        rep["reason"] = reason
        save_report(rep, c.get("keep", 48))
        self.last_end = until
        self.last = {"ts": until, "id": rep["id"], "err": ""}
        return rep

    def tick(self):
        """Call every ~30 s. Reviews each interval while the stream is live, plus a closing review when it ends."""
        c = self.c()
        if not c.get("enabled"):
            return None
        live = bool(self.is_live()) if c.get("only_when_live", True) else True
        now = self.now()
        try:
            if live and not self.was_live:
                self.live_since = self.last_end = now
            if live and self.last_end is not None and now - self.last_end >= c.get("interval_min", 60) * 60:
                return self.run(reason="hourly")
            if self.was_live and not live and c.get("final_review", True) and self.last_end is not None and now - self.last_end > 300:
                return self.run(reason="stream ended")
        except Exception as e:
            self.last["err"] = str(e)[:100]
            console_log.warn("review", f"review failed: {str(e)[:100]}", dedupe_s=300)
        finally:
            self.was_live = live
        return None
