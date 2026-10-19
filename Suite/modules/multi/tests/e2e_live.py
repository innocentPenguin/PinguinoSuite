"""End-to-end pass over every Multi feature against a REAL server process (throwaway port + data dir, nothing audible, no network).
Run:  ..\\..\\.venv\\Scripts\\python.exe tests\\e2e_live.py      Prints a PASS/FAIL table and writes Docs\\PinguinoMulti\\E2E_RESULTS.md"""
import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import websockets

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "e2e-module-token"
RESULTS = []


def call(method, path, body=None, headers=None, base=BASE):
    h = {"content-type": "application/json", "origin": BASE}
    h.update(headers or {})
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw[:1] in "[{" else raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw[:1] in "[{" else raw)


def check(area, name, ok, detail=""):
    RESULTS.append((area, name, bool(ok), str(detail)[:140]))


def inject(**kw):
    kw.setdefault("text", "hello")
    return call("POST", "/api/dev/inject", kw)[1]


async def ws_events(seconds, trigger):
    got = []
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=BASE) as ws:
        async def reader():
            try:
                while True:
                    got.append(json.loads(await ws.recv()))
            except Exception:
                pass
        t = asyncio.create_task(reader())
        await asyncio.sleep(0.5)
        await asyncio.to_thread(trigger)
        await asyncio.sleep(seconds)
        t.cancel()
    return got


