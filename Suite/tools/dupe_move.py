"""Move (never delete) redundant byte-identical copies out of a data folder into ONE review folder, with a MANIFEST and a restore script.
Same-drive rename only: nothing is copied or removed, and a move back puts every file exactly where it was.
Usage: python dupe_move.py DATA_DIR DEST_DIR [--ref STEM ...] [--ref-file FILE] [--busy-minutes 5] [--apply]
Without --apply it only prints the plan. A copy is skipped when its file name stem is in --ref (something references it), it was written to
in the last --busy-minutes, or it cannot be opened for writing (another process holds it)."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dupe_report import find_groups, sha256  # noqa: E402

RESTORE = '''"""Put every file listed in MANIFEST.json back where it came from. Usage: python restore.py [--dry-run]"""
import json
import os
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
items = json.loads((here / "MANIFEST.json").read_text("utf-8"))["moved"]
dry = "--dry-run" in sys.argv
back = skipped = 0
for it in items:
    src, dst = Path(it["moved"]), Path(it["original"])
    if not src.exists():
        print("missing, skipped:", src)
        skipped += 1
    elif dst.exists():
        print("original path already exists, skipped:", dst)
        skipped += 1
    else:
        if not dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
        back += 1
print(("would restore" if dry else "restored"), back, "file(s);", skipped, "skipped")
'''


def busy(p, minutes):
    if time.time() - p.stat().st_mtime < minutes * 60:
        return "written in the last %g min" % minutes
    try:
        with open(p, "r+b"):
            pass
    except OSError:
        return "held open by another process"
    return ""


def plan(data_dir, refs=(), busy_minutes=5, exts=(".mp4",)):
    data_dir = Path(data_dir)
    refs = set(refs)
    keep, move, skipped = [], [], []
    for size, paths in find_groups(data_dir, exts):
        paths = sorted(paths, key=lambda p: (p.stem not in refs, p.stat().st_mtime, str(p)))   # referenced first, then oldest
        keeper = paths[0]
        keep.append((keeper, size))
        for p in paths[1:]:
            why = "referenced" if p.stem in refs else busy(p, busy_minutes)
            (skipped if why else move).append((p, keeper, size, why))
    return keep, move, skipped


def apply(data_dir, dest, move):
    data_dir, dest = Path(data_dir).resolve(), Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for p, keeper, size, _ in move:
        if p.stat().st_size != size:
            continue
        digest = sha256(p)
        p, keeper = p.resolve(), keeper.resolve()
        target = dest / p.relative_to(data_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(p, target)       # same-drive rename; raises if the drive differs rather than silently copying
        moved.append({"original": str(p), "moved": str(target), "size": size, "sha256": digest, "duplicates": str(keeper)})
    (dest / "MANIFEST.json").write_text(json.dumps({"created": time.strftime("%Y-%m-%d %H:%M:%S"), "moved": moved}, indent=1), "utf-8")
    (dest / "MANIFEST.txt").write_text("".join(f"{m['original']}\t->\t{m['moved']}\t{m['size']}\t{m['sha256']}\tduplicate of {m['duplicates']}\n" for m in moved), "utf-8")
    (dest / "restore.py").write_text(RESTORE, "utf-8")
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("dest")
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument("--ref-file")
    ap.add_argument("--busy-minutes", type=float, default=5)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    refs = list(a.ref)
    if a.ref_file:
        refs += [x.strip() for x in Path(a.ref_file).read_text("utf-8").splitlines() if x.strip()]
    if os.path.splitdrive(os.path.abspath(a.data_dir))[0].lower() != os.path.splitdrive(os.path.abspath(a.dest))[0].lower():
        sys.exit("data and destination are on different drives: a move would copy. Refusing.")
    keep, move, skipped = plan(a.data_dir, refs, a.busy_minutes)
    for k, size in keep:
        print("KEEP ", k)
    for p, k, size, _ in move:
        print("MOVE ", p, "(dup of", k.name + ")")
    for p, k, size, why in skipped:
        print("SKIP ", p, "-", why)
    print(f"{len(move)} to move ({sum(m[2] for m in move) / 1024 ** 3:.2f} GB), {len(skipped)} skipped, {len(keep)} kept")
    if a.apply:
        done = apply(a.data_dir, a.dest, move)
        print("moved", len(done), "->", a.dest)


if __name__ == "__main__":
    main()
