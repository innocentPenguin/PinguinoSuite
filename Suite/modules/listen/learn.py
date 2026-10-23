"""Learning from corrections: vocabulary (biases Whisper), replacement rules (fix repeat mistakes), uncertainty flags."""
import difflib
import json
import re

import config as cfg
import db

_common = None


def common_words() -> set:
    global _common
    if _common is None:
        try:
            _common = {w.strip().lower() for w in cfg.COMMON_WORDS.read_text("utf8", "ignore").split() if w.strip()}
        except Exception:
            _common = set()
    return _common


def norm(w: str) -> str:
    w = w.replace("’", "'").lower()
    return re.sub(r"[^\w']+", "", w).strip("'")


def _strip_punct(w: str) -> str:
    return re.sub(r"^[^\w']+|[^\w']+$", "", w.replace("’", "'"))


def _trail(w: str) -> str:
    m = re.search(r"[^\w']+$", w)
    return m.group(0) if m else ""


# ---------------------------------------------------------------- rules / vocab

def load_rules() -> dict:
    out = {}
    for r in db.rows("SELECT wrong,right,count FROM rules"):
        # a one-word rule on an everyday word must be confirmed twice before it rewrites everything
        if r["count"] < 2 and " " not in r["wrong"] and r["wrong"] in common_words():
            continue
        out[r["wrong"]] = r["right"]
    return out


def vocab_terms(limit=40, max_chars=300) -> list:
    terms, size = [], 0
    for r in db.rows("SELECT term FROM vocab ORDER BY count DESC, term LIMIT ?", (limit,)):
        size += len(r["term"]) + 2
        if size > max_chars:
            break
        terms.append(r["term"])
    return terms


def add_vocab(term: str, source="correction"):
    term = term.strip()
    if not term:
        return
    db.run("INSERT INTO vocab(term,count,source) VALUES(?,1,?) ON CONFLICT(term) DO UPDATE SET count=count+1", (term, source))


# ---------------------------------------------------------------- applying learning

def apply_rules(raw_words: list, rules: dict) -> list:
    """raw_words: [{w,s,e,p}] -> words with learned replacements applied (flagged f=True)."""
    if not rules:
        return [dict(w) for w in raw_words]
    norms = [norm(w["w"]) for w in raw_words]
    out, i = [], 0
    while i < len(raw_words):
        for n in (4, 3, 2, 1):
            if i + n > len(raw_words):
                continue
            key = " ".join(norms[i:i + n])
            if key and key in rules:
                right = rules[key].split()
                if not right:
                    break
                s, e = raw_words[i]["s"], raw_words[i + n - 1]["e"]
                step = (e - s) / len(right)
                for k, rw in enumerate(right):
                    nw = {"w": rw, "s": s + k * step, "e": s + (k + 1) * step, "p": 1.0, "f": True,
                          "was": " ".join(x["w"] for x in raw_words[i:i + n])}
                    if k == len(right) - 1:
                        nw["w"] += _trail(raw_words[i + n - 1]["w"])
                    out.append(nw)
                i += n
                break
        else:
            out.append(dict(raw_words[i]))
            i += 1
    return out


def finalize(raw_words: list, avg_logprob: float = 0.0) -> dict:
    """Apply rules, then grade every word: ok / warn (yellow) / bad (red) / fix (auto-corrected by learning)."""
    st = cfg.settings()
    yellow, red = st["yellow"], st["red"]
    words = apply_rules(raw_words, load_rules())
    shaky = avg_logprob < -1.2
    unsure = 0.0
    for w in words:
        if w.get("f"):
            w["l"] = "fix"
            continue
        p = w["p"]
        lvl = "bad" if p < red else "warn" if p < yellow else "ok"
        if shaky and lvl == "ok" and p < 0.9:
            lvl = "warn"
        w["l"] = lvl
        if lvl != "ok":
            unsure += (1 - p) * (2 if lvl == "bad" else 1)
    return {
        "words": words,
        "text": " ".join(w["w"] for w in words),
        "raw_text": " ".join(w["w"] for w in raw_words),
        "unsure": round(unsure, 3),
    }