def run():
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise SystemExit(f"port {PORT} is already in use: stop the other test server first (results would be polluted)")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="multi-e2e-"))
    env = dict(os.environ, MULTI_PORT=str(PORT), PINGUINO_DATA_DIR=str(tmp), PINGUINO_API_TOKEN=TOKEN, PINGUINO_CORE_URL="http://127.0.0.1:1", MULTI_NO_KEYRING="1")
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                if call("GET", "/api/status")[0] == 200:
                    break
            except Exception:
                time.sleep(0.25)
        s, st = call("GET", "/api/status")
        check("Core", "server starts, /api/status", s == 200 and st["ok"], f"{len(st['connectors'])} connectors")
        check("Core", "connectors declared", {c["platform"] for c in st["connectors"]} == {"twitch", "discord", "youtube", "tiktok"})
        time.sleep(1.0)
        st = call("GET", "/api/status")[1]
        check("Core", "no platform connected -> Twitch needs_auth (honest)", next(c for c in st["connectors"] if c["platform"] == "twitch")["status"] == "needs_auth")

        # ingest + ranking + cards + websocket
        def trig():
            inject(user="alice", text="hey innocentpenguin what game is this?", badges=["subscriber"], color="#FF4500")
            inject(user="bob", text="lol nice", platform="discord")
            inject(user="newbie", text="hi first time here", first_time=True)
        events = asyncio.run(ws_events(1.5, trig))
        types = [e["type"] for e in events]
        check("Ingest", "messages arrive over WebSocket", types.count("message") == 3, types)
        check("Ingest", "question+mention makes a priority card", "card.new" in types)
        s, msgs = call("GET", "/api/messages?limit=20")
        check("Ingest", "messages stored and listed", s == 200 and len(msgs) >= 3)
        alice = next(m for m in msgs if m["user"] == "alice")
        s, ex = call("GET", f"/api/messages/{alice['id']}/explain")
        check("Ingest", "score is explained (reasons)", s == 200 and any(r["rule"] == "question" for r in ex["reasons"]), [r["rule"] for r in ex.get("reasons", [])])
        inject(id=alice["id"], user="alice", text="dup")
        time.sleep(0.3)
        check("Ingest", "duplicate id ignored", len([m for m in call("GET", "/api/messages?limit=50")[1] if m["id"] == alice["id"]]) == 1)

        s, cards = call("GET", "/api/cards")
        card = cards["open"][0]
        for action in ("snooze", "reopen", "answer"):
            s, _ = call("POST", f"/api/cards/{card['id']}/{action}", {"seconds": 60})
            check("Cards", f"card action: {action}", s == 200)
        inject(user="carl", text="what is your setup?")
        time.sleep(0.3)
        s, r = call("POST", "/api/hotkey/dismiss")
        check("Cards", "hotkey dismiss acts on top card", s == 200, r)
        s, c2 = call("POST", "/api/cards/manual", {"message_id": alice["id"]})
        check("Assist", "mark to answer creates a card", s == 200 and c2["reasons"][0]["rule"] == "marked")
        s, rc = call("GET", "/api/recap")
        check("Cards", "after-stream recap", s == 200 and "count" in rc)
        s, cl = call("GET", "/api/claims")
        check("Cards", "streamer-first claims endpoint", s == 200)

        # search / viewer / notes / mute / pins / templates
        s, hits = call("GET", "/api/search?q=innocentpenguin")
        check("Chat", "search finds a message", s == 200 and len(hits) >= 1)
        s, ch = call("GET", "/api/chatter/twitch/alice")
        check("Assist", "chatter card (who is this)", s == 200 and ch["messages"] >= 1 and ch["badges"] == ["subscriber"])
        s, n = call("POST", "/api/viewers/alice/note", {"note": "likes Elden Ring"})
        check("Assist", "private note saved", s == 200 and call("GET", "/api/chatter/twitch/alice")[1]["note"] == "likes Elden Ring")
        s, m = call("POST", "/api/viewers/spammer/mute", {"muted": True})
        check("Chat", "mute viewer in ranking", s == 200 and "spammer" in m["muted"])
        s, p = call("POST", "/api/pins", {"message_id": alice["id"]})
        check("Chat", "pin a message", s == 200 and p["pins"][0]["user"] == "alice")
        call("POST", "/api/pins", {"message_id": alice["id"], "pin": False})
        s, t = call("POST", "/api/templates", {"templates": ["Thanks {name}!", "lol"]})
        check("Assist", "quick-reply templates", s == 200 and t["templates"][0].startswith("Thanks"))
        s, sg = call("POST", "/api/assist/suggest", {"message_id": alice["id"]})
        check("Assist", "suggested replies (no AI key -> templates)", s == 200 and sg["source"] == "templates" and sg["replies"][0] == "Thanks alice!", sg.get("why"))
        s, tr = call("POST", "/api/assist/translate", {"message_id": alice["id"]})
        check("Assist", "translate degrades gracefully without a key", s == 200 and tr["source"] == "none")
        s, bad = call("POST", "/api/assist/suggest", {"message_id": "twitch:x:none"})
        check("Assist", "unknown message -> 404", s == 404)

        # sending safety
        s, r = call("POST", "/api/send", {"platform": "all", "text": "hi everyone"})
        check("Safety", "no broadcast-to-all send", s == 400, r)
        s, r = call("POST", "/api/send", {"platform": "twitch", "text": "hi"})
        check("Safety", "send blocked while Twitch is not connected", s in (400, 502), r)
        s, r = call("POST", "/api/mod/ban", {"message_id": alice["id"]})
        check("Safety", "mod action refused without the scopes", s in (400, 502), r)

        # look, events, popout
        s, cs = call("GET", "/api/chatstyle")
        check("Look", "chat look loads defaults", s == 200 and cs["style"]["base"]["marker"] == "text")
        s, cs2 = call("POST", "/api/chatstyle", {"style": {"base": {"marker": "both", "size": 18}, "event": {"raid": {"bg": "#123456"}}}})
        check("Look", "chat look saved + validated", s == 200 and cs2["style"]["base"]["marker"] == "both" and cs2["style"]["event"]["raid"]["bg"] == "#123456")
        s, cs3 = call("POST", "/api/chatstyle", {"style": {"base": {"family": "x;}", "bg": "javascript:1"}}})
        check("Look", "hostile style values are rejected", cs3["style"]["base"]["family"] == "system-ui" and cs3["style"]["base"]["bg"] == "#09090a")
        s, r = call("POST", "/api/events", {"type": "follow", "user": "FollowFin"}, headers={"origin": "", "authorization": "Bearer " + TOKEN})
        check("Look", "follow event pushed with the module token", s == 200, r)
        s, r = call("POST", "/api/events", {"type": "follow", "user": "X"}, headers={"origin": ""})
        check("Safety", "event push without a token is refused", s in (401, 403), r)
        s, pg = call("GET", "/popout")
        check("Look", "stream-safe popout serves", s == 200 and "<!--THEME-->" not in pg and "theme.css" in pg)
        s, pg = call("GET", "/?type=style")
        check("Look", "style editor page serves", s == 200)
        time.sleep(0.3)
        s, mm = call("GET", "/api/messages?limit=50")
        fol = [m for m in mm if m.get("event") == "follow"]
        check("Look", "follow shown as a styled event, never ranked", len(fol) == 1 and fol[0]["tier"] == "none")

        # dashboard / feed
        s, d = call("GET", "/api/dashboard")
        check("Dashboard", "chat rate + top chatters", s == 200 and d["messages_last_hour"] >= 4 and d["top_chatters"], d["rate_per_min"])
        s, f = call("GET", "/api/feed?since=0")
        check("Dashboard", "aux feed snapshot", s == 200 and len(f["messages"]) >= 4)

        # sounds (off by default; settings only, no audio)
        s, dg = call("GET", "/api/ding")
        check("Sounds", "ding off by default, bell sound found", s == 200 and not dg["enabled"] and dg["sound_exists"] and dg["volume"] == 24)
        s, dg2 = call("POST", "/api/ding/settings", {"platforms": ["twitch", "kick"], "volume": 0, "returning_volume": 0, "master_volume": 0})
        check("Sounds", "ding settings validated + saved", s == 200 and dg2["platforms"] == ["twitch"] and dg2["master_volume"] == 0)
        s, r = call("POST", "/api/ding/settings", {"sound": "C:\\nope\\x.mp3"})
        check("Sounds", "missing sound file refused", s == 400)
        s, pp = call("POST", "/api/pop/settings", {"platforms": ["twitch", "youtube"], "master_volume": 0})
        check("Sounds", "chat pop settings saved", s == 200 and pp["volume"]["youtube"] == 76)
        inject(user="soundtest", text="silent at master volume 0")
        time.sleep(2.5)
        s, dg3 = call("GET", "/api/ding")
        s, pp3 = call("GET", "/api/pop")
        check("Sounds", "new-chatter ding plays (silent at volume 0)", dg3["played"] >= 1 and dg3["errors"] == 0, dg3)
        check("Sounds", "chat pop plays (silent at volume 0)", pp3["played"] >= 1 and pp3["errors"] == 0, pp3)
        s, nc = call("GET", "/api/newchatters?since=0")
        check("Sounds", "new-chatter feed for the bot", s == 200 and any(x["user"] == "soundtest" for x in nc["items"]))

        # secrets are write-only
        secret = "S3CRETtokenVALUE" + "x" * 20
        s, r = call("POST", "/api/secrets/discord", {"token": secret, "channels": ["123456789012345678"]})
        check("Secrets", "discord token stored write-only", s == 200 and secret not in json.dumps(r) and r["has_token"])
        call("POST", "/api/secrets/discord", {"clear": True})
        check("Secrets", "no secret in /api/setup or /api/settings", secret not in json.dumps(call("GET", "/api/setup")[1]) + json.dumps(call("GET", "/api/settings")[1]))

        # status, help, integrations, prestream, console
        s, ps = call("GET", "/api/prestream")
        ids = {i["id"] for i in ps["items"]}
        check("Console", "prestream items all have help", s == 200 and all(i["help"] for i in ps["items"]), sorted(ids))
        check("Console", "Twitch down is a FAIL, optional ones WARN", next(i for i in ps["items"] if i["id"] == "conn-twitch")["status"] == "fail" and next(i for i in ps["items"] if i["id"] == "conn-discord")["status"] == "warn")
        s, it = call("GET", "/api/integrations")
        check("Console", "integrations items with help + test path", s == 200 and len(it["items"]) == 4 and all(i["help"] and i["test"] for i in it["items"]))
        s, r = call("POST", "/api/test/twitch")
        check("Console", "integration Test fails honestly when not connected", s == 409, r)
        s, ha = call("GET", "/api/help/all")
        check("Console", "help index incl. module overview + secrets", s == 200 and "_module" in ha["items"] and len(ha["secrets"]) == 4)
        time.sleep(0.5)
        log = tmp / "console" / "multi.jsonl"
        text = log.read_text("utf-8") if log.exists() else ""
        check("Console", "console log written, no secrets, valid JSON lines", log.exists() and all(json.loads(l)["module"] == "multi" for l in text.splitlines()) and secret not in text)
        check("Console", "prestream-multi.json fallback written", (tmp / "console" / "prestream-multi.json").exists())

        # windows / layouts / settings
        s, w = call("POST", "/api/windows", {"type": "chat"})
        check("Windows", "create a chat window", s == 200 and w["type"] == "chat")
        s, ws_ = call("GET", "/api/windows")
        check("Windows", "list windows with monitor placement", s == 200 and any(x["id"] == w["id"] and "placed" in x for x in ws_))
        s, u = call("PUT", f"/api/windows/{w['id']}", {"font_size": 18, "link_group": "g1"})
        check("Windows", "update window settings", s == 200 and u["font_size"] == 18)
        s, r = call("DELETE", f"/api/windows/{w['id']}")
        check("Windows", "delete window", s == 200)
        s, pr = call("GET", "/api/profiles")
        check("Windows", "built-in layouts include Combined Chat", "Combined Chat" in pr["builtin"])
        s, mo = call("GET", "/api/monitors")
        check("Windows", "monitor list", s == 200 and len(mo) >= 1)
        s, pl = call("GET", "/api/chatstyle/presets")
        check("Look", "10 ready-made looks listed", s == 200 and len(pl["builtin"]) >= 10)
        s, ap = call("POST", "/api/chatstyle/apply", {"name": "Neon"})
        check("Look", "pick a ready-made look", s == 200 and ap["style"]["base"]["bg"] == "#0b0014")
        s, un = call("POST", "/api/chatstyle/undo", {})
        check("Look", "undo goes back", s == 200 and un["style"]["base"]["bg"] == "#09090a")
        s, sv = call("POST", "/api/chatstyle/save-preset", {"name": "E2E look"})
        s2, pl = call("GET", "/api/chatstyle/presets")
        check("Look", "save my own look", s == 200 and "E2E look" in [x["name"] for x in pl["mine"]])
        s, ex = call("GET", "/api/chatstyle/export")
        s2, im = call("POST", "/api/chatstyle/import", ex)
        check("Look", "export then import round trip", s == 200 and s2 == 200 and im["style"] == ex["style"])
        s, bad = call("POST", "/api/chatstyle/import", {"hello": 1})
        check("Look", "import refuses junk", s == 400)
        s, sp = call("POST", "/api/splits/apply", {"mode": "platform", "platforms": ["twitch"]})
        check("Split", "by-platform split makes two panes", s == 200 and sp["panes"]["split-a"]["filter"]["platforms"] == ["twitch"])
        s, sp = call("POST", "/api/splits/apply", {"mode": "flow"})
        check("Split", "flow split links the two halves", s == 200 and sp["panes"]["split-a"]["flow"]["order"] == 1 and sp["panes"]["split-b"]["flow"]["order"] == 0)
        s, pn = call("POST", "/api/panes/split-b", {"look": {"size": 20, "bgA": 100, "evil": 1}})
        check("Split", "each half keeps its own look (bad keys dropped)", s == 200 and pn["look"] == {"size": 20, "bgA": 100})
        s, sp = call("POST", "/api/splits/apply", {"mode": "events"})
        s2, pn = call("GET", "/api/panes/split-b")
        check("Split", "changing the split mode keeps each half's look", s == 200 and pn["look"].get("size") == 20 and pn["filter"]["kind"] == "events")
        s, g = call("POST", "/api/geom/pane-split-a", {"x": 10, "y": 20, "w": 500, "h": 400})
        s2, pa = call("GET", "/api/panes")
        check("Windows", "pop-out position is remembered", s == 200 and pa["geom"]["pane-split-a"]["w"] == 500)
        s, _ = call("GET", "/?type=chat&pane=split-a")
        check("Split", "pane page loads", s == 200)
        s, se = call("GET", "/api/setup")
        check("Setup", "setup info for the launcher", s == 200 and "sources" in se)
        s, ru = call("GET", "/api/rules")
        check("Ranking", "explainable rules + defaults", s == 200 and "question" in ru["rules"]["weights"])
        s, ln = call("GET", "/api/learning")
        check("Ranking", "learning view", s == 200)
        s, ai_ = call("GET", "/api/ai")
        check("Ranking", "AI usage view (no key: local only)", s == 200 and ai_["mode"] == "local" and not ai_["has_key"])
        s, vo = call("POST", "/api/voice/transcript", {"text": "what game is this"})
        check("Ranking", "voice suggestions disabled by default", s == 200 and vo.get("enabled") is False, vo)

        # server guard
        s, r = call("POST", "/api/settings", {"channel": "x"}, headers={"origin": "http://evil.example"})
        check("Safety", "foreign Origin write refused", s == 403)
        s, r = call("POST", "/api/settings", {"channel": "innocentpenguin_"}, headers={"origin": ""})
        check("Safety", "tokenless writer refused", s in (401, 403))
        s, r = call("POST", "/api/settings", {"channel": "innocentpenguin_"}, headers={"origin": "", "authorization": "Bearer " + TOKEN})
        check("Safety", "writer with the module token accepted", s == 200)
        try:
            req = urllib.request.Request(BASE + "/api/status", headers={"Host": "evil.example"})
            code = urllib.request.urlopen(req, timeout=5).status
        except urllib.error.HTTPError as e:
            code = e.code
        check("Safety", "non-loopback Host refused", code == 403, code)

        # bursts: 300 messages must not crash or lose the feed
        t0 = time.time()
        for i in range(300):
            inject(user=f"burst{i % 40}", text=f"burst message {i}", id=f"twitch:dev:burst{i}")
        time.sleep(3)
        s, st2 = call("GET", "/api/status")
        check("Performance", "300-message burst handled", st2["stats"]["in"] >= 280 and st2["stats"]["dropped"] == 0, st2["stats"])
        check("Performance", "queue drained", st2["queue"] == 0, st2["queue"])
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def table():
    ok = sum(1 for r in RESULTS if r[2])
    lines = ["| Area | Check | Result | Detail |", "|---|---|---|---|"]
    for area, name, passed, detail in RESULTS:
        lines.append(f"| {area} | {name} | {'PASS' if passed else '**FAIL**'} | {detail.replace('|', '/')} |")
    return ok, len(RESULTS), "\n".join(lines)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        check("Harness", "script ran to the end", False, repr(e))
    ok, total, md = table()
    print(md)
    print(f"\n{ok}/{total} passed")
    out = pathlib.Path(r"D:\PinguinoSuite\Docs\PinguinoMulti\E2E_RESULTS.md")
    out.write_text(f"# Multi end-to-end pass ({time.strftime('%Y-%m-%d %H:%M')})\n\nReal server process on a throwaway port with a throwaway data folder; nothing audible, no network, no live accounts. "
                   f"Script: `Suite/modules/multi/tests/e2e_live.py`.\n\n**{ok}/{total} passed**\n\n{md}\n", "utf-8")
    sys.exit(0 if ok == total else 1)
