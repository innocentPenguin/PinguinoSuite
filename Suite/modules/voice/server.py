# INDEX: HTTP API on 127.0.0.1:8772 (stdlib). Guards (host_ok/origin_ok/token_ok), Host polling (poll_loop, is_live), config/master/mute/speak/event/preset endpoints, chat-command, prestream, sounds, counters, control (g_control..p_control_try), review (g_reports..p_review_apply, g_incidents), router class H, main(). Related: brain.py, config.py, voicectl.py, review.py, static/index.html, module.json.
"""Pinguino Voice - talking co-host. stdlib HTTP on 127.0.0.1:8772. UI: /   API below.
Silent unless the master switch is on. Page calls are same-origin; other callers need the module/app token."""
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config as cfg
import console_log
import review as rv
import textproc
import voicectl
from brain import Brain

ROOT = Path(__file__).parent
PORT = int(os.environ.get("VOICE_PORT", "8772"))
HOST_URL = os.environ.get("VOICE_HOST_URL", "http://127.0.0.1:8770")
LISTEN_URL = os.environ.get("VOICE_LISTEN_URL", "http://127.0.0.1:8765")
START = time.time()
TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")
ROLE_RANK = {"viewer": 0, "sub": 1, "vip": 2, "mod": 3, "broadcaster": 4}

brain = None
ctl = None
reviewer = None
live = {"v": False, "t": 0}
feed = {"seq": None, "ok": None, "err": "", "last": 0, "events": 0}


def host_ok(h):
    h = (h or "").lower()
    h = h[:h.index("]") + 1] if h.startswith("[") else h.rsplit(":", 1)[0]
    return h in LOCAL_HOSTS


LOCAL_ORIGIN = re.compile(r"^http://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?$")


def origin_ok(o):
    """No Origin (a program, not a browser), a Tauri webview, or exactly a local host:port ("http://127.0.0.1.evil.com" is not local)."""
    return not o or o in TAURI_ORIGINS or bool(LOCAL_ORIGIN.match(o))


# Routes that show private text (chat that was spoken, the whole config, review reports built from transcripts). Callers need the module
# token (the core and the Host send it) or must be this module's own page in a browser; the page is served without a token (open item).
SENSITIVE_GET = {"/api/history", "/api/history.csv", "/api/export", "/api/incidents", "/api/review/report", "/api/review/reports", "/api/control", "/api/config"}


def browser_same(headers):
    """True for a request made by a page of this module itself (or a Suite webview). A browser sets these headers and a web page of another
    site cannot fake them; a local program can, so this is a speed bump for them, not a lock (token injection into the page is the real fix)."""
    host = headers.get("host") or ""
    if (headers.get("sec-fetch-site") or "").lower() == "same-origin":
        return True
    if (headers.get("origin") or "") in TAURI_ORIGINS:
        return True
    ref = headers.get("referer") or ""
    return bool(host) and ref.startswith("http://" + host + "/") and host_ok(host)


PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "via", "x-real-ip", "tailscale-user-login")
# POSTs that change settings, speak, enable spoken control or call a paid service: with a Suite token set they need that token. The page
# gets it inside its own HTML (direct loopback loads only), the core and the Host send it as a header. The other buttons (mute, stop, replay,
# preview, sound check ...) stay same-origin so a page that was loaded some other way keeps working.
TOKEN_POST = {"/api/config", "/api/preset", "/api/master", "/api/speak", "/api/event", "/api/sound-upload", "/api/sound-delete", "/api/control/enable",
              "/api/control/confirm", "/api/control/try", "/api/review/apply", "/api/test-cloud", "/api/timer-fire"}


def page_token(headers):
    """The token to hand to the page: only when the page is loaded directly on loopback (the Suite shell's frame), never through a proxy, tunnel
    or a made-up Host name. Empty = the page runs without one and the same-origin rules apply."""
    tok = os.environ.get("PINGUINO_API_TOKEN") or ""
    if not tok or not host_ok(headers.get("host")) or any(headers.get(h) is not None for h in PROXY_HEADERS):
        return ""
    return tok