# ---------------------------------------------------------------- learning from review notes (setting learn_from_notes, default OFF)
_ARROW = re.compile(r"\s*(?:->|→|=>)\s*")
_VOCAB = re.compile(r"^(?:vocab|vocabulary|hotwords?|names?|terms?)\s*[:=]\s*(.+)$", re.I)
_WRONG = re.compile(r"^(?:wrong|misheard|bad)\s*(?:words?)?\s*[:=]\s*(.+)$", re.I)
_QUOTES = "\"'“”‘’`"


def _clean(s: str) -> str:
    return " ".join(w for w in (_strip_punct(t.strip(_QUOTES)) for t in s.split()) if w)


def parse_note(note: str) -> dict:
    """What a reviewer's note says, if it uses one of the markers: 'wrong -> right', 'vocab: A, B', 'wrong: word'. Anything else is ignored."""
    out = {"rules": [], "vocab": [], "wrong": []}
    for part in re.split(r"[;\n]+", note or ""):
        part = part.strip()
        if not part:
            continue
        m = _VOCAB.match(part)
        if m:
            out["vocab"] += [t for t in (_clean(x) for x in m.group(1).split(",")) if t and len(t.split()) <= 4]
            continue
        m = _WRONG.match(part)
        if m:
            out["wrong"] += [norm(t) for t in re.split(r"[,\s]+", m.group(1)) if norm(t)]
            continue
        bits = _ARROW.split(part)
        if len(bits) == 2:
            a, b = _clean(bits[0]), _clean(bits[1])
            if a and b and len(a.split()) <= 4 and len(b.split()) <= 4 and norm(a.replace(" ", "")) != norm(b.replace(" ", "")):
                out["rules"].append((" ".join(norm(w) for w in a.split()), b))
    return out


MAX_NOTE_RULES = 2000     # notes cannot grow the tables without limit
MAX_NOTE_VOCAB = 5000
FLIP_NEEDS = 2            # a rule's right side changes only when this many different segments' notes say so


def _want(note: str) -> dict:
    """What a note should teach, after the safety filters: no rule on an everyday one-word term, no self-rules, no duplicates."""
    p = parse_note(note)
    rules, seen = [], set()
    for wrong, right in p["rules"]:
        if not wrong or wrong == right or (" " not in wrong and wrong in common_words()) or (wrong, right) in seen:
            continue
        seen.add((wrong, right))
        rules.append([wrong, right])
    vocab = []
    for t in p["vocab"] + [_strip_punct(w) for _, right in rules for w in right.split()]:
        if t and t.lower() not in common_words() and not t.isdigit() and t not in vocab:
            vocab.append(t)
    return {"rules": rules, "vocab": vocab, "wrong": list(dict.fromkeys(p["wrong"]))}


def _undo(seg_id: int, produced: dict):
    """Take back what this segment's earlier note taught."""
    flipped = {f["wrong"]: f for f in produced.get("flipped", [])}
    for wrong, right in produced.get("applied_rules", []):
        f = flipped.get(wrong)
        if f and db.one("SELECT 1 x FROM rules WHERE wrong=? AND right=?", (wrong, right)):   # this note flipped the rule: put the old answer back
            db.run("UPDATE rules SET right=?, count=? WHERE wrong=?", (f["old_right"], f["old_count"], wrong))
            for sid, rt in f["votes"]:    # the other notes that had voted for the new answer are pending again
                if sid != seg_id:
                    db.run("INSERT OR IGNORE INTO rule_pending(wrong,right,seg_id) VALUES(?,?,?)", (wrong, rt, sid))
            continue
        db.run("UPDATE rules SET count=count-1 WHERE wrong=? AND right=?", (wrong, right))
    db.run("DELETE FROM rules WHERE count<=0")
    for t in produced.get("applied_vocab", []):
        db.run("UPDATE vocab SET count=count-1 WHERE term=?", (t,))
    db.run("DELETE FROM vocab WHERE count<=0")
    db.run("DELETE FROM rule_pending WHERE seg_id=?", (seg_id,))


