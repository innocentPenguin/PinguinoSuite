"""Soak test on a throwaway Multi (port 8797, temp data dir, no network/keyring): ~50 msgs/s of mixed chat + events through /api/dev/inject
(the real pipeline), a websocket client draining the hub, and a sampler for RSS / CPU / queue / cards / latency / console errors.
Run:  ..\\..\\.venv\\Scripts\\python.exe tests\\soak.py [seconds=240] [rate=50]      -> prints a markdown report"""
import asyncio
import ctypes
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[1]
import socket


def _free_port(pref=8797):
    for port in [pref] + list(range(8780, 8796)):
        with socket.socket() as sk:
            if sk.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("no free port")


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 240
RATE = int(sys.argv[2]) if len(sys.argv) > 2 else 50


def http(method, path, body=None, timeout=15):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"content-type": "application/json", "origin": BASE})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return json.loads(data or b"null"), (time.perf_counter() - t) * 1000


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def listener_pid(port):
    """venv python.exe is a launcher stub: the real server is whoever listens on the port."""
    out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        p = ln.split()
        if len(p) >= 5 and p[1].endswith(f":{port}") and p[3] == "LISTENING":
            return int(p[4])
    return None


def proc_stats(pid):
    k, p = ctypes.windll.kernel32, ctypes.windll.psapi
    h = k.OpenProcess(0x1000 | 0x0010, False, pid)           # QUERY_LIMITED_INFORMATION | VM_READ
    try:
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        p.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
        c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
        k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
        cpu = ((kt.dwHighDateTime << 32 | kt.dwLowDateTime) + (ut.dwHighDateTime << 32 | ut.dwLowDateTime)) / 1e7
        return pmc.WorkingSetSize / 1048576, cpu
    finally:
        k.CloseHandle(h)


EMOTES = [{"id": "25", "text": "Kappa"}, {"id": "354", "text": "4Head"}, {"id": "86", "text": "BibleThump"}]
WORDS = "hello chat nice play lol gg wow song music game boss run clip raid sub hype pog the a is this that when how".split()
UNI = ["こんにちは配信ありがとう", "🔥🔥🔥 let's goooo 🐧", "Привет, стример!", "مرحبا بالجميع", "ñandú café ☕ naïve", "‮RTL override test", "zalgo t̸̢̛e̶̛s̷t̷"]
QUESTIONS = ["@pingu what game is this?", "how long have you been streaming?", "pingu can you play X next?", "is the giveaway still open?"]
EVENTS = [("follow", 0), ("sub", 1), ("resub", 6), ("gift", 5), ("cheer", 100), ("raid", 40)]
sent = {"n": 0, "err": 0}
lat = []


def make(i, rnd):
    r = rnd.random()
    user = f"viewer{rnd.randint(1, 3000)}"
    b = {"user": user, "id": f"soak:{i}"}
    if r < 0.60:
        b["text"] = " ".join(rnd.choices(WORDS, k=rnd.randint(1, 12)))
    elif r < 0.68:
        b["text"] = "Kappa " + " ".join(rnd.choices(WORDS, k=3)) + " 4Head"; b["emotes"] = EMOTES
    elif r < 0.73:
        b["text"] = ("long message " * 60)[:500]
    elif r < 0.78:
        b["text"] = rnd.choice(UNI)
    elif r < 0.84:
        b["text"] = "SPAM SPAM SPAM buy followers"; b["user"] = f"spammer{rnd.randint(1, 5)}"; b["id"] = f"soak:{i}"
    elif r < 0.90:
        b["text"] = rnd.choice(QUESTIONS)
    elif r < 0.93:
        b["text"] = rnd.choice(["", " ", "\n", "a" * 2000])
    else:
        ev, amt = rnd.choice(EVENTS)
        b.update(event=ev, amount=amt, text=f"{user} {ev}")
    if r > 0.5 and rnd.random() < 0.3:
        b["platform"] = rnd.choice(["youtube", "kick", "tiktok"])
    return b