def token_ok(headers):
    want = os.environ.get("PINGUINO_API_TOKEN")
    if not want:
        return False          # started outside the Suite: no token to compare with, so nobody counts as the Suite (the page still works through same-origin)
    got = headers.get("x-pinguino-token") or headers.get("authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(got.encode(), want.encode())


# ------------------------------------------------------------------ Host activity feed -> events
def _host_get(path):
    req = urllib.request.Request(HOST_URL + path)
    tok = os.environ.get("PINGUINO_MODULE_TOKEN") or os.environ.get("PINGUINO_API_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.loads(r.read())


def _host_post(path, body):
    req = urllib.request.Request(HOST_URL + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    tok = os.environ.get("PINGUINO_API_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"{}")


def is_live():
    if time.time() - live["t"] > 25:
        try:
            live["v"] = bool(_host_get("/api/live").get("live"))
        except Exception:
            pass
        live["t"] = time.time()
    return live["v"]


def review_loop():
    while True:
        try:
            reviewer.tick()
        except Exception as e:
            console_log.warn("review", f"tick failed: {str(e)[:100]}", dedupe_s=300)
        time.sleep(30)


def mic_loop(sleep=time.sleep, stop=lambda: False):
    """Speaks ONE fixed line when Listen reports a microphone problem (event 'mic_alert', OFF by default; the master switch still decides). Never reads Listen's message aloud."""
    last = None
    while not stop():
        try:
            with urllib.request.urlopen(LISTEN_URL + "/api/status", timeout=3) as r:
                a = json.loads(r.read()).get("mic_alert")
            key = (a.get("kind"), a.get("message")) if isinstance(a, dict) else None
            if key and key != last:
                brain.handle({"kind": "mic_alert", "user": "", "manual": False, "message": ""})
            last = key
        except Exception:
            pass
        sleep(10)


KIND_MAP = {"follow": "follow", "sub": "sub", "resub": "resub", "gift": "gift", "cheer": "cheer", "raid": "raid", "redeem": "redeem"}


def poll_loop():
    while True:
        try:
            d = _host_get(f"/api/activity?limit=50&since={feed['seq']}" if feed["seq"] is not None else "/api/activity?limit=1")
            if feed["seq"] is None:
                feed["seq"] = d.get("seq", 0)          # start from now: never replay old events
            else:
                for it in d.get("items", []):
                    feed["seq"] = max(feed["seq"], it.get("seq", 0))
                    k = KIND_MAP.get(it.get("kind") or it.get("type"))
                    if k:
                        feed["events"] += 1
                        brain.handle({"kind": k, "user": it.get("user", ""), "amount": it.get("amount", 0), "viewers": it.get("amount", 0), "bits": it.get("amount", 0),
                                      "tier": it.get("tier", 1), "what": it.get("what", ""), "message": it.get("message", ""), "platform": "twitch"})
            if feed["ok"] is not True:
                console_log.info("events", "connected to the Host activity feed")
            feed.update(ok=True, err="", last=time.time())
        except Exception as e:
            if feed["ok"] is not False:
                # the Host is usually still starting right after the Suite or restarting: quiet for 90 s, then one warn per 30 min; retries are silent
                late = time.time() - START > 90 and time.time() - feed.get("warned", 0) > 1800
                console_log.log("warn" if late else "debug", "events", f"Host activity feed unavailable, retrying every 2 s: {str(e)[:100]}")
                if late:
                    feed["warned"] = time.time()
            feed.update(ok=False, err=str(e)[:120], last=time.time())
        time.sleep(2.0)


# ------------------------------------------------------------------ API handlers
def g_status(h, q):
    c = brain.cfg
    return {"ok": True, "name": "PinguinoVoice", "uptime": int(time.time() - START), "state": brain.state(), "master": c["master"], "mute_until": c["mute_until"],
            "queue": len(brain.q), "speaking": brain.current["text"] if brain.current else None, "stats": brain.stats, "last_error": brain.last_error,
            "backend": getattr(brain.sapi, "name", ""), "feed": {"ok": feed["ok"], "err": feed["err"], "events": feed["events"]}, "quiet_now": textproc.in_quiet(c), "persona": c["default_persona"]}


def g_config(h, q):
    return {"config": brain.cfg, "help": cfg.HELP, "events": cfg.EVENTS, "roles": cfg.ROLES, "platforms": cfg.PLATFORMS, "effects": cfg.EFFECTS, "stingers": cfg.STINGERS}


def _locked(data):
    """Switches only their own endpoints may change: master, mute, spoken-control enable. Presets/imports/restores keep the current state."""
    data["master"], data["mute_until"] = brain.cfg["master"], brain.cfg["mute_until"]
    data["control"] = {**(data.get("control") if isinstance(data.get("control"), dict) else {}), "enabled": brain.cfg["control"]["enabled"]}
    return data


def p_config(h, b):
    c = b.get("config") if isinstance(b.get("config"), dict) else b
    c = _locked(dict(c))
    return {"ok": True, "config": brain.set_config(c)}


def p_master(h, b):
    brain.set_master(bool(b.get("on")))
    return {"ok": True, "state": brain.state()}


def p_mute(h, b):
    brain.mute(max(0, min(1440, int(b.get("minutes") or 0))))
    return {"ok": True, "state": brain.state()}


NO_VOICE_HINT = {
    "win": "No Windows voice was found. Open Windows Settings > Time & Language > Speech and add a voice, then press Refresh.",
    "dar": "No macOS voice was found. Open System Settings > Accessibility > Spoken Content > System Voice > Manage Voices and download one, then press Refresh.",
    "lin": "No voice was found. Install espeak-ng (for example: sudo apt install espeak-ng), then press Refresh."}


def _voice_problem(e):
    """A plain sentence for a speech-engine failure (shown in the page), never a traceback."""
    if not brain.sapi.voices():
        return "No voice is available yet. " + NO_VOICE_HINT.get(sys.platform[:3], NO_VOICE_HINT["lin"])
    return "The voice engine could not speak this: " + str(e)[:150]


def g_voices(h, q):
    from engine import sapi
    v = sapi.voices(refresh=q.get("refresh") == "1")
    return {"ok": bool(v), "voices": v, "backend": getattr(sapi, "name", ""), "hint": "" if v else NO_VOICE_HINT.get(sys.platform[:3], NO_VOICE_HINT["lin"])}


def p_speak(h, b):
    """Say custom text through the filters. Master/mute/quiet rules apply."""
    ev = {"kind": "say", "message": str(b.get("text") or ""), "user": str(b.get("user") or ""), "role": b.get("role"), "platform": b.get("platform"),
          "persona": b.get("persona"), "manual": True, "priority": b.get("priority")}
    return brain.handle(ev)


def p_event(h, b):
    """For Actions & Events http steps and other modules: {kind, user, amount, message, what, tier, viewers, role, platform}."""
    return brain.handle({k: b.get(k) for k in ("kind", "user", "amount", "viewers", "bits", "tier", "what", "message", "role", "platform", "persona", "live", "priority")})


def p_test_event(h, b):
    """Test button: runs a sample event through the real pipeline (needs master ON to be heard) so wording, limits and queue are the real ones."""
    kind = b.get("kind") if b.get("kind") in cfg.EVENTS else "test"
    sample = {"user": b.get("user") or "Test_Penguin42", "amount": int(b.get("amount") or {"raid": 25, "cheer": 500, "gift": 5, "resub": 6}.get(kind, 1)), "tier": 1,
              "what": "a sample reward", "message": b.get("message") or "Great stream, love the penguin!", "persona": b.get("persona") or None}
    sample["viewers"] = sample["amount"]
    return brain.handle({"kind": kind, "manual": True, **sample})


def p_preview(h, b):
    pid = str(b.get("persona") or brain.cfg["default_persona"])
    c = cfg.normalize(b["config"]) if isinstance(b.get("config"), dict) else brain.cfg
    persona = c["personas"].get(pid)
    if persona is None:
        raise ValueError("unknown persona")
    text = str(b.get("text") or "")
    if not text:
        import random
        text = textproc.render("This is {persona}. {catch}", {}, persona)
    try:
        wav, said = brain.preview(pid, text, c)
    except RuntimeError as e:
        raise ValueError(_voice_problem(e))
    return ("audio/wav", wav, {"X-Said": urllib.parse.quote(said)})


def p_stop(h, b):
    return {"ok": True, "cleared": brain.panic()}


def p_replay(h, b):
    return brain.replay()


def g_history(h, q):
    return {"history": brain.tail(max(1, min(500, int(q.get("n") or 60))))}


def g_presets(h, q):
    return {"presets": cfg.preset_list(), "backups": cfg.backups()}


def p_preset(h, b):
    op, name = b.get("op"), str(b.get("name") or "")
    if op == "save":
        return {"ok": True, "name": cfg.preset_save(name, brain.cfg)}
    if op == "load":
        data = cfg.preset_get(name)
        data = _locked(data)
        return {"ok": True, "config": brain.set_config(data)}
    if op == "delete":
        cfg.preset_delete(name)
        return {"ok": True}
    if op == "import":
        data = cfg.normalize(b.get("data"))
        data = _locked(data)
        if b.get("save_as"):
            cfg.preset_save(str(b["save_as"]), data)
        return {"ok": True, "config": brain.set_config(data)}
    if op == "restore":
        data = cfg.restore_backup(name)
        data = _locked(data)
        return {"ok": True, "config": brain.set_config(data)}
    if op == "reset":
        data = cfg.defaults()
        data = _locked(data)
        return {"ok": True, "config": brain.set_config(data)}
    raise ValueError("unknown op")


def g_export(h, q):
    c = json.loads(json.dumps(brain.cfg))
    c["master"], c["mute_until"] = False, 0
    return ("application/json", json.dumps(c, indent=2, ensure_ascii=False).encode(), {"Content-Disposition": 'attachment; filename="pinguino-voice-setup.json"'})


def role_of(b):
    """The Host sends role as a number ("0" viewer ... "2" vip, "3" mod, "4" broadcaster) plus isMod/isSub/isVip flags; tests and older callers send a name."""
    r = str(b.get("role") if b.get("role") is not None else "").strip().lower()
    if r in ROLE_RANK:
        return r
    if r.isdigit():
        n = int(r)
        return "broadcaster" if n >= 4 else "mod" if n == 3 else "vip" if n == 2 else "sub" if b.get("isSub") is True or str(b.get("isSub")).lower() == "true" else "viewer"
    if b.get("isBroadcaster") is True or (b.get("isMod") and b.get("user") and b.get("user") == b.get("channel")):
        return "broadcaster"
    return "mod" if b.get("isMod") is True else "vip" if b.get("isVip") is True else "sub" if b.get("isSub") is True else "viewer"


def p_chat_command(h, b):
    """Host module_command contract. !tts <text> (if enabled, role check) and !voice mute|unmute|stop|again (mods). Always answers silently."""
    cmd, args = str(b.get("command") or "").lower().lstrip("!"), str(b.get("args") or "").strip()
    role = role_of(b)
    user = str(b.get("user") or "")
    c = brain.cfg
    if cmd in ("tts", "speak"):   # same switch and role check; the final command name is Ivan's call
        if not c["tts"]["enabled"]:
            return {"ok": True, "say": ""}
        if b.get("redeem") is not True and ROLE_RANK.get(role, 0) < ROLE_RANK[c["tts"]["min_role"]]:     # a channel-point redeem was already paid for: anyone
            return {"ok": True, "say": ""}
        r = brain.handle({"kind": "say", "message": args, "user": user, "role": role, "platform": b.get("platform") or "twitch"})
        return {"ok": True, "say": "", "outcome": r.get("outcome")}
    if cmd == "voice" and ROLE_RANK.get(role, 0) >= ROLE_RANK["mod"]:
        sub = args.split()[0].lower() if args else ""
        if sub == "mute":
            brain.mute(10)
        elif sub == "unmute":
            brain.mute(0)
        elif sub == "stop":
            brain.panic()
        elif sub == "again":
            brain.replay()
        return {"ok": True, "say": ""}
    return {"ok": True, "say": ""}


def g_prestream(h, q):
    c, st = brain.cfg, brain.state()
    items = [{"id": "voice-master", "label": "PenguinComm Speak", "status": "pass",
              "detail": {"off": "Switched off (silent, as intended)", "on": "On", "muted": "Muted for a while", "quiet-mute": "Quiet hours (muted)", "quiet-whisper": "Quiet hours (whispering)"}.get(st, st)}]
    from engine import sapi
    v = sapi.voices()
    items.append({"id": "voice-engine", "label": "Voice engine", "status": "pass" if v else "fail", "detail": f"{len(v)} Windows voice(s)" if v else "No Windows voices found"})
    import engine as _e
    dev = c["output"]["device"]
    dev_ok = (not dev) or _e.find_device(dev) is not None
    vp = c["personas"][c["default_persona"]]
    items.append({"id": "voice-output", "label": "Voice and output", "status": "pass" if dev_ok else "warn",
                  "detail": f"{vp['name']} ({vp['engine']}: {vp['voice'] if vp['engine'] == 'sapi' else vp['cloud_voice'] or 'default'}) on " + ((dev + ("" if dev_ok else " - NOT FOUND, using default")) if dev else "the Windows default output") + f", volume {c['output']['volume']}%"})
    if c["master"] and not dev:
        items.append({"id": "voice-loop", "label": "Bot voice vs microphone", "status": "warn", "detail": "Plays on the default speakers: Listen's mic may hear it. Use headphones or pick another output."})
    items.append({"id": "voice-events", "label": "Event feed (Host)", "status": "pass" if feed["ok"] else "warn", "detail": "connected" if feed["ok"] else (feed["err"] or "waiting for the Host")})
    import engine
    used = [e for e in ("openai", "elevenlabs") if any(p["engine"] == e for p in c["personas"].values())]
    if c["cloud"]["allow"] and used:
        miss = [e for e in used if not engine.cloud.has_key(e)]
        items.append({"id": "voice-cloud", "label": "Cloud voices", "status": "warn" if miss else "pass",
                      "detail": ("key missing for " + ", ".join(miss) + ": " + ", ".join(engine.KEY_NAMES[e] for e in miss) + " (Windows voice is used instead)") if miss else "keys present"})
    cc = c["control"]
    items.append({"id": "voice-control", "label": "Spoken control (game/title/timeout)", "status": "pass" if not cc["enabled"] or ctl.src.get("ok") else "warn",
                  "detail": "off (as intended)" if not cc["enabled"] else ("listening for '" + cc["wake_words"][0] + "'" + ("" if cc["require_confirm"] else " - NO confirm step") if ctl.src.get("ok") else "cannot read Listen: " + (ctl.src.get("err") or "waiting"))})
    items.append({"id": "voice-review", "label": "Hourly review", "status": "pass", "detail": ("on - last report " + time.strftime("%H:%M", time.localtime(reviewer.last["ts"]))) if c["review"]["enabled"] and reviewer.last["ts"] else ("on, waiting for the stream" if c["review"]["enabled"] else "off")})
    items.append({"id": "voice-queue", "label": "Speech queue", "status": "pass" if len(brain.q) < c["queue"]["max_queue"] else "warn", "detail": f"{len(brain.q)} waiting"})
    bad = brain.last_error and brain.stats["errors"]
    items.append({"id": "voice-errors", "label": "Speech errors", "status": "warn" if bad else "pass", "detail": brain.last_error if bad else "none"})
    worst = "fail" if any(i["status"] == "fail" for i in items) else "warn" if any(i["status"] == "warn" for i in items) else "pass"
    return {"status": worst, "items": items}


def p_soundcheck(h, b):
    origin = h.headers.get("origin") or ""
    if not origin or origin.split("://", 1)[-1] != h.headers.get("host"):
        raise ValueError("Sound check only works from the Speak page button")
    import engine
    if not engine.devices() and (sys.platform != "win32" or brain.cfg["output"]["device"]):
        raise ValueError("No audio output device was found on this computer, so there is nothing to play on. Plug in or enable speakers/headphones.")
    try:
        return brain.soundcheck()
    except RuntimeError as e:
        raise ValueError(_voice_problem(e))


def g_intervals(h, q):
    since = float(q.get("since") or 0)
    now = time.time()
    return {"now": now, "speaking": bool(brain.current) or brain.player.busy, "intervals": [[a, b] for a, b in list(brain.intervals) if b >= since]}


ROUTING_PLAN = [("voice", "Bot voice", "Voicemeeter AUX Input", "Voicemeeter is not installed or not running. Use 'CABLE In 16ch' instead (music then stays on 'CABLE Input')."),
                ("music", "Music", "CABLE Input", "Install VB-Cable (vb-audio.com/Cable) and restart the PC, or leave the music on the default output.")]


def g_routing_check(h, q):
    """Read-only: which output devices exist, whether the planned routing devices are there and whether the chosen Play-on device resolves. Plays nothing."""
    import engine
    raw = engine._raw_outputs()
    names = [d["name"] for d in engine.dedupe_devices(raw)]
    checks = []
    for cid, label, want, fix in ROUTING_PLAN:
        i = engine.pick_device(want, raw)
        found = next((e["name"] for e in raw if e["index"] == i), "") if i is not None else ""
        checks.append({"id": cid, "label": label, "want": want, "found": bool(found), "device": found, "status": "pass" if found else "warn",
                       "detail": f"{label}: '{found}' is available." if found else f"{label}: no output called '{want}' was found. {fix}"})
    dev = str(brain.cfg["output"]["device"] or "")
    if not names:
        po = {"id": "play_on", "label": "Play on", "want": dev, "found": False, "device": "", "status": "fail",
              "detail": "No audio output device was found on this computer, so Speak cannot play anything. Plug in or enable speakers/headphones."}
    elif not dev:
        po = {"id": "play_on", "label": "Play on", "want": "", "found": True, "device": "", "status": "pass",
              "detail": "Play on is 'System default': Speak uses the system output, one shared volume. Pick the planned voice device for a separate stream fader."}
    else:
        i = engine.pick_device(dev, raw)
        found = next((e["name"] for e in raw if e["index"] == i), "") if i is not None else ""
        po = {"id": "play_on", "label": "Play on", "want": dev, "found": bool(found), "device": found, "status": "pass" if found else "fail",
              "detail": f"Play on '{dev}' resolves to '{found}'." if found else f"Play on is '{dev}', but no such output exists right now. Speak will use the system default instead. Pick another device or start the program that provides it."}
    checks.append(po)
    worst = "fail" if any(c["status"] == "fail" for c in checks) else "warn" if any(c["status"] == "warn" for c in checks) else "pass"
    return {"status": worst, "devices": names, "checks": checks}


def g_devices(h, q):
    import engine
    d = engine.devices()
    return {"devices": d, "current": brain.cfg["output"]["device"],
            "hint": "" if d else "No audio output device was found on this computer. Plug in or enable speakers/headphones; until then Speak cannot play anything (previews inside this page still work)."}


def p_test_cloud(h, b):
    import engine
    eng = b.get("engine")
    if eng not in engine.KEY_NAMES:
        raise ValueError("engine must be openai or elevenlabs")
    return engine.cloud.test(eng)


def p_timer_fire(h, b):
    for t in brain.cfg["timers"]:
        if t["id"] == b.get("id"):
            return brain.fire_timer(t)
    raise ValueError("no such timer")


def g_integrations(h, q):
    import engine
    c = brain.cfg
    items = [{"id": "voice-engine", "name": "Windows voices (SAPI)", "group": "Voice", "status": "connected" if engine.sapi.voices() else "error",
              "detail": f"{len(engine.sapi.voices())} voice(s) installed"}]
    for eng, label in (("openai", "OpenAI voices"), ("elevenlabs", "ElevenLabs voices")):
        used = any(p["engine"] == eng for p in c["personas"].values())
        has = engine.cloud.has_key(eng)
        st = "off" if not c["cloud"]["allow"] else ("connected" if has else "needs_auth") if used else "off"
        items.append({"id": "voice-" + eng, "name": label, "group": "Voice", "status": st,
                      "detail": ("cloud voices are off (nothing leaves this PC)" if not c["cloud"]["allow"] else "in use" if used else "not used by any persona") + ("" if has else "; key missing: add " + engine.KEY_NAMES[eng] + " in Integrations > Key vault"),
                      "test": "/api/test-cloud"})
    items.append({"id": "voice-events", "name": "Host event feed", "group": "Voice", "status": "connected" if feed["ok"] else "unknown", "detail": "follows, subs and raids arrive from the Host"})
    return {"items": items}


def _sounds_dir():
    d = cfg.path("sounds")
    d.mkdir(exist_ok=True)
    return d


def g_sounds(h, q):
    return {"sounds": sorted(f.name for f in _sounds_dir().glob("*.wav"))}


def p_sound_upload(h, b):
    """{name, data(base64 WAV)}: 2 MB max, .wav only, file name sanitised (no paths)."""
    import base64
    import re
    name = re.sub(r"[^\w .()-]", "", os.path.basename(str(b.get("name") or "sound.wav")))[:60]
    if not name.lower().endswith(".wav"):
        name += ".wav"
    name = cfg.dev_safe(name[:-4].rstrip(" .") or "sound") + ".wav"          # CON.wav / NUL.wav / trailing dots are not files on Windows
    raw = base64.b64decode(str(b.get("data") or ""), validate=False)
    if not (0 < len(raw) <= 2_000_000):
        raise ValueError("sound must be under 2 MB")
    import engine
    try:
        engine.wav_to_np(raw)
    except Exception:
        raise ValueError("not a readable WAV file")
    (_sounds_dir() / name).write_bytes(raw)
    return {"ok": True, "name": name, "stinger": "file:" + name}


def p_sound_delete(h, b):
    import os as _os
    f = _sounds_dir() / _os.path.basename(str(b.get("name") or ""))
    if f.is_file() and f.suffix.lower() == ".wav":
        f.unlink()
    return {"ok": True}


def p_sound_play_preview(h, b):
    import engine
    name = str(b.get("name") or "")
    a = engine.load_sound(name, _sounds_dir())
    if not len(a):
        raise ValueError("sound not found or unreadable")
    return ("audio/wav", engine.np_to_wav(a * (brain.cfg["output"]["volume"] / 100.0)), {})


def g_counters(h, q):
    c = brain._counters()
    return {"day": c["day"], "daily": c["daily"], "total": c["total"]}


def p_counters_reset(h, b):
    brain.reset_counters()
    return {"ok": True}


def g_history_csv(h, q):
    import csv
    import io
    bio = io.StringIO()
    w = csv.writer(bio)
    w.writerow(["time", "event", "user", "result", "detail", "persona", "text"])
    for r in reversed(brain.tail(500)):
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])), r.get("kind", ""), r.get("user", ""), r.get("outcome", ""), r.get("detail", ""), r.get("persona", ""), r.get("text", "")])
    return ("text/csv", bio.getvalue().encode("utf-8-sig"), {"Content-Disposition": 'attachment; filename="speak-history.csv"'})


