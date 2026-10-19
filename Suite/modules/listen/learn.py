"""Learning from corrections: vocabulary (biases Whisper), replacement rules (fix repeat mistakes), uncertainty flags."""
import difflib
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


def regrade_unreviewed() -> int:
    """Re-run current rules over every segment nobody has reviewed yet."""
    import json
    n = 0
    for r in db.rows("SELECT id,raw_words FROM segments WHERE status='new'"):
        f = finalize(json.loads(r["raw_words"]))
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
