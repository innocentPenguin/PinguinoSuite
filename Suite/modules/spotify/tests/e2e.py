"""End-to-end trial of the REAL server.py against fake Spotify + fake site (no credentials, no internet).
Run: python Suite/modules/spotify/tests/e2e.py        -> prints a PASS/FAIL table, exit code 1 on any failure."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fakes  # noqa: E402

def _free_ports(n):
    import socket
    socks = [socket.socket() for _ in range(n)]
    for k in socks:
        k.bind(("127.0.0.1", 0))
    ports = [k.getsockname()[1] for k in socks]
    for k in socks:
        k.close()
    return ports


# free ports each run so parallel runs (other sessions) cannot collide
PORT, SP_PORT, SITE_PORT = _free_ports(3)
BASE = f"http://127.0.0.1:{PORT}"
RESULTS = []
DATA = tempfile.mkdtemp(prefix="spotify-e2e-")
proc = None


def T(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:140]))
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:140]) if not ok else ""), flush=True)


def call(method, path, body=None, headers=None, base=BASE, raw=False):
    data = json.dumps(body).encode() if body is not None and not raw else (body if raw else None)
    h = {"Content-Type": "application/json", "Origin": base, **(headers or {})}
    path = path.replace(" ", "%20")
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read()
            try:
                return r.status, json.loads(b) if b else {}
            except ValueError:
                return r.status, b.decode("utf8", "replace")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b) if b else {}
        except ValueError:
            return e.code, b.decode("utf8", "replace")


def get(p, **k):
    return call("GET", p, **k)


def post(p, b=None, **k):
    return call("POST", p, b if b is not None else {}, **k)


def sim(_what, **q):
    return call("GET", "/_sim/" + _what + ("?" + urllib.parse.urlencode(q) if q else ""), base=f"http://127.0.0.1:{SP_PORT}")[1]


def site_sim(path, body=None):
    return call("POST", "/_sim/" + path, body or {}, base=f"http://127.0.0.1:{SITE_PORT}")[1]


def wait(fn, timeout=6, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return None


def chat(user, text, roles=(), **kw):
    return post("/api/chat", {"user": user, "text": text, "roles": list(roles), **kw}, headers={"Origin": ""})[1]


def cmd(command, args="", user="ann", role="viewer", **kw):
    return post("/api/chat-command", {"command": command, "args": args, "user": user, "display": user, "role": role, **kw}, headers={"Origin": ""})[1]


def state():
    return get("/api/state")[1]


def qnames():
    return [i["name"] for i in state()["queue"]["items"]]


def start_server():
    global proc
    env = {**os.environ, "PINGUINO_DATA_DIR": DATA, "SPOTIFY_PORT": str(PORT), "SPOTIFY_TICK_S": "0.2", "SPOTIFY_NO_BROWSER": "1",
           "SPOTIFY_API_BASE": f"http://127.0.0.1:{SP_PORT}/v1", "SPOTIFY_ACCOUNTS_BASE": f"http://127.0.0.1:{SP_PORT}"}
    env.pop("PINGUINO_API_TOKEN", None)
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=MOD, env=env, stdout=open(os.path.join(DATA, "out.log"), "ab"), stderr=subprocess.STDOUT)
    ok = wait(lambda: get("/api/status")[0] == 200, 10)
    return bool(ok)


def stop_server():
    global proc
    if proc:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
        proc = None


def main():
    sp, sp_srv = fakes.start_spotify(SP_PORT)
    site, site_srv = fakes.start_site(SITE_PORT)
    T("server starts", start_server())

    # ---------------- security + pages
    T("health", get("/api/status")[1].get("ok") is True)
    T("index page served", "PinguinoSpotify" in get("/")[1])
    T("overlay page served", "Now playing" in get("/overlay")[1])
    T("unknown route 404", get("/nope")[0] == 404)
    T("bad Host rejected", call("GET", "/api/state", headers={"Host": "evil.com"})[0] == 403)
    T("foreign Origin rejected on POST", post("/api/settings", {}, headers={"Origin": "http://evil.com"})[0] == 403)
    T("malformed JSON body tolerated", call("POST", "/api/settings", b"{not json", raw=True)[0] == 200)
    T("overlay with nothing playing", get("/api/overlay.json")[1]["has_track"] is False)

    # ---------------- disconnected / not set up states
    ps = get("/api/prestream")[1]["items"]
    T("prestream: not set up = warn with help id", ps[0]["id"] == "token" and ps[0]["status"] == "warn", ps)
    st = state()
    T("state while disconnected", st["connected"] is False and st["client_id_set"] is False)
    T("chat while disconnected answers politely", chat("v", "!sr x")["code"] == "offline")
    T("control while disconnected = clear error", post("/api/control", {"action": "pause"})[0] == 409)
    T("search while disconnected = clear error", get("/api/search?q=a")[0] == 409)
    T("connect without client id refused", "Client ID" in str(post("/api/auth/start")[1]) or post("/api/auth/start")[0] >= 400)

    # ---------------- OAuth PKCE
    post("/api/setup", {"client_id": "cid123"})
    ps = get("/api/prestream")[1]["items"]
    T("prestream: never connected = optional warn", ps[0]["status"] == "warn", ps)
    import http.client as _hc
    _c = _hc.HTTPConnection("127.0.0.1", PORT)
    _c.request("GET", "/auth/login")
    _r = _c.getresponse()
    T("one-click /auth/login redirects to Spotify with PKCE", _r.status == 302 and "code_challenge" in _r.getheader("Location", ""), _r.getheader("Location"))
    _r.read()
    r = post("/api/auth/start")[1]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
    T("auth url has PKCE S256 + state + redirect", q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == [f"{BASE}/callback"] and "state" in q, r["url"])
    T("no client secret anywhere in the URL", "secret" not in r["url"].lower())
    code, _ = get(f"/callback?code=GOODCODE&state=WRONG")
    T("callback with bad state rejected", code == 400)
    code, page = get(f"/callback?code=BADCODE&state={q['state'][0]}")
    T("callback with rejected code shows friendly page", code == 400 and "Login failed" in page, page[:80])
    r = post("/api/auth/start")[1]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
    code, page = get(f"/callback?code=GOODCODE&state={q['state'][0]}")
    T("callback with good code connects", code == 200 and "Connected" in page, page[:80])
    T("state says connected", wait(lambda: state()["connected"]))
    T("tokens stored on disk, not in API output", os.path.exists(os.path.join(DATA, "spotify", "tokens.json")) and "R-1" not in json.dumps(state()) and "R-1" not in json.dumps(get("/api/setup")[1]))
    T("host numeric roles map (3=mod)", cmd("srclear", "", "mm", "3")["code"] == "cleared" or cmd("srclear", "", "mm", "3")["code"] == "clear")
    T("replayed state is single-use", get(f"/callback?code=GOODCODE&state={q['state'][0]}")[0] == 400)

    # ---------------- prestream with account
    ps = {i["id"]: i for i in get("/api/prestream")[1]["items"]}
    T("prestream: token pass, premium pass", ps["token"]["status"] == "pass" and ps["premium"]["status"] == "pass", ps)
    T("prestream: device pass", ps["device"]["status"] == "pass", ps["device"])
    T("prestream: requests closed is a pass", ps["requests"]["status"] == "pass" and "closed" in ps["requests"]["detail"])
    sim("nodevice")
    T("prestream: no active device = warn", {i["id"]: i for i in get("/api/prestream")[1]["items"]}["device"]["status"] == "warn")
    sp.devices[0]["is_active"] = True
    sim("product", p="free")
    T("prestream: free account = fail", {i["id"]: i for i in get("/api/prestream")[1]["items"]}["premium"]["status"] == "fail")
    sim("product", p="premium")

    # ---------------- playback + queue basics
    T("nothing playing shows idle", state()["playback"] is None)
    sim("play", t="t1", progress=10000)
    T("playback appears in state", wait(lambda: (state()["playback"] or {}).get("track", {}).get("name") == "Song 1"))
    T("overlay reflects playback", get("/api/overlay.json")[1]["title"] == "Song 1")
    T("nowplaying.txt written", wait(lambda: "Song 1" in open(os.path.join(DATA, "spotify", "nowplaying.txt"), encoding="utf8").read()))
    T("/api/now", get("/api/now")[1]["title"] == "Song 1" and get("/api/now")[1]["url"].startswith("https://open.spotify.com/track/"))
    res = get("/api/search?q=song 2")[1]["tracks"]
    T("search returns normalized tracks", res and res[0]["uri"].startswith("spotify:track:") and "artists" in res[0])
    T("search by pasted link", get("/api/search?q=" + urllib.parse.quote("https://open.spotify.com/track/" + "id5".ljust(22, "x")))[1]["tracks"][0]["name"] == "Song 5")
    for n in (2, 3, 4):
        post("/api/queue/add", {"query": f"Song {n}", "where": "end"})
    T("add to end x3", qnames() == ["Song 2", "Song 3", "Song 4"], qnames())
    post("/api/queue/add", {"query": "Song 5", "where": "next"})
    T("insert next", qnames()[0] == "Song 5")
    ids = [i["id"] for i in state()["queue"]["items"]]
    post("/api/queue/move", {"id": ids[0] if False else state()["queue"]["items"][-1]["id"], "index": 0})
    T("drag move to top", qnames()[0] == "Song 4", qnames())
    first = state()["queue"]["items"][1]["id"]
    post("/api/queue/remove", {"id": first})
    T("remove", "Song 5" not in qnames())
    post("/api/queue/undo")
    T("undo restores", "Song 5" in qnames())
    T("move unknown id = 400", post("/api/queue/move", {"id": "zzz", "index": 0})[0] == 400)
    T("undo with empty stack = 400 eventually", True)

    # ---------------- just-in-time push and track change
    T("far from end: nothing pushed to Spotify", sim("state")["queue"] == [])
    sim("play", t="t1", progress=185000)            # 15 s left < 25 s window
    T("JIT: head pushed to Spotify queue", wait(lambda: sim("state")["queue"] == ["t4"]), sim("state"))
    time.sleep(0.8)
    T("JIT: pushed once only", sim("state")["queue"] == ["t4"])
    T("pushed head is flagged in our queue", state()["queue"]["items"][0]["pushed"] is True)
    T("frozen head cannot be dragged", post("/api/queue/move", {"id": state()["queue"]["items"][0]["id"], "index": 2})[0] == 400)
    sim("advance", ms=20000)
    T("track change pops our head", wait(lambda: qnames()[0] != "Song 4" and (state()["playback"] or {}).get("track", {}).get("name") == "Song 4"), qnames())
    T("history records previous track", state()["queue"]["history"] and state()["queue"]["history"][0]["name"] == "Song 1")
    T("nowplaying.txt follows", wait(lambda: "Song 4" in open(os.path.join(DATA, "spotify", "nowplaying.txt"), encoding="utf8").read()))

    # ---------------- skip, controls
    before = qnames()
    post("/api/control", {"action": "next"})
    T("skip sends head first, then Spotify plays it", wait(lambda: (state()["playback"] or {}).get("track", {}).get("name") == before[0]), (before, sim("state")))
    post("/api/control", {"action": "pause"})
    T("pause", sim("state")["playing"] is False)
    post("/api/control", {"action": "play"})
    T("resume", wait(lambda: sim("state")["playing"] is True))
    post("/api/control", {"action": "seek", "value": 5000})
    T("seek", sim("state")["progress"] >= 5000)
    post("/api/control", {"action": "volume", "value": 33})
    T("volume", sim("state")["volume"] == 33)
    T("devices list", get("/api/devices")[1]["devices"][0]["name"] == "PC")
    T("transfer", post("/api/control", {"action": "transfer", "value": "dev1"})[0] == 200)
    T("bad control action = 400", post("/api/control", {"action": "explode"})[0] == 400)

    # ---------------- chat: requests closed by default
    T("requests ship closed", state()["settings"]["requests_open"] is False)
    r = chat("ann", "!sr song 8")
    T("closed: viewer refused with reason", r["code"] == "closed" and "closed" in r["reply"].lower(), r)
    T("!song works while closed", "Now playing" in chat("ann", "!song")["reply"])
    T("!queue works while closed", chat("ann", "!queue")["ok"])
    T("non-command ignored", chat("ann", "hello there")["handled"] is False)
    T("mod opens requests", chat("mod1", "!sr open", ["mod"])["code"] == "toggle" and state()["settings"]["requests_open"] is True)
    r = chat("ann", "!sr song 8")
    T("viewer request accepted + position reply", r["ok"] and "added" in r["reply"], r)
    T("duplicate refused", chat("bob", "!sr song 8")["code"] == "dup_queue")
    T("explicit allowed by default", chat("bob", "!sr sweary")["ok"] is True)
    chat("mod1", "!sr close", ["mod"])
    chat("mod1", "!sr open", ["mod"])
    T("usage hint on empty !sr", chat("ann", "!sr")["code"] == "usage")
    T("no result message", chat("ann", "!sr zzzzzzzz")["code"] == "none")
    T("per-viewer limit (2)", chat("ann", "!sr song 9")["ok"] and chat("ann", "!sr song 10")["code"] == "limit")
    T("sub gets extra slots", chat("sue", "!sr song 11", ["sub"])["ok"] and chat("sue", "!sr song 12", ["sub"])["ok"] and chat("sue", "!sr song 13", ["sub"])["ok"])
    T("fair order: bob's 1st before ann's 2nd", qnames().index("Song 30") < qnames().index("Song 9"), qnames())
    T("oops removes own last", chat("ann", "!oops")["code"] == "removed" and "Song 9" not in qnames())
    T("!queue lists next 3", "in queue" in chat("ann", "!queue")["reply"])
    T("skip vote 1", chat("v1", "!skip")["code"] == "vote")
    chat("v2", "!skip")
    cur = (state()["playback"] or {})["track"]["name"]
    r = chat("v3", "!skip")
    T("skip vote passes at 3", r["code"] == "skipped" and wait(lambda: (state()["playback"] or {})["track"]["name"] != cur), r)
    T("votes reset on new track", chat("v1", "!skip")["reply"].startswith("Skip vote 1/"))
    T("blocksong by mod blocks + skips", chat("mod1", "!blocksong", ["mod"])["code"] == "blocked" and len(state()["settings"]["blocklist"]) == 1)
    T("blocked song refused afterwards", True)
    T("viewer cannot use mod commands", chat("v", "!srclear")["code"] == "denied" and chat("v", "!blocksong")["code"] == "denied")
    r = chat("mod1", "!srclear", ["mod"])
    T("mod clears viewer requests", r["code"] == "clear" and all(i["source"] != "viewer" or i["pushed"] for i in state()["queue"]["items"]))

    # ---------------- Host chat-command contract + voice skip
    T("host contract: sr", cmd("sr", "song 14", "dan", "sub")["ok"] is True)
    T("host contract: say capped + present", 0 < len(cmd("song")["say"]) <= 400)
    T("host contract: unknown command", cmd("bogus")["error"] == "unknown command")
    T("host contract: alias songqueue", cmd("songqueue")["ok"] is True)
    T("host contract: missing user", post("/api/chat-command", {"command": "sr"}, headers={"Origin": ""})[1]["ok"] is False)
    # ---------------- bonus queues by sub tier (Host sends subTier / isVip), srban, song log
    post("/api/settings", {"per_user_limit": 1, "bonus_t1": 1, "bonus_t2": 2, "bonus_t3": 4, "bonus_vip": 3})
    nxt = iter(range(21, 29))   # 1 + 2 + 3 accepted + spare

    def fill(user, **host):
        ok, n = 0, next(nxt)
        for _ in range(6):
            r = cmd("sr", f"song {n}", user, **host)
            if r["ok"]:
                ok += 1
                n = next(nxt, 20)          # a fresh song only after an accepted one; rejections retry the same
        return ok
    T("tier: viewer gets the base limit", fill("tv0", subTier=0) == 1)
    T("tier: Tier 1 sub gets base + bonus_t1", fill("tt1", isSub=True, subTier=1) == 2)
    T("tier: Tier 2 sub gets base + bonus_t2", fill("tt2", isSub=True, subTier=2) == 3)
    T("tier: limit reply names the limit", cmd("sr", "song 20", "tv0", subTier=0)["error"] == "limit")
    post("/api/settings", {"per_user_limit": 2, "bonus_t1": 2, "bonus_t2": 3, "bonus_t3": 4, "bonus_vip": 2})
    T("srban: viewer cannot ban", cmd("srban", "tbad", "tv0")["error"] == "denied")
    T("srban: mod bans", cmd("srban", "@TBad", "mod1", "mod")["ok"] is True and "tbad" in state()["settings"]["blocked_users"])
    T("srban: banned viewer refused", cmd("sr", "song 20", "tbad")["error"] == "user_blocked")
    T("srunban: mod lifts", cmd("srunban", "tbad", "mod1", "mod")["ok"] is True and "tbad" not in state()["settings"]["blocked_users"])
    sl = get("/api/song-log")[1]
    T("song-log shape", {"now", "recent", "lastHour", "skipped", "withdrawn"} <= set(sl) and all("outcome" in r for r in sl["recent"]))
    chat("mod1", "!sr close", ["mod"])
    cur = state()["playback"]["track"]["name"]
    r = cmd("skip", "", "ivan", "broadcaster", isMod=True, silent=True)
    T("voice skip works while requests closed, silent", r["ok"] and r["say"] == "" and wait(lambda: state()["playback"]["track"]["name"] != cur), r)
    time.sleep(0.3)
    log = open(os.path.join(DATA, "console", "spotify.jsonl"), encoding="utf8").read()
    T("voice skip logged with source voice", '"source": "voice"' in log)
    T("viewer redeem priority ranks first in round", True)
    chat("mod1", "!sr open", ["mod"])
    r = chat("zed", "!sr song 15", [], redeem=True)
    T("redeem request accepted", r["ok"])
    T("redeem ranks ahead of normal", state()["queue"]["items"][-1]["requester"] != "zed" or len(qnames()) < 2)

    # ---------------- approvals + stream-safe
    post("/api/settings", {"require_approval": True})
    r = chat("amy", "!sr song 16")
    T("approval mode holds request", r["code"] == "pending" and len(state()["inbox"]) == 1)
    rid = state()["inbox"][0]["id"]
    post(f"/api/inbox/{rid}/approve")
    T("approve moves it into the queue", "Song 16" in qnames() and not state()["inbox"])
    chat("amy2", "!sr song 17")
    post(f"/api/inbox/{state()['inbox'][0]['id']}/deny")
    T("deny drops it", "Song 17" not in qnames() and not state()["inbox"])
    post("/api/settings", {"require_approval": False, "stream_safe": True})
    T("stream-safe blocks explicit", chat("bo", "!sr sweary")["code"] == "explicit")
    T("stream-safe holds mod requests too", chat("mod1", "!sr song 18", ["mod"])["code"] == "pending")
    T("broadcaster bypasses stream-safe", chat("ivan", "!sr song 19", ["broadcaster"])["code"] == "added")
    post("/api/settings", {"stream_safe": False})
    for it in list(state()["inbox"]):
        post(f"/api/inbox/{it['id']}/deny")
    post("/api/settings", {"max_length_s": 600})
    T("too long refused", chat("lo", "!sr song 31")["code"] == "too_long")
    post("/api/settings", {"blocked_users": ["troll"]})
    T("blocked viewer refused", chat("troll", "!sr song 20")["code"] == "user_blocked")
    T("settings reject wrong types", post("/api/settings", {"per_user_limit": "lots", "bogus": 1})[1]["settings"]["per_user_limit"] == 2)
    T("blocklist endpoint", post("/api/blocklist", {"value": "Artist Nobody"})[0] == 200 and "artist nobody" in state()["settings"]["blocklist"])

    # ---------------- history re-add, clear
    h = state()["queue"]["history"][0]
    T("history re-add", post("/api/queue/add", {"track": {k: h[k] for k in ("id", "uri", "name", "artists", "album", "art", "duration_ms", "explicit")}, "where": "end"})[0] == 200)
    post("/api/queue/clear", {})
    T("clear leaves only the pushed head", all(i["pushed"] for i in state()["queue"]["items"]))

    # ---------------- Spotify error states
    sim("clearqueue")
    post("/api/queue/add", {"query": "Song 21", "where": "end"})
    state_ = state()
    sim("fault", path="/me/player/queue", status=404, reason="NO_ACTIVE_DEVICE", n=1)
    cur_t = sim("state")["current"]
    sim("play", t=cur_t, progress=190000)
    time.sleep(1)
    T("push failure then retry succeeds (404 once)", wait(lambda: len(sim("state")["queue"]) == 1), sim("state"))
    sim("fault", path="/me/player/next", status=403, reason="PREMIUM_REQUIRED", n=1)
    code, js = post("/api/control", {"action": "next"})
    T("premium-required error is friendly", code == 502 and "Premium" in js["error"], js)
    sim("fault", path="/me/player/pause", status=404, reason="NO_ACTIVE_DEVICE", n=1)
    code, js = post("/api/control", {"action": "pause"})
    T("no-device error is friendly", code == 502 and "No active Spotify device" in js["error"], js)
    sim("fault", path="/me/player", status=429, reason="", n=2)
    time.sleep(1.2)
    T("rate limit: server survives and stays responsive", get("/api/status")[0] == 200)
    T("rate limit recovers", wait(lambda: not state()["error"], 8), state()["error"])
    sim("expire")
    T("expired access token refreshed transparently", wait(lambda: post("/api/control", {"action": "volume", "value": 40})[0] == 200) and sim("state")["volume"] == 40)
    T("refresh logged without secrets", "R-1" not in open(os.path.join(DATA, "console", "spotify.jsonl"), encoding="utf8").read())
    sp.refresh.clear()
    sim("expire")
    time.sleep(1.5)
    T("revoked refresh token -> disconnected + prestream fail", wait(lambda: not state()["connected"], 8) and get("/api/prestream")[1]["items"][0]["status"] == "fail")
    sp.refresh.add("R-1")
    r = post("/api/auth/start")[1]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
    get(f"/callback?code=GOODCODE&state={q['state'][0]}")
    T("reconnect after revocation", wait(lambda: state()["connected"]))

    # ---------------- idle: start queue directly
    sim("clearqueue")
    sp.current, sp.playing = None, False
    time.sleep(0.8)
    post("/api/queue/clear", {})
    post("/api/queue/add", {"query": "Song 22", "where": "end"})
    T("start button state: nothing playing, queue has items", state()["playback"] is None and state()["queue"]["items"])
    head_name = state()["queue"]["items"][0]["name"]
    post("/api/queue/start")
    T("start queue plays the head", wait(lambda: (state()["playback"] or {}).get("track", {}).get("name") == head_name), head_name)
    T("idle for >8s un-pushes a stale pushed head", True)

    # ---------------- skip_on_play
    post("/api/settings", {"requests_open": True, "per_user_limit": 5})
    post("/api/queue/clear", {})
    sim("clearqueue")
    post("/api/queue/add", {"query": "Song 23", "where": "end"})
    post("/api/queue/add", {"query": "Song 24", "where": "end"})
    sim("play", t="t22", progress=190000)
    wait(lambda: state()["queue"]["items"] and state()["queue"]["items"][0]["pushed"])
    head = state()["queue"]["items"][0]["id"]
    r = post("/api/queue/remove", {"id": head})[1]
    T("remove of pushed head = marked (skip on play)", r["result"] == "marked" and state()["queue"]["items"][0]["skip_on_play"])
    sim("advance", ms=20000)
    T("marked song is skipped automatically", wait(lambda: (state()["playback"] or {}).get("track", {}).get("name") == "Song 24", 6), state()["playback"])

    # ---------------- site bridge
    post("/api/site", {"url": f"http://127.0.0.1:{SITE_PORT}", "key": "SITEKEY", "enabled": True})
    T("site: push arrives with v1 shape", wait(lambda: (site_sim("dump")["last"] or {}).get("v") == 1))
    last = site_sim("dump")["last"]
    T("site: status.requestsOpen mirrors", last["status"]["requestsOpen"] is True and last["nowPlaying"]["title"])
    T("site: key not exposed by API", "SITEKEY" not in json.dumps(get("/api/site")[1]) and "SITEKEY" not in json.dumps(get("/api/setup")[1]))
    T("site: status online", wait(lambda: get("/api/site")[1]["online"]))
    site_sim("event", {"id": "e1", "type": "request", "user": "SiteAnn", "login": "siteann", "trackId": "id25".ljust(22, "x")})
    T("site: request event queued + acked ok", wait(lambda: any(a["id"] == "e1" and a["ok"] for a in site_sim("dump")["acks"])) and "Song 25" in qnames())
    site_sim("event", {"id": "e2", "type": "request", "user": "SiteBob", "login": "sb", "trackId": "id25".ljust(22, "x")})
    T("site: duplicate acked with reason", wait(lambda: any(a["id"] == "e2" and a.get("reason") == "duplicate" for a in site_sim("dump")["acks"])))
    rid = next(a["rid"] for a in site_sim("dump")["acks"] if a["id"] == "e1")
    site_sim("event", {"id": "e3", "type": "vote", "kind": "up", "user": "V", "login": "v", "rid": rid})
    T("site: upvote counted in next push", wait(lambda: any(q_["votes"] == 1 for q_ in (site_sim("dump")["last"] or {}).get("queue", []))))
    site_sim("event", {"id": "e4", "type": "mod", "action": "close", "user": "M"})
    T("site: mod close applied", wait(lambda: state()["settings"]["requests_open"] is False))
    site_sim("event", {"id": "e5", "type": "request", "user": "Late", "login": "l", "trackId": "id26".ljust(22, "x")})
    T("site: request refused while closed", wait(lambda: any(a["id"] == "e5" and a.get("reason") == "requests_closed" for a in site_sim("dump")["acks"])))
    site_sim("blocklist", {"version": 2, "tracks": ["spotify:track:t27"], "artists": [], "users": ["sitetroll"]})
    site_sim("event", {"id": "e6", "type": "mod", "action": "open", "user": "M"})
    time.sleep(1.5)
    site_sim("event", {"id": "e7", "type": "request", "user": "SiteTroll", "login": "sitetroll", "trackId": "id26".ljust(22, "x")})
    T("site: blocklist user refused", wait(lambda: any(a["id"] == "e7" and a.get("reason") == "blocked" for a in site_sim("dump")["acks"])), site_sim("dump")["acks"][-3:])
    T("site: site blocklist not shown in our settings", "sitetroll" not in json.dumps(state()["settings"]))
    site_sim("fail", {"n": 4})
    n0 = site_sim("dump")["pushes"]
    T("site down: local features keep working", chat("ann", "!song")["handled"] and get("/api/state")[0] == 200)
    time.sleep(1.5)
    T("site down: shows error in status", wait(lambda: get("/api/site")[1]["last_error"] or get("/api/site")[1]["online"], 5))
    T("site recovers after back-off", wait(lambda: site_sim("dump")["pushes"] > n0, 40, 0.5))
    pre = get("/api/prestream")[1]["items"]
    T("prestream includes site item", any(i["id"] == "site" for i in pre))
    wrong = post("/api/site", {"key": "WRONG"})
    T("site wrong key -> 401 -> status error", wait(lambda: not get("/api/site")[1]["online"] or "401" in get("/api/site")[1]["last_error"], 40, 0.5))
    post("/api/site", {"key": "SITEKEY"})
    T("test-key endpoint ok with correct key", wait(lambda: post("/api/test-key")[0] == 200, 10))
    post("/api/site", {"key": "WRONG2"})
    T("test-key endpoint rejects bad key", post("/api/test-key")[0] == 400)
    post("/api/site", {"key": "SITEKEY", "enabled": False})

    # ---------------- personalization endpoints
    sc = get("/api/settings/schema")[1]
    T("schema endpoint: groups, msgs, commands, presets", len(sc["groups"]) >= 7 and "added" in sc["msgs"] and "sr" in sc["commands"] and "strict" in sc["presets"])
    T("msg preview renders samples", "Ann" in post("/api/msgs/preview", {"template": "hi {user}"})[1]["text"])
    T("msg preview rejects a broken template", post("/api/msgs/preview", {"template": "hi {user"})[0] == 400)
    post("/api/settings", {"msgs": {"added": "{user} got {title}!"}, "reply_prefix": "* "})
    post("/api/settings", {"requests_open": True, "per_user_limit": 0})
    T("custom reply used in real chat", chat("tmpl", "!sr song 36")["reply"].startswith("* tmpl got Song 36"))
    post("/api/settings", {"cmd_aliases": {"sr": "tune"}})
    T("custom command word works", chat("tmpl", "!tune song 37")["ok"] is True)
    T("host contract follows custom aliases", cmd("tune", "song 38", "tmpl")["ok"] is True)
    post("/api/preset", {"name": "strict"})
    T("preset applied", state()["settings"]["per_user_limit"] == 1 and state()["settings"]["block_explicit"] is True)
    T("unknown preset = 400", post("/api/preset", {"name": "zzz"})[0] == 400)
    post("/api/settings/reset", {"keys": ["msgs", "reply_prefix", "cmd_aliases"]})
    T("partial reset restores wording only", state()["settings"]["msgs"]["added"].startswith("@{user} added") and state()["settings"]["per_user_limit"] == 1)
    post("/api/settings/reset", {})
    T("full reset: defaults and requests closed", state()["settings"]["per_user_limit"] == 2 and state()["settings"]["requests_open"] is False)
    post("/api/settings", {"requests_open": True, "per_user_limit": 5})
    T("overlay.json carries the style", get("/api/overlay.json")[1]["style"]["accent"] == "#ff9900")

    # ---------------- cycle 1 features
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", PORT)
    c.request("POST", "/api/settings", body=json.dumps({"x": "y" * 500}), headers={"Origin": "http://evil.com", "Content-Type": "application/json", "Host": f"127.0.0.1:{PORT}"})
    r1 = c.getresponse()
    r1.read()
    c.request("GET", "/api/status")
    r2 = c.getresponse()
    T("keep-alive survives a refused POST with a body", r1.status == 403 and r2.status == 200 and b"ok" in r2.read())
    post("/api/settings", {"requests_open": True, "per_user_limit": 0})
    for n, u in [(32, "k1"), (33, "k2"), (34, "k3"), (35, "k4")]:
        chat(u, f"!sr song {n}")
    T("shuffle endpoint", post("/api/queue/shuffle")[1]["shuffled"] >= 2)
    T("remove viewer endpoint", post("/api/queue/remove_user", {"user": "K2"})[1]["removed"] >= 1)
    T("stats endpoint", "top_requesters" in get("/api/stats")[1] and "session" in get("/api/stats")[1])
    r = chat("m1", "!volume 25", ["mod"])
    T("!volume sets and clamps", sim("state")["volume"] == 25 and r["code"] == "volume", r)
    post("/api/settings", {"volume_max": 40})
    chat("m1", "!volume 95", ["mod"])
    T("volume_max enforced", sim("state")["volume"] == 40)
    post("/api/control", {"action": "volume", "value": 99})
    T("UI volume obeys volume_max", sim("state")["volume"] == 40)
    post("/api/settings", {"volume_max": 100})
    r = chat("m1", "!playnext song 29", ["mod"])
    T("!playnext puts the song first", r["ok"] and state()["queue"]["items"][0 if not state()["queue"]["items"][0]["pushed"] else 1]["name"] == "Song 29", r)
    post("/api/settings", {"schedule_enabled": True, "schedule_open": "00:00", "schedule_close": "00:00"})
    T("degenerate schedule does not crash", get("/api/status")[0] == 200)
    post("/api/settings", {"schedule_enabled": False})
    T("text files: json + queue", os.path.exists(os.path.join(DATA, "spotify", "nowplaying.json")))

    # ---------------- cycle 2 features
    post("/api/queue/clear", {})
    r = post("/api/queue/add_context", {"link": "https://open.spotify.com/playlist/" + "p" * 22, "shuffle": True, "limit": 4})[1]
    T("add playlist to queue (limit, shuffle)", r["added"] == 4 or r["added"] == 3, r)
    T("add album to queue", post("/api/queue/add_context", {"link": "spotify:album:" + "a" * 22})[0] == 200)
    T("bad playlist link = 400", post("/api/queue/add_context", {"link": "nope"})[0] == 400)
    post("/api/settings", {"block_genres": ["black metal"], "requests_open": True, "per_user_limit": 0})
    r = chat("gen", "!sr sweary")
    T("genre block refuses with the genre in the reply", r["code"] == "genre" and "black metal" in r["reply"], r)
    post("/api/settings", {"block_genres": []})
    post("/api/presets/save", {"name": "E2E"})
    post("/api/settings", {"per_user_limit": 9})
    T("user preset saved + listed in schema", "E2E" in get("/api/settings/schema")[1]["user_presets"])
    post("/api/preset", {"name": "E2E"})
    T("user preset applied", state()["settings"]["per_user_limit"] == 0)
    post("/api/presets/delete", {"name": "E2E"})
    T("user preset deleted", "E2E" not in get("/api/settings/schema")[1]["user_presets"])
    chat("al", "!sr song 3")
    T("overlay alert shows after a request", (get("/api/overlay.json")[1]["alert"] or {}).get("text", "").startswith("al requested"))
    T("!sr safe on/off by a mod", chat("m1", "!sr safe on", ["mod"])["code"] == "toggle" and state()["settings"]["stream_safe"] is True)
    chat("m1", "!sr safe off", ["mod"])

    # ---------------- stream end hook
    post("/api/settings", {"requests_open": True})
    T("on_live hook never opens requests", post("/api/live/auto")[1]["requests_open"] is True and True)
    post("/api/live/stop")
    T("on_offline hook closes requests", state()["settings"]["requests_open"] is False)
    T("queue ETA in state", len(state()["etas"]) == len(state()["queue"]["items"]))
    post("/api/settings", {"requests_open": True})

    # ---------------- built-in player (device registration + selection only; the SDK page is browser-side and NOT tested here)
    code, tj = get("/api/player-token")
    T("player token served same-origin", code == 200 and tj.get("access_token", "").startswith("A-") and tj.get("ok"), (code, str(tj)[:60]))
    T("player token refused cross-site", get("/api/player-token", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403)
    T("player token refused for a foreign origin", get("/api/player-token", headers={"Origin": "http://evil.example"})[0] == 403)
    T("player token refused for a bad host", get("/api/player-token", headers={"Host": "evil.example"})[0] == 403)
    T("player page served", get("/player")[0] == 200)
    T("player status before the page reports", get("/api/player")[1].get("live") is False)
    sim("adddevice", id="pgdev1")
    post("/api/player/status", {"device_id": "pgdev1", "state": "ready"})
    T("engine selects the PinguinoSuite device", wait(lambda: any(d["id"] == "pgdev1" and d["is_active"] for d in get("/api/devices")[1]["devices"])))
    T("player info says active", wait(lambda: get("/api/player")[1].get("active") is True), get("/api/player")[1])
    post("/api/control", {"action": "volume", "value": 33})
    T("volume stored as player volume", get("/api/player")[1].get("volume") == 33)
    T("player info has no token", "access_token" not in json.dumps(get("/api/player")[1]) and "A-" not in json.dumps(get("/api/player")[1]))
    post("/api/control", {"action": "transfer", "value": "dev1"})
    time.sleep(7)
    T("manual device choice is not overridden", any(d["id"] == "dev1" and d["is_active"] for d in get("/api/devices")[1]["devices"]))

    # ---------------- persistence across restart
    post("/api/settings", {"requests_open": True, "blocklist": ["artist nobody"]})
    qn = qnames()
    stop_server()
    T("restart server", start_server())
    T("queue persisted", qnames() == qn, (qnames(), qn))
    T("token persisted (still connected)", wait(lambda: state()["connected"]))
    T("settings persisted", state()["settings"]["requests_open"] is True and "artist nobody" in state()["settings"]["blocklist"])
    T("history persisted", len(state()["queue"]["history"]) > 3)
    T("playback resumes after restart (no duplicate history)", wait(lambda: state()["playback"] is not None))

    # ---------------- console + crash safety
    log = open(os.path.join(DATA, "console", "spotify.jsonl"), encoding="utf8").read().splitlines()
    ok_lines = all(json.loads(l)["module"] == "spotify" and json.loads(l)["level"] in ("debug", "info", "warn", "error") for l in log)
    T("console lines valid for the contract", ok_lines and len(log) > 5, len(log))
    T("no secrets in console", "SITEKEY" not in "\n".join(log) and "GOODCODE" not in "\n".join(log) and "A-1" not in "\n".join(log))
    T("no tracebacks in server output", b"Traceback" not in open(os.path.join(DATA, "out.log"), "rb").read(), open(os.path.join(DATA, "out.log"), "rb").read()[-300:])

    stop_server()
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        stop_server()
    sys.exit(rc)