def feeder(stop, idx, nthreads):
    rnd, i, per = random.Random(idx), idx, RATE / nthreads
    nxt = time.perf_counter()
    while not stop.is_set():
        try:
            http("POST", "/api/dev/inject", make(i, rnd), timeout=10)
            sent["n"] += 1
        except Exception:
            sent["err"] += 1
        i += nthreads
        nxt += 1 / per
        d = nxt - time.perf_counter()
        if d > 0:
            time.sleep(d)
        else:
            nxt = time.perf_counter()


async def ws_drain(stop, counter):
    try:
        import websockets
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=BASE, max_size=2 ** 24) as ws:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(ws.recv(), 1)
                    counter["ws"] = counter.get("ws", 0) + 1
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        counter["ws_err"] = str(e)[:100]


def main():
    tmp = tempfile.mkdtemp(prefix="multi_soak_")
    env = dict(os.environ, MULTI_PORT=str(PORT), PINGUINO_DATA_DIR=tmp, PINGUINO_CORE_URL="http://127.0.0.1:1", MULTI_NO_KEYRING="1", MULTI_NO_SEND="1")
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows, counter, stop = [], {}, threading.Event()
    try:
        for _ in range(60):
            try:
                http("GET", "/api/status", timeout=1); break
            except Exception:
                time.sleep(0.5)
        try:
            http("POST", "/api/settings", {"my_names": ["pingu"]})
        except Exception:
            pass
        threading.Thread(target=lambda: asyncio.run(ws_drain(stop, counter)), daemon=True).start()
        n = 4
        for k in range(n):
            threading.Thread(target=feeder, args=(stop, k, n), daemon=True).start()
        t0 = time.time()
        spid = listener_pid(PORT) or proc.pid
        r0, c0 = proc_stats(spid)
        lastc, lastt = c0, t0
        while time.time() - t0 < SECS:
            time.sleep(10)
            try:
                rss, cpu = proc_stats(spid)
                st, _ = http("GET", "/api/status")
                cards, cl = http("GET", "/api/cards")
                _, ml = http("GET", "/api/messages?limit=200")
                _, sl = http("GET", "/api/search?q=hello")
                now = time.time()
                rows.append(dict(t=int(now - t0), rss=rss, cpu=(cpu - lastc) / (now - lastt) * 100, sent=sent["n"], queue=st["queue"], stats=st["stats"],
                                 open=len(cards["open"]), missed=len(cards["missed"]), cards_ms=cl, msgs_ms=ml, search_ms=sl, ws=counter.get("ws", 0)))
                lastc, lastt = cpu, now
                print(rows[-1], flush=True)
            except Exception as e:
                rows.append(dict(t=int(time.time() - t0), error=str(e)[:100]))
                print("sample error", e, flush=True)
        stop.set()
        time.sleep(3)
        try:
            fin, _ = http("GET", "/api/status")
        except Exception as e:
            fin = {"error": str(e)}
        errs = []
        cf = pathlib.Path(tmp) / "console" / "multi.jsonl"
        if cf.exists():
            errs = [json.loads(x) for x in cf.read_text(encoding="utf-8").splitlines() if x.strip()]
        errs = [e for e in errs if e.get("level") in ("warn", "error")]
        dbsz = (pathlib.Path(tmp) / "multi" / "multi.db").stat().st_size / 1048576 if (pathlib.Path(tmp) / "multi" / "multi.db").exists() else 0
        report(rows, fin, errs, dbsz)
    finally:
        stop.set()
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def report(rows, fin, errs, dbsz):
    ok = [r for r in rows if "rss" in r]
    print("\n| t(s) | RSS MB | CPU % | sent | queue | in | dropped | open cards | missed | /api/cards ms | /api/messages ms | search ms |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ok:
        print(f"| {r['t']} | {r['rss']:.0f} | {r['cpu']:.0f} | {r['sent']} | {r['queue']} | {r['stats']['in']} | {r['stats']['dropped']} | {r['open']} | {r['missed']} | {r['cards_ms']:.0f} | {r['msgs_ms']:.0f} | {r['search_ms']:.0f} |")
    print(f"\nfinal status: {json.dumps(fin)[:300]}\nsend errors: {sent['err']}  db: {dbsz:.1f} MB  console warn/error lines: {len(errs)}")
    for e in errs[:15]:
        print("  ", e.get("level"), e.get("source"), str(e.get("msg"))[:160])


if __name__ == "__main__":
    main()
