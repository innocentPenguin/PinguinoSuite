#!/usr/bin/env python
"""Helper unanswered questions -> Docs/HELPER_DRAFTS.md (drafts for a mod to approve).

Reads the "## Helper unanswered" section of every Docs/nightly/YYYY-MM-DD.md, groups equal questions (case, spacing and
punctuation ignored), and lists them most-asked first with an empty "Answer:" line. NOTHING goes into the knowledge pack
from here: a mod writes the answer, then moves it into Docs/HELPER_PUBLIC.md (or HELPER_MOD.md) and the nightly pack build
picks it up. Lines with a hidden secret ([hidden]) are skipped. Run: python -I Tools/helper-drafts.py
"""
import os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIGHTLY = os.path.join(ROOT, "Docs", "nightly")
OUT = os.path.join(ROOT, "Docs", "HELPER_DRAFTS.md")
LINE = re.compile(r"^- (\d\d:\d\d) ([^:\s]+): (.*?)(?: \(([^()]*)\))?$")


def norm(q):
    return re.sub(r"[^a-z0-9\u00c0-\u024f ]+", "", re.sub(r"\s+", " ", q.lower())).strip()


def main():
    groups = collections.OrderedDict()
    if os.path.isdir(NIGHTLY):
        for name in sorted(os.listdir(NIGHTLY)):
            if not re.match(r"\d{4}-\d\d-\d\d\.md$", name):
                continue
            day = name[:-3]
            with open(os.path.join(NIGHTLY, name), encoding="utf-8") as f:
                text = f.read().replace("\r\n", "\n")
            m = re.search(r"^## Helper unanswered\n(.*?)(?=^## |\Z)", text, re.S | re.M)
            if not m:
                continue
            for ln in m.group(1).splitlines():
                lm = LINE.match(ln.strip())
                if not lm or "[hidden]" in ln:
                    continue
                key = norm(lm.group(3))
                if len(key) < 6:
                    continue
                g = groups.setdefault(key, {"q": lm.group(3), "n": 0, "users": set(), "last": day, "why": lm.group(4) or ""})
                g["n"] += 1
                g["users"].add(lm.group(2))
                g["last"] = day
    rows = sorted(groups.values(), key=lambda g: (-g["n"], g["last"]), reverse=False)
    out = ["# Helper drafts (unanswered questions)", "",
           "Made by `Tools/helper-drafts.py` from the nightly logs. A mod fills in `Answer:`, then moves the entry into `Docs/HELPER_PUBLIC.md` (or `HELPER_MOD.md`) as a `## Title` section; the nightly pack build picks it up. Nothing here is in the knowledge pack.", ""]
    if not rows:
        out.append("_No unanswered questions in the nightly logs._")
    for g in rows:
        out += ["## " + g["q"][:90], "- asked %d time(s) by %d viewer(s), last %s%s" % (g["n"], len(g["users"]), g["last"], (" (" + g["why"] + ")") if g["why"] else ""), "- Answer: ", ""]
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print("wrote %s (%d question(s))" % (os.path.relpath(OUT, ROOT), len(rows)))


if __name__ == "__main__":
    sys.exit(main())
