"""Pinguino Voice - talking co-host. stdlib HTTP on 127.0.0.1:8772. UI: /   API below.
Silent unless the master switch is on. Page calls are same-origin; other callers need the module/app token."""
import hmac
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config as cfg
import console_log
import textproc
from brain import Brain

ROOT = Path(__file__).parent
PORT = int(os.environ.get("VOICE_PORT", "8772"))
HOST_URL = os.environ.get("VOICE_HOST_URL", "http://127.0.0.1:8770")
START = time.time()
TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")
ROLE_RANK = {"viewer": 0, "sub": 1, "vip": 2, "mod": 3, "broadcaster": 4}

brain = None
feed = {"seq": None, "ok": None, "err": "", "last": 0, "events": 0}


def host_ok(h):
    h = (h or "").lower()
    h = h[:h.index("]") + 1] if h.startswith("[") else h.rsplit(":", 1)[0]
    return h in LOCAL_HOSTS


def origin_ok(o):
    return not o or o in TAURI_ORIGINS or o.startswith(tuple(f"http://{h}" for h in LOCAL_HOSTS))


def token_ok(headers):
    want = os.environ.get("PINGUINO_API_TOKEN")
    if not want:
        return True
    got = headers.get("x-pinguino-token") or headers.get("authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(got.encode(), want.encode())


# ------------------------------------------------------------------ Host activity feed -> events
def _host_get(path):
    req = urllib.request.Request(HOST_URL + path)
    tok = os.environ.get("PINGUINO_API_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.loads(r.read())


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
            "feed": {"ok": feed["ok"], "err": feed["err"], "events": feed["events"]}, "quiet_now": textproc.in_quiet(c), "persona": c["default_persona"]}


def g_config(h, q):
    return {"config": brain.cfg, "help": cfg.HELP, "events": cfg.EVENTS, "roles": cfg.ROLES, "platforms": cfg.PLATFORMS, "effects": cfg.EFFECTS, "stingers": cfg.STINGERS}


def p_config(h, b):
    c = b.get("config") if isinstance(b.get("config"), dict) else b
    c = dict(c)
    c["master"] = brain.cfg["master"]          # the master switch only changes through its own endpoint
    c["mute_until"] = brain.cfg["mute_until"]
    return {"ok": True, "config": brain.set_config(c)}


def p_master(h, b):
    brain.set_master(bool(b.get("on")))
    return {"ok": True, "state": brain.state()}


def p_mute(h, b):
    brain.mute(max(0, min(1440, int(b.get("minutes") or 0))))
    return {"ok": True, "state": brain.state()}


def g_voices(h, q):
    from engine import sapi
    v = sapi.voices(refresh=q.get("refresh") == "1")
    return {"ok": bool(v), "voices": v}


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
    wav, said = brain.preview(pid, text, c)
    return ("audio/wav", wav, {"X-Said": urllib.parse.quote(said)})


def p_stop(h, b):
    return {"ok": True, "cleared": brain.panic()}


def p_replay(h, b):
    return brain.replay()


def g_history(h, q):
    return {"history": brain.tail(int(q.get("n") or 60))}


def g_presets(h, q):
    return {"presets": cfg.preset_list(), "backups": cfg.backups()}


def p_preset(h, b):
    op, name = b.get("op"), str(b.get("name") or "")
    if op == "save":
        return {"ok": True, "name": cfg.preset_save(name, brain.cfg)}
    if op == "load":
        data = cfg.preset_get(name)
        data["master"], data["mute_until"] = brain.cfg["master"], brain.cfg["mute_until"]
        return {"ok": True, "config": brain.set_config(data)}
    if op == "delete":
        cfg.preset_delete(name)
        return {"ok": True}
    if op == "import":
        data = cfg.normalize(b.get("data"))
        data["master"], data["mute_until"] = brain.cfg["master"], brain.cfg["mute_until"]
        if b.get("save_as"):
            cfg.preset_save(str(b["save_as"]), data)
        return {"ok": True, "config": brain.set_config(data)}
    if op == "restore":
        data = cfg.restore_backup(name)
        data["master"], data["mute_until"] = brain.cfg["master"], brain.cfg["mute_until"]
        return {"ok": True, "config": brain.set_config(data)}
    if op == "reset":
        data = cfg.defaults()
        data["master"], data["mute_until"] = brain.cfg["master"], brain.cfg["mute_until"]
        return {"ok": True, "config": brain.set_config(data)}
    raise ValueError("unknown op")


def g_export(h, q):
    c = json.loads(json.dumps(brain.cfg))
    c["master"], c["mute_until"] = False, 0
    return ("application/json", json.dumps(c, indent=2, ensure_ascii=False).encode(), {"Content-Disposition": 'attachment; filename="pinguino-voice-setup.json"'})


def p_chat_command(h, b):
    """Host module_command contract. !tts <text> (if enabled, role check) and !voice mute|unmute|stop|again (mods). Always answers silently."""
    cmd, args = str(b.get("command") or "").lower().lstrip("!"), str(b.get("args") or "").strip()
    role = b.get("role") or ("broadcaster" if b.get("isMod") and b.get("user") == b.get("channel") else "mod" if b.get("isMod") else "sub" if b.get("isSub") else "viewer")
    user = str(b.get("user") or "")
    c = brain.cfg
    if cmd == "tts":
        if not c["tts"]["enabled"]:
            return {"ok": True, "say": ""}
        if ROLE_RANK.get(role, 0) < ROLE_RANK[c["tts"]["min_role"]]:
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
    items.append({"id": "voice-queue", "label": "Speech queue", "status": "pass" if len(brain.q) < c["queue"]["max_queue"] else "warn", "detail": f"{len(brain.q)} waiting"})
    bad = brain.last_error and brain.stats["errors"]
    items.append({"id": "voice-errors", "label": "Speech errors", "status": "warn" if bad else "pass", "detail": brain.last_error if bad else "none"})
    worst = "fail" if any(i["status"] == "fail" for i in items) else "warn" if any(i["status"] == "warn" for i in items) else "pass"
    return {"status": worst, "items": items}


def p_soundcheck(h, b):
    origin = h.headers.get("origin") or ""
    if not origin or origin.split("://", 1)[-1] != h.headers.get("host"):
        raise ValueError("Sound check only works from the Speak page button")
    return brain.soundcheck()


def g_intervals(h, q):
    since = float(q.get("since") or 0)
    now = time.time()
    return {"now": now, "speaking": bool(brain.current) or brain.player.busy, "intervals": [[a, b] for a, b in brain.intervals if b >= since]}


def g_devices(h, q):
    import engine
    return {"devices": engine.devices(), "current": brain.cfg["output"]["device"]}


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
    f.unlink(missing_ok=True)
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


def g_help(h, q):
    return {"help": cfg.STATUS_HELP, "settings": cfg.HELP}


def g_selftest(h, q):
    """Does the engine work end to end? Synthesises a short line (no playback)."""
    t = time.time()
    try:
        wav, _ = brain.preview(brain.cfg["default_persona"], "Test.")
        return {"ok": True, "ms": int((time.time() - t) * 1000), "bytes": len(wav)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


GET = {"/api/speech-intervals": g_intervals, "/api/sounds": g_sounds, "/api/counters": g_counters, "/api/history.csv": g_history_csv, "/api/devices": g_devices, "/api/integrations": g_integrations, "/api/status": g_status, "/api/config": g_config, "/api/voices": g_voices, "/api/history": g_history, "/api/presets": g_presets, "/api/export": g_export,
       "/api/prestream": g_prestream, "/api/help": g_help, "/api/selftest": g_selftest}
POST = {"/api/soundcheck": p_soundcheck, "/api/sound-upload": p_sound_upload, "/api/sound-delete": p_sound_delete, "/api/sound-preview": p_sound_play_preview, "/api/counters-reset": p_counters_reset, "/api/test-cloud": p_test_cloud, "/api/timer-fire": p_timer_fire, "/api/config": p_config, "/api/master": p_master, "/api/mute": p_mute, "/api/speak": p_speak, "/api/event": p_event, "/api/test-event": p_test_event,
        "/api/preview": p_preview, "/api/stop": p_stop, "/api/replay": p_replay, "/api/preset": p_preset, "/api/chat-command": p_chat_command}
PAGES = {"/": "static/index.html"}
OPEN_POST = {"/api/chat-command"}      # local bots (Host) with no Origin may call this one: it has its own role checks and is silent in chat


class H(BaseHTTPRequestHandler):
    server_version = "PinguinoVoice"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else str(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("content-length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if 0 < n < 4_000_000 else {}
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
            if not (same or (path in OPEN_POST and not origin) or token_ok(self.headers)):
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
                return self._send(200, (ROOT / PAGES[path]).read_bytes(), "text/html")
            fn = (GET if method == "GET" else POST).get(path)
            if fn is None:
                return self._send(404, {"error": "not found"})
            res = fn(self, q) if method == "GET" else fn(self, self._body())
            if isinstance(res, tuple):
                return self._send(200, res[1], res[0], res[2] if len(res) > 2 else None)
            if res is not None:
                self._send(200, res)
        except ValueError as e:
            self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            console_log.error("server", f"{method} {path} failed: {type(e).__name__}: {e}", dedupe_s=60)
            self._send(500, {"ok": False, "error": "internal error"})


def main():
    global brain
    brain = Brain()
    console_log.info("server", f"Pinguino Voice on 127.0.0.1:{PORT} (master {'ON' if brain.cfg['master'] else 'OFF'})")
    threading.Thread(target=poll_loop, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
