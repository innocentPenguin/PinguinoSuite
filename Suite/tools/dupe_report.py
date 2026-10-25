"""READ-ONLY duplicate video report for the Listen data folder. Never deletes, moves or writes inside the data folder.
Groups files by size first, then confirms with sha256 only for files whose size matches another file's.
Usage: python dupe_report.py [data_dir] [-o report.md] [--ext .mp4,.mkv,.webm]"""
import argparse
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path


def sha256(p, chunk=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_groups(root, exts=(".mp4",), hasher=sha256):
    """-> list of (size, [paths]) for byte-identical files, biggest reclaimable first."""
    by_size = defaultdict(list)
    for dirpath, _, names in os.walk(root):
        for n in names:
            if n.lower().endswith(tuple(exts)):
                p = Path(dirpath) / n
                try:
                    by_size[p.stat().st_size].append(p)
                except OSError:
                    pass
    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2 or size == 0:
            continue
        by_hash = defaultdict(list)
        for p in paths:
            try:
                by_hash[hasher(p)].append(p)
            except OSError:
                pass
        groups += [(size, sorted(v)) for v in by_hash.values() if len(v) > 1]
    return sorted(groups, key=lambda g: -g[0] * (len(g[1]) - 1))


def gb(n):
    return f"{n / 1024 ** 3:.2f} GB"


def render(root, groups):
    total = sum(s * (len(v) - 1) for s, v in groups)
    out = [f"# Duplicate video report (read-only)", "", f"Folder: `{root}`", f"Duplicate groups: {len(groups)}  |  files that are copies: {sum(len(v) - 1 for _, v in groups)}  |  **reclaimable: {gb(total)}**", "",
           "Nothing was deleted or moved. Keep one file per group; check that no database row points at a copy before removing it.", ""]
    for i, (size, v) in enumerate(groups, 1):
        out.append(f"## {i}. {gb(size)} x {len(v)} (reclaim {gb(size * (len(v) - 1))})")
        out += [f"- `{p}`" for p in v]
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default=str(Path(__file__).resolve().parents[1] / "modules" / "listen" / "data"))
    ap.add_argument("-o", "--out")
    ap.add_argument("--ext", default=".mp4")
    a = ap.parse_args(argv)
    root = Path(a.data_dir)
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 2
    groups = find_groups(root, tuple(e.strip().lower() for e in a.ext.split(",")))
    text = render(root, groups)
    if a.out:
        Path(a.out).write_text(text, "utf8")
    print(text if not a.out else f"{len(groups)} groups, reclaimable {gb(sum(s * (len(v) - 1) for s, v in groups))} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "suite"))
    import safetext  # a bell character in a file name or chat line must not beep the console
    safetext.install()
    sys.exit(main())
