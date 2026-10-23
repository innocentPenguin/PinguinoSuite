"""READ-ONLY Listen quality trend: word error rate of the ASR text against the human-corrected text, per day and overall.
Opens a COPY of ears.db in a temp folder (the real database is never opened for writing and nothing is written under Data/).
Usage: python wer_report.py [listen_data_dir] [-o report.md]

Definitions
- reviewed line: segments.status in (approved, corrected). Human text = corrected_text, or the shown text when the line was approved as it was.
- WER(raw) = word edit distance between the ASR output (raw_text) and the human text / human word count.
- WER(shown) = same for the text the reviewer actually saw (text = ASR after the learned rules and vocab), so WER(raw) - WER(shown) is what learning already fixes.
- day = the day the line was transcribed (segments.created); gold.jsonl has no timestamps, so it is used for the overall cross-check only.
- repeat rate: a fix is a one-word or phrase substitution (a -> b) found in a corrected line. After the first time a fix was made, every later line whose ASR
  text contains `a` is an opportunity; it is a repeat when the shown text still has `a` (the rule did not stop the same mistake), and prevented when it shows `b`."""
import argparse
import difflib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

COMMON = 0.02   # a wrong phrase found in more than 2% of all lines is too common to count as a repeat
WORD = re.compile(r"[a-z0-9']+")


def words(t):
    return WORD.findall((t or "").lower())


def edit_distance(a, b):
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def fixes(raw, human):
    """[(wrong, right)] phrase pairs between two word lists (replacements, plus deletions as (w, '') and insertions as ('', w))."""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, raw, human, autojunk=False).get_opcodes():
        if op != "equal":
            out.append((" ".join(raw[i1:i2]), " ".join(human[j1:j2])))
    return out


