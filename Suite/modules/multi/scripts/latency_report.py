"""Read-only: message latency per platform from a COPY of multi.db (never open the live file; copy multi.db, multi.db-wal and multi.db-shm together).
Usage: python scripts/latency_report.py <copy-of-multi.db> [--since <epoch>]
latency = meta.recv - ts  (recv is stamped by Pipeline.ingest; ts is the source time on YouTube, the receive time elsewhere, so only
connectors that store a source time (YouTube, Twitch meta.src) give a true delay; the rest show ~0)."""
import json
import sqlite3
import statistics
import sys


def report(path, since=0.0):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    lat, nostamp = {}, {}
    for plat, ts, js in db.execute("select platform, ts, json from messages where ts >= ?", (since,)):
        meta = json.loads(js).get("meta") or {}
        if "recv" not in meta:
            nostamp[plat] = nostamp.get(plat, 0) + 1
            continue
        src = float(meta.get("src") or ts)
        lat.setdefault(plat, []).append(max(0.0, float(meta["recv"]) - src))
    out = {}
    for plat, v in sorted(lat.items()):
        v.sort()
        out[plat] = {"n": len(v), "median_s": round(statistics.median(v), 2), "p95_s": round(v[int(0.95 * (len(v) - 1))], 2), "max_s": round(v[-1], 2),
                     "without_stamp": nostamp.get(plat, 0)}
    for plat, n in nostamp.items():
        out.setdefault(plat, {"n": 0, "without_stamp": n})
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    since = float(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else 0.0
    for plat, r in report(sys.argv[1], since).items():
        print(plat, r)