def g_control(h, q):
    return {"ok": True, **ctl.state(), "help": cfg.HELP}


def p_control_enable(h, b):
    c = dict(brain.cfg)
    c["control"] = {**c["control"], "enabled": bool(b.get("on"))}
    brain.cfg = cfg.save(c, backup=False)
    console_log.info("control", f"spoken control {'ON' if b.get('on') else 'OFF'}")
    return {"ok": True, **ctl.state()}


def p_control_confirm(h, b):
    return {"ok": True, "result": ctl.confirm(by="page")}


def p_control_cancel(h, b):
    return {"ok": True, "result": ctl.cancel(by="page")}


def p_control_try(h, b):
    """Rehearse a sentence without acting: what would be understood, and would it pass the checks? ({text})"""
    text = str(b.get("text") or "")[:300]
    rest = voicectl.strip_wake(text, brain.cfg["control"]["wake_words"])
    if rest is None:
        return {"ok": True, "understood": False, "why": "no wake word at the start"}
    intent = voicectl.parse(rest)
    if not intent:
        return {"ok": True, "understood": False, "why": "no command I know"}
    if intent.get("control"):
        return {"ok": True, "understood": True, "intent": intent}
    ok, why, intent = ctl.check(intent)
    return {"ok": True, "understood": True, "intent": intent, "allowed": ok and bool(brain.cfg["control"]["allow"].get(intent["action"])), "why": why, "summary": ctl.summary(intent) if ok else ""}


