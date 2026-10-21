"""PinguinoSpotify - queue system for Spotify. stdlib HTTP server on 127.0.0.1:8771 (no extra dependencies).
UI: /   Overlay (OBS browser source): /overlay   API: see Docs/SPOTIFY.md
INDEX (keep in step when moving code)
What: stdlib HTTP server (127.0.0.1:8771), routes, Host/Origin/token guards, background loop.
  Guards/handler: host_ok:44, origin_ok:50, token_ok:54, H:73, do_GET:118, do_POST:121, loop:502, main:519
  GET: g_status:170, g_state:174, g_overlay:178, g_prestream:182, g_search:192, g_devices:197, g_setup:219, g_login:226, g_callback:236, g_queue_public:258, g_schema:467
  POST queue: p_add:297, p_remove:314, p_move:321, p_play_next:328, p_play_now:335, p_clear:360, p_undo:367, p_control:374, p_start:379
  POST chat/other: p_chat:384, p_chat_command:397, p_settings:293, p_preset:451, p_block:480, p_blocklist_import:489, p_site:431, p_live_auto:436, p_live_stop:440, p_test_key:424
Related: engine.py, config_schema.py, static/*.html, Docs/SPOTIFY.md (route table)
"""
import hmac
import html
import json
import os
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import console_log
import store
from engine import Engine
from site_bridge import Bridge
from queue_core import QueueError
from spotify_api import ApiError, Auth, Client, NotConnected

ROOT = Path(__file__).parent
PORT = int(os.environ.get("SPOTIFY_PORT", "8771"))
FAST_TICK = float(os.environ.get("SPOTIFY_TICK_S", "0"))     # tests only
REDIRECT = f"http://127.0.0.1:{PORT}/callback"
START = time.time()
TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")
PAGES = {"/": "static/index.html", "/overlay": "static/overlay.html",
         "/overlay/queue": "static/queue.html", "/queue": "static/queue.html", "/player": "static/player.html"}

auth = Auth()
engine = Engine(Client(auth), auth)
bridge = Bridge(engine)


def host_ok(host):
    h = (host or "").lower()
    h = h[:h.index("]") + 1] if h.startswith("[") else h.rsplit(":", 1)[0]
    return h in LOCAL_HOSTS


def origin_ok(origin):
    return not origin or origin in TAURI_ORIGINS or origin.startswith(tuple(f"http://{h}" for h in LOCAL_HOSTS))


