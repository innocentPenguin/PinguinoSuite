"""Voice Studio back end (built on Listen's own data): "talks like me" style profile, voice commands, clip markers.

Everything here is local and listen-only by default: voice commands are OFF until you switch them on, and each command
has its own switch. A command can drop a marker (e.g. "clip that") or ask the Suite core to call another module's API
(an OBS macro in Link, a Host endpoint...) through /api/voice/dispatch, which only forwards POSTs to registered modules.
"""
import difflib
import json
import os
import re
import statistics
import threading
import time
from collections import Counter

import requests

import config as cfg
import db
import learn

CMD_FILE = cfg.DATA / "voice_commands.json"
MARKERS = cfg.DATA / "markers.jsonl"
GOLD = cfg.DATA / "gold.jsonl"
GOOD_HOURS = 10.0  # rule of thumb for a clean personal voice/style set
_lock = threading.Lock()
_last = {}  # command id -> last fire time (cooldown)

STOP = set("the a an and or but so to of in on at for with is are was were be been it its this that i you he she we they me my your our "
           "im i'm it's thats that's dont don't just not no yes do did have has had if then there here what how why who when about out up "
           "down get got go going can will would could should like really very".split())
FILLERS = ["um", "uh", "like", "literally", "basically", "actually", "bro", "dude", "chat", "guys", "yeah", "okay", "so", "right", "lol", "gg"]

DEFAULT_CMDS = {
    "enabled": False,          # master switch: nothing below fires while this is off
    "wake_word": "",           # optional: e.g. "pinguino" -> only "pinguino clip that" counts
    "cooldown_s": 8,           # per command
    "max_unsure": 0.6,         # ignore lines Listen is not sure it heard right
    "commands": [{"id": "clip", "phrase": "clip that", "enabled": False, "action": {"type": "marker", "label": "clip"}}],
}


# ---------------------------------------------------------------- talks like me
def _verified_rows(include_unverified):
    q = ("SELECT COALESCE(corrected_text, text) AS t, end - start AS d, status FROM segments WHERE status IN ('approved','corrected')"
         + (" OR (status='new' AND unsure<=0.6)" if include_unverified else ""))
    return db.rows(q)


def style(include_unverified=False, top=24):
    rows = _verified_rows(include_unverified)
    toks_per_line, uni, bi, tri, secs = [], Counter(), Counter(), Counter(), 0.0
    common = learn.common_words()
    for r in rows:
        toks = [x for x in (learn.norm(w) for w in (r["t"] or "").split()) if x]
        if not toks:
            continue
        toks_per_line.append(len(toks))
        secs += max(0.0, r["d"] or 0.0)
        uni.update(toks)
        bi.update(zip(toks, toks[1:]))
        tri.update(zip(toks, toks[1:], toks[2:]))
    n_words = sum(toks_per_line)
    words = [{"w": w, "n": n} for w, n in uni.most_common(400) if n >= 3 and len(w) > 2 and w not in STOP and w not in common][:top]
    def phrases(counter, minc):
        out = []
        for g, n in counter.most_common(300):
            if n < minc or all(x in STOP for x in g):
                continue
            out.append({"w": " ".join(g), "n": n})
        return out[:top]
    fillers = [{"w": f, "per100": round(uni[f] * 100 / n_words, 2)} for f in FILLERS if n_words and uni[f] >= 3]
    fillers.sort(key=lambda x: -x["per100"])
    counts = db.one("SELECT SUM(status='corrected') c, SUM(status='approved') a FROM segments") or {}
    c, a = counts.get("c") or 0, counts.get("a") or 0
    gold = sum(1 for _ in open(GOLD, encoding="utf8")) if GOLD.exists() else 0
    return {
        "lines": len(toks_per_line), "words": n_words, "hours": round(secs / 3600, 2), "good_hours": GOOD_HOURS,
        "avg_words": round(n_words / len(toks_per_line), 1) if toks_per_line else 0,
        "median_words": statistics.median(toks_per_line) if toks_per_line else 0,
        "your_words": words, "phrases": phrases(tri, 3) + phrases(bi, 5), "fillers": fillers[:8],
        "accuracy": round(100 * a / (a + c)) if a + c else None,   # lines that needed no correction
        "gold_pairs": gold, "include_unverified": include_unverified,
    }


# ---------------------------------------------------------------- commands
def load_cmds():
    d = json.loads(json.dumps(DEFAULT_CMDS))
    try:
        d.update(json.loads(CMD_FILE.read_text("utf8")))
    except (OSError, ValueError):
        pass
    return d