def g_reports(h, q):
    return {"ok": True, "reports": rv.list_reports(), "last": reviewer.last, "enabled": brain.cfg["review"]["enabled"], "live": is_live()}


def g_report(h, q):
    return {"ok": True, "report": rv.get_report(q.get("id", ""))}


def p_review_run(h, b):
    m = b.get("minutes")
    return {"ok": True, "report": reviewer.run(minutes=max(5, min(720, int(m))) if m else 60, reason="manual")}


def p_review_apply(h, b):
    new = rv.apply_suggestion(b.get("set") if isinstance(b.get("set"), dict) else {}, brain.cfg)
    return {"ok": True, "config": brain.set_config(_locked(new))}


def g_incidents(h, q):
    return {"ok": True, "incidents": [r for r in rv.read_jsonl(cfg.path("incidents.jsonl"), 0, 4e9, tail=200)][-50:]}


def g_help(h, q):
    return {"help": cfg.STATUS_HELP, "settings": cfg.HELP}


def g_selftest(h, q):
    """Does the engine work end to end? Synthesises a short line (no playback)."""
    t = time.time()
    try:
        wav, _ = brain.preview(brain.cfg["default_persona"], "Test.")
        return {"ok": True, "ms": int((time.time() - t) * 1000), "bytes": len(wav)}
    except Exception as e:
        return {"ok": False, "error": ("No voice is available yet: " + NO_VOICE_HINT.get(sys.platform[:3], NO_VOICE_HINT["lin"])) if not brain.sapi.voices() else "The voice engine failed: " + str(e)[:150]}


