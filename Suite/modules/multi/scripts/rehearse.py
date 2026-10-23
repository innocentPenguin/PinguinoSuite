"""Full-Host rehearsal on a THROWAWAY database: Multi runs in this process next to scripts/fake_host.py, every Host path fires at once,
and a recorder wraps the alert engine's emit so we can check queue order, duplicates, stalls and the editor log afterwards.
Nothing leaves this PC (no chat, no OBS, no platform). Run:  python scripts/rehearse.py [--seconds 300]  -> prints a report and exits 1 on a problem."""
import argparse
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="rehearse_"))
PORT, HPORT = 8788, 8793
os.environ.update(MULTI_PORT=str(PORT), MULTI_DB=str(tmp / "r.db"), CORE_URL="http://127.0.0.1:1", MULTI_HOST_URL=f"http://127.0.0.1:{HPORT}",
                  MULTI_CLIP_EXTRA_HOSTS=f"127.0.0.1:{HPORT}")
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.chdir(ROOT)
import fake_host  # noqa: E402
import server  # noqa: E402
import uvicorn  # noqa: E402
from models import ChatMessage  # noqa: E402

BASE = f"http://127.0.0.1:{PORT}"
rec = []                                                # (t, event) for alert.show / alert.end
t0 = time.time()


class Srv(ThreadingHTTPServer):
    request_queue_size = 128                            # a raid brings many first messages at once; the stdlib default backlog of 5 refuses some


def host_start():
    fake_host.H.log_message = lambda *a, **k: None
    s = Srv(("127.0.0.1", HPORT), fake_host.H)
    s.handle_error = lambda *a: None                    # the slow-viewer case makes Multi hang up first: not a failure
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def call(method, path, body=None):
    r = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Origin": BASE, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=10) as x:
        return json.loads(x.read().decode() or "{}")


def fire(**b):
    return call("POST", "/api/alerts/fire", b)