def save_cmds(d):
    clean = {"enabled": bool(d.get("enabled")), "wake_word": learn.norm(str(d.get("wake_word", ""))), "cooldown_s": max(1, min(600, int(d.get("cooldown_s", 8)))),
             "max_unsure": float(d.get("max_unsure", 0.6)), "commands": []}
    for i, c in enumerate(d.get("commands", [])[:60]):
        ph = " ".join(learn.norm(w) for w in str(c.get("phrase", "")).split() if learn.norm(w))
        if not ph:
            continue
        act = c.get("action") or {}
        a = {"type": act.get("type") if act.get("type") in ("marker", "call") else "marker"}
        if a["type"] == "marker":
            a["label"] = str(act.get("label") or ph)[:40]
        else:
            a.update({"module": str(act.get("module", ""))[:30], "path": str(act.get("path", ""))[:200], "body": act.get("body") if isinstance(act.get("body"), (dict, list)) else {}})
        clean["commands"].append({"id": re.sub(r"[^\w-]", "", str(c.get("id") or f"c{i}"))[:30] or f"c{i}", "phrase": ph, "enabled": bool(c.get("enabled")), "action": a})
    with _lock:
        CMD_FILE.write_text(json.dumps(clean, indent=2), "utf8")
    return clean


def _tokens(text):
    return [x for x in (learn.norm(w) for w in text.split()) if x]


def _find(toks, phrase_toks, start=0):
    """Index just after the first (fuzzy) occurrence of phrase_toks in toks at/after start, else -1."""
    n = len(phrase_toks)
    for i in range(start, len(toks) - n + 1):
        ok = True
        for a, b in zip(toks[i:i + n], phrase_toks):
            if a != b and not (len(b) >= 4 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85):
                ok = False
                break
        if ok:
            return i + n
    return -1


def matches(text, cfg_cmds, only_enabled=True):
    toks = _tokens(text)
    start = 0
    wake = cfg_cmds.get("wake_word", "")
    if wake:
        w = _find(toks, wake.split())
        if w < 0:
            return []
        start = w
    return [c for c in cfg_cmds["commands"] if (c["enabled"] or not only_enabled) and _find(toks, c["phrase"].split(), start) >= 0]


def _marker(label, text, seg):
    rec = {"ts": time.time(), "label": label, "text": text, "session": (seg or {}).get("session_id"), "t": (seg or {}).get("t")}
    with _lock, open(MARKERS, "a", encoding="utf8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def markers(n=50):
    try:
        lines = MARKERS.read_text("utf8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out[::-1]


def run_action(cmd, text, seg, log):
    a = cmd["action"]
    if a["type"] == "marker":
        _marker(a.get("label", cmd["phrase"]), text, seg)
        log("info", f"voice command '{cmd['phrase']}' -> marker", "voice")
        return {"ok": True, "detail": "marker saved"}
    core = os.environ.get("PINGUINO_CORE_URL", "http://127.0.0.1:8760")
    tok = os.environ.get("PINGUINO_API_TOKEN", "")
    try:
        r = requests.post(core + "/api/voice/dispatch", json={"module": a["module"], "path": a["path"], "body": a.get("body") or {}},
                          headers={"Authorization": f"Bearer {tok}"}, timeout=12)
        ok = r.ok
        log("info" if ok else "warn", f"voice command '{cmd['phrase']}' -> {a['module']}{a['path']}: {r.status_code} {r.text[:120]}", "voice")
        return {"ok": ok, "detail": f"{r.status_code} {r.text[:160]}"}
    except requests.RequestException as e:
        log("warn", f"voice command '{cmd['phrase']}' failed: {e}", "voice")
        return {"ok": False, "detail": str(e)[:160]}


def handle_segment(seg, log, emit):
    """Called for every live segment. Fires enabled commands (master switch on, confident line, cooldown respected)."""
    d = load_cmds()
    if not d["enabled"] or (seg.get("unsure") or 0) > d["max_unsure"]:
        return
    text = seg.get("text") or ""
    for c in matches(text, d):
        now = time.time()
        if now - _last.get(c["id"], 0) < d["cooldown_s"]:
            continue
        _last[c["id"]] = now
        threading.Thread(target=lambda c=c: emit({"type": "voice_cmd", "phrase": c["phrase"], "text": text, **run_action(c, text, seg, log)}), daemon=True).start()