def open_copy(data_dir):
    """Copy ears.db (and its WAL) to a temp folder and open the copy read-only."""
    src = Path(data_dir) / "ears.db"
    tmp = Path(tempfile.mkdtemp(prefix="wer-"))
    shutil.copy2(src, tmp / "ears.db")
    for ext in ("-wal",):
        w = Path(str(src) + ext)
        if w.exists():
            shutil.copy2(w, tmp / ("ears.db" + ext))
    c = sqlite3.connect(f"file:{(tmp / 'ears.db').as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c, tmp


def load(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(segments)")}
    note = "note" if "note" in cols else "NULL"
    rows = conn.execute(f"SELECT id, created, raw_text, text, corrected_text, status, {note} AS note FROM segments ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def analyse(rows, gold=None, top=20):
    reviewed = [r for r in rows if r["status"] in ("approved", "corrected")]
    per_day = defaultdict(lambda: [0, 0, 0, 0])   # lines, human words, errors raw, errors shown
    tot = [0, 0, 0]
    cnt = Counter()
    notes = sum(1 for r in reviewed if (r["note"] or "").strip())
    corrected = []
    for r in reviewed:
        human = words(r["corrected_text"] if r["status"] == "corrected" and r["corrected_text"] else r["text"])
        raw, shown = words(r["raw_text"]), words(r["text"])
        er, es = edit_distance(raw, human), edit_distance(shown, human)
        day = time.strftime("%Y-%m-%d", time.localtime(r["created"] or 0))
        d = per_day[day]
        d[0] += 1; d[1] += len(human); d[2] += er; d[3] += es
        tot[0] += len(human); tot[1] += er; tot[2] += es
        if r["status"] == "corrected":
            corrected.append((r, raw, shown, human))
            for a, b in fixes(raw, human):
                cnt[(a, b)] += 1
    # repeat rate
    first_seen = {}
    repeats = prevented = recurring = 0
    for r, raw, shown, human in corrected:
        for a, b in set(fixes(raw, human)):
            if not a:
                continue
            if (a, b) in first_seen:
                recurring += 1
            else:
                first_seen[(a, b)] = r["id"]
    # opportunities after the fix existed: every later line (reviewed or not) whose ASR text contains the wrong phrase
    norm = [(r["id"], f" {' '.join(words(r['raw_text']))} ", f" {' '.join(words(r['text']))} ") for r in rows]
    for (a, b), fid in first_seen.items():
        pat = f" {a} "
        if len(norm) >= 200 and sum(1 for _, rawn, _ in norm if pat in rawn) > COMMON * len(norm):
            continue   # "the", "a", "have"...: appears everywhere, so a later hit says nothing about this fix
        for rid, rawn, s in norm:
            if rid <= fid:
                continue
            if pat in rawn:
                if pat in s:
                    repeats += 1
                elif b and f" {b} " in s:
                    prevented += 1
    opp = repeats + prevented
    g = None
    if gold:
        gl, ge = 0, [0, 0]
        for e in gold:
            if e.get("status") not in ("approved", "corrected"):
                continue
            h = words(e.get("text"))
            gl += 1; ge[0] += len(h); ge[1] += edit_distance(words(e.get("raw")), h)
        g = {"lines": gl, "words": ge[0], "wer": (ge[1] / ge[0]) if ge[0] else None}
    return {
        "all_lines": len(rows), "reviewed": len(reviewed), "corrected": len(corrected), "approved": len(reviewed) - len(corrected),
        "words": tot[0], "wer_raw": tot[1] / tot[0] if tot[0] else None, "wer_shown": tot[2] / tot[0] if tot[0] else None,
        "notes": notes, "notes_share": notes / len(reviewed) if reviewed else None,
        "per_day": {k: {"lines": v[0], "words": v[1], "wer_raw": v[2] / v[1] if v[1] else None, "wer_shown": v[3] / v[1] if v[1] else None} for k, v in sorted(per_day.items())},
        "top": cnt.most_common(top), "fix_pairs": len(first_seen), "recurring_fixes": recurring,
        "opportunities": opp, "repeats": repeats, "prevented": prevented, "repeat_rate": repeats / opp if opp else None, "gold": g,
    }


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render(a, source=""):
    o = [f"# Listen quality report (read-only)", "", f"Source: {source}", ""]
    o += ["## Key numbers",
          f"1. Reviewed lines: **{a['reviewed']}** of {a['all_lines']} ({a['corrected']} corrected, {a['approved']} approved as they were)",
          f"2. WER of the raw ASR text vs the human text: **{pct(a['wer_raw'])}** over {a['words']} human words",
          f"3. WER of the text the reviewer saw (after learned rules/vocab): **{pct(a['wer_shown'])}**",
          f"4. Share of reviewed lines with a note: **{pct(a['notes_share'])}** ({a['notes']})",
          f"5. Same fix made again by a human: **{a['recurring_fixes']}** of {a['fix_pairs']} distinct fixes. Upper bound for a learned fix failing to stop the same ASR phrase: **{pct(a['repeat_rate'])}** ({a['repeats']} later lines still show the phrase vs {a['prevented']} showing the fix; includes lines where the phrase was right, so only meaningful once many fixes repeat)", ""]
    if a["gold"]:
        g = a["gold"]
        o += [f"Cross-check from gold.jsonl: {g['lines']} reviewed entries, WER raw vs human {pct(g['wer'])}", ""]
    o += ["## Per day (by the day the line was transcribed)", "", "| day | reviewed lines | words | WER raw | WER shown |", "|---|---|---|---|---|"]
    o += [f"| {d} | {v['lines']} | {v['words']} | {pct(v['wer_raw'])} | {pct(v['wer_shown'])} |" for d, v in a["per_day"].items()]
    o += ["", "## Most corrected words / phrases (ASR said -> human wrote)", "", "| count | ASR | human |", "|---|---|---|"]
    o += [f"| {n} | {x or '(nothing)'} | {y or '(deleted)'} |" for (x, y), n in a["top"]]
    return "\n".join(o) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default=str(Path(__file__).resolve().parents[1] / "modules" / "listen" / "data"))
    ap.add_argument("-o", "--out")
    ns = ap.parse_args(argv)
    root = Path(ns.data_dir)
    if not (root / "ears.db").is_file():
        print(f"no ears.db in {root}", file=sys.stderr)
        return 2
    conn, tmp = open_copy(root)
    try:
        rows = load(conn)
    finally:
        conn.close()
        shutil.rmtree(tmp, ignore_errors=True)
    gold = None
    gp = root / "gold.jsonl"
    if gp.is_file():
        gold = []
        for line in gp.read_text("utf8", errors="replace").splitlines():
            try:
                gold.append(json.loads(line))
            except ValueError:
                pass
    text = render(analyse(rows, gold), str(root))
    if ns.out:
        Path(ns.out).write_text(text, "utf8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