def learn_from_note(seg_id: int, note: str):
    """Feed one saved note into the rules / vocabulary / wrong-word list. A segment counts once per rule however often its note is saved; editing or
    deleting the note takes back what it taught. Returns what was learned, or None (setting off, nothing recognised, same result as before)."""
    on = bool(cfg.settings().get("learn_from_notes"))
    note = " ".join((note or "").split())
    prev = db.one("SELECT note,produced FROM note_learned WHERE seg_id=?", (seg_id,))
    if not on and prev is None:
        return None
    want = _want(note) if on else {"rules": [], "vocab": [], "wrong": []}
    try:
        old = json.loads(prev["produced"]) if prev and prev.get("produced") else {}
    except ValueError:
        old = {}
    if prev is not None and old.get("want") == want:       # same parsed result: nothing to do (a stray "." or space changes nothing)
        if prev["note"] != note:
            db.run("UPDATE note_learned SET note=? WHERE seg_id=?", (note, seg_id))
        return None
    if prev is None and not (want["rules"] or want["vocab"] or want["wrong"]):
        return None
    if prev is not None:
        _undo(seg_id, old)
    applied_rules, applied_vocab, conflicts, flipped = [], [], [], []
    for wrong, right in want["rules"]:
        cur = db.one("SELECT right FROM rules WHERE wrong=?", (wrong,))
        if cur is None:
            if db.one("SELECT COUNT(*) n FROM rules")["n"] >= MAX_NOTE_RULES:
                continue
            db.run("INSERT INTO rules(wrong,right,count) VALUES(?,?,1)", (wrong, right))
        elif cur["right"] == right:
            db.run("UPDATE rules SET count=count+1 WHERE wrong=?", (wrong,))
        else:    # disagrees with the rule we have: keep it until a second segment agrees with the new answer
            db.run("INSERT OR IGNORE INTO rule_pending(wrong,right,seg_id) VALUES(?,?,?)", (wrong, right, seg_id))
            if db.one("SELECT COUNT(*) n FROM rule_pending WHERE wrong=? AND right=?", (wrong, right))["n"] < FLIP_NEEDS:
                conflicts.append([wrong, cur["right"], right])
                continue
            old = db.one("SELECT right,count FROM rules WHERE wrong=?", (wrong,))
            votes = [[v["seg_id"], v["right"]] for v in db.rows("SELECT seg_id,right FROM rule_pending WHERE wrong=?", (wrong,))]
            flipped.append({"wrong": wrong, "old_right": old["right"], "old_count": old["count"], "votes": votes})    # kept so undoing this note restores the old rule
            db.run("UPDATE rules SET right=?, count=1 WHERE wrong=?", (right, wrong))
            db.run("DELETE FROM rule_pending WHERE wrong=?", (wrong,))
        applied_rules.append([wrong, right])
    for t in want["vocab"]:
        if not db.one("SELECT 1 x FROM vocab WHERE term=?", (t,)) and db.one("SELECT COUNT(*) n FROM vocab")["n"] >= MAX_NOTE_VOCAB:
            continue
        add_vocab(t, "note")
        applied_vocab.append(t)
    produced = {"want": want, "applied_rules": applied_rules, "applied_vocab": applied_vocab, "flipped": flipped}
    db.run("INSERT INTO note_learned(seg_id,note,wrong,produced) VALUES(?,?,?,?) ON CONFLICT(seg_id) DO UPDATE SET note=excluded.note, wrong=excluded.wrong, produced=excluded.produced",
           (seg_id, note, " ".join(want["wrong"]), json.dumps(produced)))
    if not (want["rules"] or want["vocab"] or want["wrong"] or conflicts):
        return None
    return {"rules": applied_rules, "vocab": applied_vocab, "wrong": want["wrong"], "conflicts": conflicts}