GET = {"/api/speech-intervals": g_intervals, "/api/sounds": g_sounds, "/api/counters": g_counters, "/api/history.csv": g_history_csv, "/api/devices": g_devices, "/api/routing-check": g_routing_check, "/api/integrations": g_integrations, "/api/status": g_status, "/api/config": g_config, "/api/voices": g_voices, "/api/history": g_history, "/api/presets": g_presets, "/api/export": g_export,
       "/api/control": g_control, "/api/review/reports": g_reports, "/api/review/report": g_report, "/api/incidents": g_incidents, "/api/prestream": g_prestream, "/api/help": g_help, "/api/selftest": g_selftest}
POST = {"/api/control/enable": p_control_enable, "/api/control/confirm": p_control_confirm, "/api/control/cancel": p_control_cancel, "/api/control/try": p_control_try, "/api/review/run": p_review_run, "/api/review/apply": p_review_apply, "/api/soundcheck": p_soundcheck, "/api/sound-upload": p_sound_upload, "/api/sound-delete": p_sound_delete, "/api/sound-preview": p_sound_play_preview, "/api/counters-reset": p_counters_reset, "/api/test-cloud": p_test_cloud, "/api/timer-fire": p_timer_fire, "/api/config": p_config, "/api/master": p_master, "/api/mute": p_mute, "/api/speak": p_speak, "/api/event": p_event, "/api/test-event": p_test_event,
        "/api/preview": p_preview, "/api/stop": p_stop, "/api/replay": p_replay, "/api/preset": p_preset, "/api/chat-command": p_chat_command}