def token_ok(headers):
    want = os.environ.get("PINGUINO_API_TOKEN")
    if not want:
        return True
    got = headers.get("x-pinguino-token") or headers.get("authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(got.encode(), want.encode())


class Quiet(ThreadingHTTPServer):
    """A client closing a keep-alive connection is normal on Windows; don't print a traceback (the Console flags those)."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError, BrokenPipeError)):
            return
        console_log.warn("server", f"request handler error: {sys.exc_info()[1]!r}", dedupe_s=60)


class H(BaseHTTPRequestHandler):
    server_version = "PinguinoSpotify"
    protocol_version = "HTTP/1.1"
    timeout = 30                      # idle keep-alive connections free their thread

    def log_message(self, *a):
        pass

    # ---- plumbing
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
            return json.loads(getattr(self, "_raw", b"") or b"{}")
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
            # /api/chat is a low-privilege viewer-command endpoint for local bots (Host/Streamer.bot): a local
            # process with no Origin header (not a web page) may call it without the module token.
            local_bot = path in ("/api/chat", "/api/chat-command") and not origin
            if not (same or local_bot or token_ok(self.headers)):
                self._send(401, "token required", "text/plain")
                return False
        return True

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        n = int(self.headers.get("content-length") or 0) if method == "POST" else 0
        if n > 1_000_000:
            self.close_connection = True          # refuse to buffer it; drop the connection so leftovers can't poison the next request
        elif n:
            self._raw = self.rfile.read(n)
        else:
            self._raw = b""
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if not self._guard(method, path):
            return
        try:
            if method == "GET" and path in PAGES:
                return self._send(200, (ROOT / PAGES[path]).read_bytes(), "text/html")
            fn = (GET if method == "GET" else POST).get(path)
            if fn is None and method == "POST" and path.startswith("/api/inbox/"):
                parts = path.split("/")
                if len(parts) == 5 and parts[4] in ("approve", "deny"):
                    engine.inbox_decide(parts[3], parts[4] == "approve")
                    return self._send(200, {"ok": True})
            if fn is None:
                return self._send(404, {"error": "not found"})
            res = fn(self, q) if method == "GET" else fn(self, self._body())
            if res is not None:
                self._send(200, res)
        except NotConnected as e:
            self._send(409, {"ok": False, "error": "not connected to Spotify", "code": "NOT_CONNECTED"})
        except QueueError as e:
            self._send(400, {"ok": False, "error": str(e)})
        except ApiError as e:
            self._send(502 if e.status != 429 else 429, {"ok": False, "error": friendly(e), "code": e.reason or str(e.status)})
        except Exception as e:     # never take the server down
            console_log.error("server", f"{method} {path} failed: {type(e).__name__}: {e}", dedupe_s=60)
            self._send(500, {"ok": False, "error": "internal error"})


def friendly(e):
    if e.reason == "NO_ACTIVE_DEVICE" or e.status == 404:
        return "No active Spotify device: open Spotify on the streaming PC and press play once."
    if e.reason == "PREMIUM_REQUIRED" or e.status == 403:
        return "Spotify Premium is required for playback control."
    return e.message or str(e)


# ---- GET routes
def g_status(h, q):
    return {"ok": True, "uptime_s": int(time.time() - START), "connected": auth.connected(), "version": engine.version}


def g_state(h, q):
    return engine.public_state()


def g_overlay(h, q):
    return engine.overlay()


def g_prestream(h, q):
    items = engine.prestream()
    st = bridge.status()
    if st["enabled"]:
        ok = st["online"]
        items.append({"id": "site", "label": "Website link", "status": "pass" if ok else "warn",
                      "detail": "site connected" if ok else (st["last_error"] or "connecting") + ("" if st["has_key"] else " (key missing)")})
    return {"ts": time.time(), "items": items}


def g_search(h, q):
    s = (q.get("q") or "").strip()
    return {"tracks": engine.resolve(s, 10) if s else []}


def g_devices(h, q):
    engine.devices = engine.api.devices()
    return {"devices": engine.devices}


def g_player_token(h, q):
    """Access token for the Web Playback SDK in /player. Guarded harder than other GETs: never cross-site, never logged, never cached."""
    sfs = (h.headers.get("sec-fetch-site") or "").lower()
    origin = h.headers.get("origin")
    if sfs in ("cross-site", "same-site") or (origin and not origin_ok(origin)):
        return h._send(403, {"ok": False, "error": "forbidden"})
    same = sfs in ("same-origin", "none") or (bool(origin) and origin.split("://", 1)[-1] == h.headers.get("host"))
    if not (same or token_ok(h.headers)) or (not same and not os.environ.get("PINGUINO_API_TOKEN")):
        return h._send(401, {"ok": False, "error": "token required"})
    if not engine.settings["player_native"]:
        return h._send(409, {"ok": False, "error": "built-in player is off", "code": "PLAYER_OFF"})
    tok = auth.access_token()
    if "streaming" not in (auth.tokens.get("scope") or "").split():
        return h._send(409, {"ok": False, "error": "reconnect Spotify once to allow the built-in player", "code": "NEEDS_REAUTH"})
    return {"ok": True, "access_token": tok, "expires_in": auth.seconds_left()}


def g_setup(h, q):
    return {"redirect_uri": REDIRECT, "client_id": auth.client_id, "connected": auth.connected(), "me": engine.me,
            "dashboard": "https://developer.spotify.com/dashboard", "port": PORT,
            "nowplaying_file": str(store.folder() / "nowplaying.txt"), "overlay_url": f"http://127.0.0.1:{PORT}/overlay",
            "token_seconds_left": auth.seconds_left()}


def g_login(h, q):
    """One-click connect: open http://127.0.0.1:8771/auth/login (from the Suite, a help panel or a bookmark)."""
    if not auth.client_id:
        return h._send(302, b"", "text/plain", {"Location": "/?setup=1"})
    try:
        return h._send(302, b"", "text/plain", {"Location": auth.begin(REDIRECT)})
    except ApiError as e:
        h._send(400, page("Cannot connect", e.message), "text/html")


def g_callback(h, q):
    if q.get("error"):
        return h._send(400, page("Spotify said no", q.get("error", "")), "text/html")
    try:
        auth.finish(q.get("code", ""), q.get("state", ""), REDIRECT)
        engine.me = None
        engine.cfg["ever_connected"] = True
        engine._save_cfg()
        engine.backoff_until = 0
        threading.Thread(target=engine.prestream, daemon=True).start()
        h._send(200, page("Connected to Spotify", "You can close this tab and go back to the Pinguino app."), "text/html")
    except ApiError as e:
        console_log.warn("auth", f"login failed: {e.message}")
        h._send(400, page("Login failed", f"{e.message}. Close this tab and press Connect again."), "text/html")


def page(title, msg):
    t, m = html.escape(str(title)), html.escape(str(msg))
    return (f"<!doctype html><meta charset=utf-8><title>{t}</title><body style='font:16px system-ui;background:#16181d;color:#eee;"
            f"display:grid;place-items:center;height:90vh'><div><h2 style='color:#ff9900'>{t}</h2><p>{m}</p></div>").encode()


def g_queue_public(h, q):
    """Read-only queue for the OBS queue widget / public page: no ids, no user roles."""
    return engine.public_queue()


GET = {"/api/queue.json": g_queue_public, "/api/status": g_status, "/api/state": g_state, "/api/overlay.json": g_overlay, "/api/prestream": g_prestream,
       "/api/search": g_search, "/api/now": lambda h, q: engine.now_info(), "/api/site": lambda h, q: bridge.status(), "/api/devices": g_devices, "/api/stats": lambda h, q: engine.stats(), "/api/song-log": lambda h, q: engine.song_log(int(q.get("limit") or 50), int(q.get("minutes") or 60)), "/api/announcements": lambda h, q: engine.announcements(int(q.get("since") or 0)), "/api/setup": g_setup, "/api/player": lambda h, q: engine.player_info(), "/api/player-token": g_player_token, "/callback": g_callback, "/auth/login": g_login}


# ---- POST routes
def p_setup(h, b):
    engine.set_client_id(b.get("client_id", ""))
    return {"ok": True, "client_id": auth.client_id}


def p_auth_start(h, b):
    url = auth.begin(REDIRECT)
    if not os.environ.get("SPOTIFY_NO_BROWSER"):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return {"ok": True, "url": url}


def p_disconnect(h, b):
    auth.disconnect()
    return {"ok": True}


def p_player_status(h, b):
    engine.player_report(b)
    return {"ok": True, "player": engine.player_info()}


def p_settings(h, b):
    return {"ok": True, "settings": engine.save_settings(b)}


def p_add(h, b):
    """{uri | query | track, where: end|next|now}  -> adds a streamer item (never filtered by viewer rules)."""
    where = b.get("where", "end")
    track = b.get("track")
    if not track:
        found = engine.resolve(b.get("uri") or b.get("query") or "", 1)
        if not found:
            raise QueueError("no song found")
        track = found[0]
    if not (isinstance(track, dict) and track.get("uri")):
        raise QueueError("bad track")
    item = engine.add_track(track, "next" if where in ("next", "now") else "end", b.get("requester", ""), "streamer")
    if where == "now":
        engine.play_now(item["id"])
    return {"ok": True, "id": item["id"]}


def p_remove(h, b):
    r = engine.queue.remove(b.get("id", ""))
    engine.persist()
    engine._bump()
    return {"ok": True, "result": r}


def p_move(h, b):
    i = engine.queue.move(b.get("id", ""), b.get("index", 0))
    engine.persist()
    engine._bump()
    return {"ok": True, "index": i}


def p_play_next(h, b):
    engine.queue.play_next(b.get("id", ""))
    engine.persist()
    engine._bump()
    return {"ok": True}


def p_play_now(h, b):
    engine.play_now(b.get("id", ""))
    return {"ok": True}


def p_shuffle(h, b):
    return {"ok": True, "shuffled": engine.shuffle_queue()}


def p_remove_user(h, b):
    return {"ok": True, "removed": engine.remove_user(str(b.get("user", "")))}


def p_add_context(h, b):
    return {"ok": True, "added": engine.add_context(str(b.get("link", "")), bool(b.get("shuffle")), int(b.get("limit") or 50))}


def p_user_preset(h, b):
    return {"ok": True, "presets": engine.save_user_preset(b.get("name", ""))}


def p_user_preset_del(h, b):
    return {"ok": True, "presets": engine.delete_user_preset(str(b.get("name", "")))}


def p_clear(h, b):
    engine.queue.clear(only_viewers=bool(b.get("only_viewers")))
    engine.persist()
    engine._bump()
    return {"ok": True}


def p_undo(h, b):
    engine.queue.undo()
    engine.persist()
    engine._bump()
    return {"ok": True}


def p_control(h, b):
    engine.control(b.get("action", ""), b.get("value"))
    return {"ok": True}


def p_start(h, b):
    engine.start_queue()
    return {"ok": True}


def p_chat(h, b):
    """Chat commands from the Host / Streamer.bot: {user, text, roles:[broadcaster|mod|vip|sub], redeem?}
    -> {handled, ok, code, reply}. Post `reply` to chat when non-empty."""
    user = str(b.get("user", "")).strip().lstrip("@")
    if not user:
        raise QueueError("user required")
    return engine.chat(user, str(b.get("text", "")), b.get("roles") or [], bool(b.get("redeem")))


ROLE_MAP = {"viewer": [], "vip": ["vip"], "sub": ["sub"], "mod": ["mod"], "broadcaster": ["broadcaster"],
            "1": [], "2": ["vip"], "3": ["mod"], "4": ["broadcaster"]}      # Streamer.bot-style numeric roles from the Host


def p_chat_command(h, b):
    """Host contract: {command, args, user, display, role, isMod, isSub, msgId} -> {ok, say, error}."""
    cmd = str(b.get("command", "")).strip().lstrip("!")
    user = str(b.get("display") or b.get("user") or "").strip().lstrip("@")
    if not cmd or not user:
        return {"ok": False, "say": "", "error": "command and user required"}
    roles = set(ROLE_MAP.get(str(b.get("role", "viewer")).lower(), []))
    if b.get("isMod"):
        roles.add("mod")
    tier = str(b.get("subTier") or "").strip().lower().lstrip("t")      # 1/2/3 or Twitch's 1000/2000/3000; 0 = not a sub
    tier = {"1000": "1", "2000": "2", "3000": "3"}.get(tier, tier)
    if b.get("isSub") or tier in ("1", "2", "3"):
        roles.add("sub")
        if tier in ("1", "2", "3"):
            roles.add("sub_t" + tier)
    if b.get("isVip"):
        roles.add("vip")
    src = str(b.get("source") or ("voice" if b.get("silent") else "chat"))[:20]
    r = engine.chat(user, f"{engine.settings['prefix']}{cmd} {b.get('args', '')}".strip(), roles, bool(b.get("redeem")))
    if not r["handled"]:
        return {"ok": False, "say": "", "error": "unknown command"}
    if cmd.lower() in ("skip", "voteskip", "blocksong"):
        console_log.info(src, f"{cmd} by {user}: {r['code']}")
    return {"ok": bool(r["ok"]), "say": "" if b.get("silent") else r["reply"][:400], "error": "" if r["ok"] else r["code"], "code": r["code"],
            "refund": bool(r.get("refund"))}


def p_test_key(h, b):
    ok, detail = bridge.test()
    if not ok:
        raise QueueError("site rejected the key or is unreachable: " + detail)
    return {"ok": True}


def p_site(h, b):
    bridge.configure(b.get("url"), b.get("key"), b.get("enabled"))
    return {"ok": True, **bridge.status()}


def p_live_auto(h, b):
    return {"ok": True, "requests_open": engine.settings["requests_open"]}      # going live never opens requests by itself


def p_live_stop(h, b):
    if engine.settings["requests_open"] and engine.settings["close_on_offline"]:
        engine.save_settings({"requests_open": False})
        console_log.info("server", "stream ended: song requests closed")
    if engine.settings["clear_on_offline"]:
        engine.queue.clear(only_viewers=True)
        engine.persist()
        engine._bump()
    return {"ok": True}


def p_preset(h, b):
    return {"ok": True, "settings": engine.apply_preset(str(b.get("name", "")))}


def p_reset(h, b):
    keys = b.get("keys")
    return {"ok": True, "settings": engine.reset_settings(keys if isinstance(keys, list) else None)}


def p_msg_preview(h, b):
    try:
        return {"ok": True, "text": engine.preview_msg(b.get("template", ""))}
    except (KeyError, ValueError, IndexError) as e:
        raise QueueError(f"bad template: {e}")


def g_schema(h, q):
    import config_schema as cs
    groups = [{"id": g["id"], "title": g["title"], "items": [
        {"key": k, "kind": kind, "default": d, "label": label, "help": hlp} for k, kind, d, label, hlp in g["items"]]} for g in cs.SCHEMA]
    return {"groups": groups, "vars": cs.VARS, "msgs": {k: {"label": v[0], "default": v[1], "help": v[2]} for k, v in cs.MSGS.items()},
            "commands": {k: {"default": v, "help": cs.COMMAND_HELP[k]} for k, v in cs.COMMANDS.items()},
            "presets": {k: {"label": v[0], "help": v[1]} for k, v in cs.PRESETS.items()},
            "user_presets": sorted(engine.cfg.get("user_presets") or {})}


GET["/api/settings/schema"] = g_schema


def p_block(h, b):
    v = str(b.get("value", "")).strip().lower()
    if not v:
        raise QueueError("value required")
    cur = engine.settings["blocklist"]
    engine.save_settings({"blocklist": cur if v in cur else cur + [v]})
    return {"ok": True}


def p_blocklist_import(h, b):
    text = str(b.get("text", ""))
    if not text.strip():
        raise QueueError("text required")
    return {"ok": True, **engine.import_blocklist(text[:200000])}


POST = {"/api/player/status": p_player_status, "/api/blocklist/import": p_blocklist_import, "/api/setup": p_setup, "/api/auth/start": p_auth_start, "/api/disconnect": p_disconnect, "/api/settings": p_settings,
        "/api/queue/add": p_add, "/api/queue/remove": p_remove, "/api/queue/move": p_move, "/api/queue/play_next": p_play_next,
        "/api/queue/play_now": p_play_now, "/api/queue/clear": p_clear, "/api/queue/shuffle": p_shuffle, "/api/queue/add_context": p_add_context, "/api/presets/save": p_user_preset, "/api/presets/delete": p_user_preset_del, "/api/queue/remove_user": p_remove_user, "/api/queue/undo": p_undo, "/api/queue/start": p_start,
        "/api/control": p_control, "/api/live/auto": p_live_auto, "/api/live/stop": p_live_stop, "/api/chat": p_chat, "/api/preset": p_preset, "/api/settings/reset": p_reset, "/api/msgs/preview": p_msg_preview, "/api/chat-command": p_chat_command, "/api/site": p_site, "/api/test-key": p_test_key, "/api/blocklist": p_block}


def loop():
    last_ready = 0
    while True:
        try:
            engine.tick()
            engine.automation_tick()
            pb = engine.pb
            near = pb and pb["track"] and (pb["track"]["duration_ms"] - pb["progress_ms"]) < 45000
            if time.time() - last_ready > 600 and auth.connected():
                last_ready = time.time()
                engine.prestream()          # refreshes `me` and keeps the token warm
        except Exception as e:
            console_log.error("engine", f"tick crashed: {type(e).__name__}: {e}", dedupe_s=30)
            near = False
        time.sleep(FAST_TICK or (1.0 if near else 2.0))


def main():
    console_log.info("server", f"PinguinoSpotify starting on 127.0.0.1:{PORT}")
    threading.Thread(target=loop, daemon=True).start()
    bridge.start()
    try:
        srv = Quiet(("127.0.0.1", PORT), H)
    except OSError as e:
        console_log.error("server", f"cannot listen on 127.0.0.1:{PORT} ({e}); is another PinguinoSpotify already running?")
        raise SystemExit(1)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.persist()
        console_log.info("server", "PinguinoSpotify stopped")


if __name__ == "__main__":
    main()