def note_conflicts() -> list:
    """Rules where notes disagree with what is already learned: [{wrong, kept, proposed, votes}]."""
    out = []
    for r in db.rows("SELECT wrong,right,COUNT(*) n FROM rule_pending GROUP BY wrong,right ORDER BY wrong"):
        cur = db.one("SELECT right FROM rules WHERE wrong=?", (r["wrong"],))
        out.append({"wrong": r["wrong"], "kept": cur["right"] if cur else None, "proposed": r["right"], "votes": r["n"]})
    return out


NOTE_BOOST = 3.0   # a line the reviewer flagged "wrong: word" sorts like a very unsure line


def regrade_unreviewed() -> int:
    """Re-run current rules over every segment nobody has reviewed yet. With learn_from_notes on, noted lines go first (their notes teach the rules
    the rest of the pass uses) and a line whose note names a wrong word that is really in it is pushed up the review queue."""
    on = bool(cfg.settings().get("learn_from_notes"))
    n = 0
    sql = "SELECT id,raw_words,note FROM segments WHERE status='new'" + (" ORDER BY (COALESCE(note,'')!='') DESC, id" if on else "")
    for r in db.rows(sql):
        if on and r.get("note"):
            learn_from_note(r["id"], r["note"])
        f = finalize(json.loads(r["raw_words"]))
        if on and r.get("note"):
            w = db.one("SELECT wrong FROM note_learned WHERE seg_id=?", (r["id"],))
            bad = set((w["wrong"] if w else "").split())
            if bad and any(norm(x["w"]) in bad for x in json.loads(r["raw_words"])):
                f["unsure"] = round(f["unsure"] + NOTE_BOOST, 3)
        db.run("UPDATE segments SET words=?,text=?,unsure=? WHERE id=?", (json.dumps(f["words"]), f["text"], f["unsure"], r["id"]))
        n += 1
    return n


# ---------------------------------------------------------------- learning from a correction

def learn_from_correction(raw_words: list, corrected: str) -> dict:
    raw_norm = [norm(w["w"]) for w in raw_words]
    corr_tokens = corrected.split()
    corr_norm = [norm(t) for t in corr_tokens]
    new_rules, new_vocab = [], []

    def rule(wrong, right):
        if not wrong or wrong == right:
            return
        db.run("INSERT INTO rules(wrong,right,count) VALUES(?,?,1) ON CONFLICT(wrong) DO UPDATE SET "
               "right=excluded.right, count=CASE WHEN rules.right=excluded.right THEN rules.count+1 ELSE 1 END", (wrong, right))
        new_rules.append((wrong, right))

    sm = difflib.SequenceMatcher(None, raw_norm, corr_norm, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and (i2 - i1) <= 4 and (j2 - j1) <= 4:
            right_toks = [_strip_punct(t) for t in corr_tokens[j1:j2]]
            rule(" ".join(raw_norm[i1:i2]), " ".join(right_toks))
        if op in ("replace", "insert"):
            for t in corr_tokens[j1:j2]:
                t = _strip_punct(t)
                if t and t.lower() not in common_words() and not t.isdigit():
                    add_vocab(t)
                    new_vocab.append(t)
        if op == "equal":  # case-only fixes inside the sentence (names!): "pinguino" -> "Pinguino"
            for k in range(i2 - i1):
                a, b = _strip_punct(raw_words[i1 + k]["w"]), _strip_punct(corr_tokens[j1 + k])
                if i1 + k > 0 and a != b and a.lower() == b.lower():
                    rule(raw_norm[i1 + k], b)
                    add_vocab(b)
                    new_vocab.append(b)
    return {"rules": new_rules, "vocab": new_vocab}