PAGES = {"/": "static/index.html"}
OPEN_POST = {"/api/chat-command"}      # local bots (Host) with no Origin may call this one: it has its own role checks and is silent in chat


class Server(ThreadingHTTPServer):
    """A client that hangs up mid-request is normal; log one line, not a traceback."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, BrokenPipeError)):
            print("client dropped:", type(exc).__name__, flush=True)
            return
        super().handle_error(request, client_address)


MAX_BODY = 4_000_000


class TooLarge(Exception):
    pass


class H(BaseHTTPRequestHandler):
    server_version = "PinguinoVoice"
    protocol_version = "HTTP/1.1"
    timeout = 15           # a client that connects and sends nothing must not hold a thread for ever

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else str(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype == "text/html":          # only this page, the Suite and its webviews may frame the page: no clickjacking from another site
            self.send_header("Content-Security-Policy", "frame-ancestors 'self' http://127.0.0.1:* http://localhost:* tauri://localhost http://tauri.localhost https://tauri.localhost")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        if self.headers.get("transfer-encoding"):
            raise TooLarge("chunked bodies are not accepted")
        try:
            n = int(self.headers.get("content-length") or 0)
        except ValueError:
            n = 0
        if n >= MAX_BODY:
            left = min(n, 16_000_000)                 # read and drop it, so the client gets the 413 instead of a reset connection
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            raise TooLarge(f"body over {MAX_BODY // 1_000_000} MB")
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n > 0 else {}
            return body if isinstance(body, dict) else {}
        except ValueError:
            return {}

    def _guard(self, method, path):
        if not host_ok(self.headers.get("host")):
            self._send(403, "forbidden host", "text/plain")
            return False
        if method == "POST":
            origin = self.headers.get("origin")
            if not origin_ok(origin):
                self._send(403, "forbidden origin", "text/plain")
                return False
            same = bool(origin) and origin.split("://", 1)[-1] == self.headers.get("host")
            if path in TOKEN_POST and os.environ.get("PINGUINO_API_TOKEN"):
                same = False
            if not (same or (path in OPEN_POST and not origin) or token_ok(self.headers)):
                self._send(401, "token required", "text/plain")
                return False
        elif path in SENSITIVE_GET and not (token_ok(self.headers) or browser_same(self.headers)):
            self._send(401, "token required", "text/plain")
            return False
        return True

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if not self._guard(method, path):
            return
        try:
            if method == "GET" and path in PAGES:
                html = (ROOT / PAGES[path]).read_bytes().replace(b"__TOKEN__", page_token(self.headers).encode())
                return self._send(200, html, "text/html")
            fn = (GET if method == "GET" else POST).get(path)
            if fn is None:
                return self._send(404, {"error": "not found"})
            res = fn(self, q) if method == "GET" else fn(self, self._body())
            if isinstance(res, tuple):
                return self._send(200, res[1], res[0], res[2] if len(res) > 2 else None)
            if res is not None:
                self._send(200, res)
        except TooLarge as e:
            self._send(413, {"ok": False, "error": str(e)}, extra={"Connection": "close"})
            self.close_connection = True
        except ValueError as e:
            self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            console_log.error("server", f"{method} {path} failed: {type(e).__name__}: {e}", dedupe_s=60)
            self._send(500, {"ok": False, "error": "internal error"})


def main():
    global brain, ctl, reviewer
    brain = Brain()
    ctl = voicectl.Control(lambda: brain.cfg, _host_post, speak=lambda t: brain.handle({"kind": "say", "message": t, "manual": True, "priority": 7}),
                          overlaps=lambda a, b: any(s < b and e > a for s, e in list(brain.intervals)))
    reviewer = rv.Reviewer(lambda: brain.cfg, lambda: list(brain.history), LISTEN_URL, is_live)
    console_log.info("server", f"Pinguino Voice on 127.0.0.1:{PORT} (master {'ON' if brain.cfg['master'] else 'OFF'})")
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=voicectl.read_loop, args=(ctl, LISTEN_URL), daemon=True).start()
    threading.Thread(target=review_loop, daemon=True).start()
    threading.Thread(target=mic_loop, daemon=True).start()
    Server(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