def chat(uid, text="hello chat", first=True):
    m = ChatMessage(id=f"twitch:rehearse:{uid}-{time.time()}", platform="twitch", channel="rehearse", user_id=uid, user=uid, display=uid, text=text, ts=time.time(), first_time=first)
    server.hub.loop.call_soon_threadsafe(server.inbox.put, m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=300)
    a = ap.parse_args()
    hs = host_start()
    orig = server.alert_engine.emit

    def spy(ev):
        if ev.get("type") in ("alert.show", "alert.end"):
            rec.append((time.time() - t0, dict(ev)))
        return orig(ev)
    server.alert_engine.emit = spy
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        try:
            call("GET", "/api/status")
            break
        except Exception:
            time.sleep(0.2)
    problems = []
    eng = server.alert_engine

    # A. priority ordering: hold the queue, submit a mixed burst, release
    server.hub.loop.call_soon_threadsafe(setattr, eng, "paused", True)
    time.sleep(0.3)
    order_in = ["follow", "tip", "raid", "sub", "follow", "gift", "cheer"]
    for i, t in enumerate(order_in):
        fire(type=t, user=f"burst{i}", id=f"burst-{i}", amount=5 + i)
    time.sleep(0.3)
    server.hub.loop.call_soon_threadsafe(setattr, eng, "paused", False)
    server.hub.loop.call_soon_threadsafe(eng.wake.set)

    # B. every Host path at once
    for uid in ("viewer_ok", "pending_one", "link_one", "long_one", "err_one", "slow_one"):
        chat(uid)
    chat("viewer_ok", "second message")                 # same viewer again: no second intro
    clip = f"http://127.0.0.1:{HPORT}/clip.webm"
    fire(type="shoutout", user="penguin_a", id="so-ok", message="go follow them", clip={"url": clip, "duration_s": 8})
    fire(type="shoutout", user="penguin_b", id="so-mkv", message="mkv clip", clip={"url": f"http://127.0.0.1:{HPORT}/clip.mkv", "duration_s": 8})
    fire(type="shoutout", user="penguin_c", id="so-bad", message="bad host", clip={"url": "https://evil.example/x.mp4", "duration_s": 8})
    fire(type="hype_start", user="", id="h-start", level=1, progress=10, goal=100, total=10)
    fire(type="hype_level", user="", id="h-l2", level=2, progress=40, goal=100, total=200)
    fire(type="hype_end", user="", id="h-end", level=2, progress=100, goal=100, total=500)
    fire(type="tip", user="generous", id="tip-1", amount=15, currency="USD", message="thanks!")
    fire(type="gamble_win", user="lucky", id="gw-1", amount=5000)
    fire(type="shop", user="buyer", id="shop-1", message="Hydrate reminder")
    fire(type="guess", user="guesser", id="guess-1", message="Got it right")
    r_loan = fire(type="loan", user="debtor", id="loan-1", amount=100)
    r_give = fire(type="give", user="giver", id="give-1", amount=20)
    for i in range(12):
        fire(type="follow", user=f"flood{i}", id=f"flood-{i}")
    fire(type="tip", user="generous", id="tip-1", amount=15)      # repeated id: must not play twice
    fire(type="no_such_type", user="odd", id="odd-1", message="from the Host")

    # C. Host goes down mid-run: new viewers get no intro, nothing stalls; it comes back later
    time.sleep(20)
    hs.shutdown()
    hs.server_close()
    chat("while_down_1")
    chat("while_down_2")
    t_end = time.time() + a.seconds
    time.sleep(15)
    hs = host_start()
    chat("after_back")
    fire(type="follow", user="late", id="late-1")
    time.sleep(65)
    chat("while_down_1", "I am back", first=False)         # their first message met a dead Host: the retry must play the intro now
    chat("err_one", "again", first=False)                   # Host answered 500 the first time: retried, still 500 -> never plays
    time.sleep(5)
    while time.time() < t_end and (eng.heap or eng.current):
        time.sleep(2)
    time.sleep(3)

    shows = [(t, e["alert"]) for t, e in rec if e["type"] == "alert.show"]
    ends = [(t, e["id"]) for t, e in rec if e["type"] == "alert.end"]
    ids = [p["id"] for _, p in shows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    print(f"\nrehearsal finished after {time.time() - t0:.0f}s  shows={len(shows)} ends={len(ends)} queue_left={len(eng.heap)} current={bool(eng.current)}")
    for t, p in shows:
        print(f"  {t:6.1f}  {p['type']:<14} {str(p.get('user') or '')[:16]:<16} id={p['id'][:28]}")
    print("burst order:", [p["type"] for _, p in shows[:len(order_in)]])
    if dup:
        problems.append(f"alert ids shown twice: {dup}")
    if len(ends) != len(shows):
        problems.append(f"{len(shows)} shows but {len(ends)} ends")
    if eng.heap or eng.current:
        problems.append("queue did not drain")
    gaps = [shows[i + 1][0] - ends[i][0] - shows[i + 1][1].get("pre_ms", 0) / 1000 for i in range(min(len(shows) - 1, len(ends)))]   # a shoutout may wait its own "delay before it plays"
    if gaps and max(gaps) > 6:
        problems.append(f"largest wait between an end and the next show was {max(gaps):.1f}s")
    users = [p.get("user") for _, p in shows]
    for u in ("viewer_ok", "penguin_a", "penguin_b", "generous", "lucky", "buyer", "guesser", "after_back", "while_down_1"):
        if users.count(u) != 1:
            problems.append(f"{u}: shown {users.count(u)}x, wanted 1")
    for u in ("pending_one", "link_one", "long_one", "err_one", "while_down_2", "debtor", "giver"):
        if u in users:
            problems.append(f"{u} must NOT have played")
    by = {p["id"]: p for _, p in shows}
    if not (by.get("so-ok", {}).get("clip") or {}).get("url") or not (by.get("so-mkv", {}).get("clip") or {}).get("url"):
        problems.append("shoutout with a playable-host clip lost its clip")
    if by.get("so-bad", {}).get("clip"):
        problems.append("shoutout from a disallowed clip host kept the clip")
    if r_loan.get("queued") or r_give.get("queued"):
        problems.append(f"loan/give should be refused as disabled: {r_loan} {r_give}")
    it = server.pipeline.intros
    print("intros:", it.stats, "retry:", sorted(it.retry), "played:", sorted(it.played), "miss:", sorted(it.miss), "pipeline:", server.pipeline.stats)
    print("slow_one shown:", "slow_one" in users, "| odd->custom shown:", "odd" in users)
    print("hype shows:", [p["type"] for _, p in shows if p["type"].startswith("hype")])
    c = Counter((e["type"], e["status"], e["why"][:30]) for e in list(eng.log))
    print("editor log:")
    for k, v in sorted(c.items()):
        print("  ", k, v)
    print("host-status:", call("GET", "/api/host-status"))
    print("\n".join(["PROBLEMS:"] + problems) if problems else "no problems found")
    sys.stdout.flush()
    os._exit(1 if problems else 0)


if __name__ == "__main__":
    main()
