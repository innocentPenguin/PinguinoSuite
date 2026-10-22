"""PinguinoMulti - unified chat core. REST + WS on 127.0.0.1:8766.
Run: run.bat   (UI at http://127.0.0.1:8766)

INDEX (server.py, sections by line)
  OBS widgets (/obs/{chat,activity,follow}, /api/obs/*): line 229
  Dashboard profiles (/api/dash*), viewer counts (/api/viewers): line 283
  messages/search/setup/prestream: line 361
  priority cards: line 441
  learning: line 484
  sending (one platform; Twitch plain lines via Host /api/say; 30 s duplicate guard): line 504
  Twitch moderation: line 547
  pins: line 568
  chat look (chatstyle): line 615
  panes + splits: line 706
  stream events pushed by Host: line 778
  assisted chat: line 799
  new-chatter ding / chat pop: line 850
  settings / rules: line 970
  windows / monitors / profiles: line 1024
  auth + secrets + voice: line 1116
  dev inject + /ws: line 1239
Related: obs.py (widget settings), viewers.py (live counts), host_feed.py (Host activity + /api/say), pipeline.py, store.py, panes.py, windows.py,
connectors/{twitch,discord,youtube,tiktok}.py, static/{index.html,dash.js,obs.html,obs_ui.js,chat.js,side.js,launcher.js,style.js}. Full index: Docs/PinguinoMulti/INDEX.md
"""
import asyncio
import hmac
import json
import os
import time
import webbrowser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import cards as cards_mod
import checks
import config
import learning
import chatstyle
import alert_media
import alerts as alerts_mod
import obs as obs_mod
import panes as panes_mod
import presets as presets_mod
import console_log
import help_text
import listen_bridge
import host_feed
import viewers as viewers_mod
import prestream
import voice
import secrets_store
import windows as win
from connectors.discord import Discord
from connectors.kick import Kick
from connectors.tiktok import TikTok
from connectors.twitch import Twitch
from connectors.youtube import YouTube
from models import ChatMessage
from pipeline import Inbox, Pipeline
from priority import rules as prio
from store import Store

START = time.time()


class Hub:
    def __init__(self):
        self.clients, self.loop = set(), None

    def emit(self, ev):
        ev = dict(ev, ts=time.time())
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._send(ev)))

    async def _send(self, ev):
        for ws in list(self.clients):
            try:
                await ws.send_json(ev)
            except Exception:
                self.clients.discard(ws)


hub = Hub()
store = Store()
alert_engine = alerts_mod.Engine(store, hub.emit)
cards = cards_mod.CardManager(store, hub.emit)
pipeline = Pipeline(store, cards, hub.emit)


def _alert_from_message(m):
    """stored stream event (Host feed or /api/events) -> alert engine event; test/sim items never get here as real alerts"""
    if m.event not in alerts_mod.TYPES and m.event not in ("follow",):
        return
    if m.event == "hype" and "started" not in m.text:
        return
    meta = m.meta or {}
    if meta.get("sim") or meta.get("test"):
        return
    ev = dict(meta, platform=m.platform, id=m.id, type=m.event, user=m.user, display=m.display, amount=m.amount, first_time=bool(meta.get("first_time") or m.first_time),
              refollow="refollow" in m.flags, rank_colour=meta.get("rank_colour") or m.color)
    if hub.loop:
        hub.loop.call_soon_threadsafe(alert_engine.submit, ev)


pipeline.on_event = _alert_from_message
inbox = Inbox(pipeline)
connectors = {}
shell = win.EdgeShell(f"http://127.0.0.1:{config.PORT}")


async def prestream_file_loop():
    while True:
        console_log.write_prestream(prestream.run(connectors, store, pipeline, inbox))
        await asyncio.sleep(120)


async def tick_loop():
    n = 0
    while True:
        await asyncio.sleep(1)
        cards.tick()
        n += 1
        if n % 3600 == 0:
            store.prune(config.settings()["retention_days"])


def _loop_exception(loop, ctx):
    """asyncio's last-resort handler. A browser / OBS source closing its socket raises ConnectionResetError (10054) inside the Windows
    event loop's connection_lost callback; that is the client leaving, not a fault, so it is not logged as an error."""
    exc = ctx.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return
    console_log.error("server", f"unhandled: {ctx.get('message', '')} {repr(exc or '')}", dedupe_s=60)


@asynccontextmanager
async def lifespan(app):
    hub.loop = asyncio.get_running_loop()
    hub.loop.set_exception_handler(_loop_exception)
    console_log.info("server", f"Multi started on port {config.PORT}")
    alert_engine.start()
    if alerts_mod.sync_bridge_token(os.environ.get("PINGUINO_DATA_DIR"), os.environ.get("PINGUINO_API_TOKEN")):
        console_log.info("server", "alert bridge token written for the Host (alert_bridge.json)")
    store.prune(config.settings()["retention_days"])
    _seed_defaults()
    tw = Twitch(inbox, hub.emit)
    connectors["twitch"] = tw
    dc = Discord(inbox, hub.emit)
    connectors["discord"] = dc
    yt = YouTube(inbox, hub.emit)
    connectors["youtube"] = yt
    tt = TikTok(inbox, hub.emit)
    connectors["tiktok"] = tt
    kk = Kick(inbox, hub.emit)
    connectors["kick"] = kk
    tasks = [asyncio.create_task(inbox.run()), asyncio.create_task(tick_loop()), asyncio.create_task(tw.run()),
             asyncio.create_task(dc.run()), asyncio.create_task(yt.run()), asyncio.create_task(tt.run()), asyncio.create_task(kk.run()),
             asyncio.create_task(listen_bridge.run(cards, hub.emit)),
             asyncio.create_task(host_feed.run(inbox, lambda: connectors['twitch'].describe()['status'] == 'connected')), asyncio.create_task(prestream_file_loop()), asyncio.create_task(viewers_mod.run(connectors, hub.emit))]
    yield
    console_log.info("server", "Multi stopping")
    tw.stop = dc.stop = yt.stop = tt.stop = kk.stop = True
    for t in tasks:
        t.cancel()
    for wid in list(shell.procs):
        shell.close(wid)


TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _seed_defaults():
    """First run: one saved chat window (so pop-outs have somewhere to go) and a ready split (newest in B, older rows continue in A)."""
    try:
        if not store.load_windows():
            store.save_window(win.describe_geometry(win.new_window(id="main-chat", type="chat", title="Chat", x=1400, y=40, w=520, h=980), win.list_monitors()))
        if not store.kv_get("panes"):
            store.kv_set("panes", panes_mod.build_split("flow"))
    except Exception as e:
        console_log.warn("server", f"could not save the default layout: {e}", dedupe_s=300)


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    console_log.error("server", f"{request.method} {request.url.path} failed: {type(exc).__name__}: {exc}", dedupe_s=60)
    return JSONResponse({"detail": "internal error"}, status_code=500)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8760", "http://localhost:8760", *TAURI_ORIGINS],
                   allow_methods=["*"], allow_headers=["*"])
STATIC = config.ROOT / "static"
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
alert_media.DIR.mkdir(parents=True, exist_ok=True)
app.mount("/alert-media", StaticFiles(directory=alert_media.DIR), name="alert-media")


def origin_ok(origin):
    """Local pages and the Tauri webview only; anything else is a drive-by page."""
    if not origin:
        return True
    if origin in TAURI_ORIGINS:
        return True
    return origin.startswith(tuple(f"http://{h}" for h in LOCAL_HOSTS))


def host_ok(host):
    h = (host or "").lower()
    h = h[:h.index("]") + 1] if h.startswith("[") else h.rsplit(":", 1)[0]
    return h in LOCAL_HOSTS


def token_ok(request):
    """Per-module token from the Suite (PINGUINO_API_TOKEN). Unset = standalone run, origin check only."""
    want = os.environ.get("PINGUINO_API_TOKEN")
    if not want:
        return True
    got = request.headers.get("x-pinguino-token") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if hmac.compare_digest(got.encode(), want.encode()):
        return True
    if request.url.path.startswith(alerts_mod.HOST_TOKEN_PATHS):    # the Host (alert bridge / activity feed) has its own module token
        ht = alerts_mod.host_token(os.environ.get("PINGUINO_DATA_DIR"))
        return bool(ht) and hmac.compare_digest(got.encode(), ht.encode())
    return False


@app.middleware("http")
async def local_only_writes(request: Request, call_next):
    """Anti DNS-rebinding (Host) + anti drive-by (Origin). Writes from our own page (Origin == Host, e.g. the
    embedded iframe) pass; any other writer (no Origin, or a Tauri origin) must present the module token."""
    if request.url.path == "/hook/kick":          # Kick's servers (via the site relay or a tunnel): authenticated by the RSA signature, not Origin / token / Host
        return await call_next(request)
    if not host_ok(request.headers.get("host")):
        return HTMLResponse("forbidden host", status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if not origin_ok(origin):
            return HTMLResponse("forbidden origin", status_code=403)
        same_origin = bool(origin) and origin.split("://", 1)[-1] == request.headers.get("host")
        if not same_origin and not token_ok(request):
            return HTMLResponse("token required", status_code=401)
    resp = await call_next(request)
    if request.url.path.startswith("/assets") or request.url.path in ("/", "/popout", "/obs/chat", "/obs/activity", "/obs/follow"):
        resp.headers["cache-control"] = "no-cache"     # always revalidate: a new Multi build must never show stale scripts
    return resp


def _page():
    """index.html with the shared Suite theme linked after our own styles (our values stay as the fallback)."""
    core = os.environ.get("PINGUINO_CORE_URL", "http://127.0.0.1:8760").rstrip("/")
    html = (STATIC / "index.html").read_text("utf-8")
    return HTMLResponse(html.replace("<!--THEME-->", f'<link rel="stylesheet" href="{core}/theme.css">'))


@app.get("/")
def index():
    return _page()


@app.get("/popout")
def popout():
    """Stream-safe chat for an OBS browser source/dock: public messages only (no cards, notes, composer, muted users)."""
    return _page()


# OBS browser sources: /obs/chat and /obs/activity (Synchra-compatible settings) ------------------
def _obs_get(kind):
    saved = store.kv_get("obs:" + kind, None)
    if saved is None and kind == "chat":
        saved = obs_mod.IVAN_CHAT       # first run: the look Ivan already had in Synchra
    return obs_mod.sanitize(kind, saved)


def _live_page():
    return FileResponse(STATIC / "live.html", headers={"Cache-Control": "no-store"})


@app.post("/hook/kick")
async def kick_hook(request: Request):
    """Kick webhook receiver (signature checked inside the connector). Kick must reach this over public HTTPS: see Docs/MULTISTREAM_PLAN.md."""
    kk = connectors.get("kick")
    if kk is None:
        raise HTTPException(503, "Kick connector not running")
    body = await request.body()
    if len(body) > 256 * 1024:
        raise HTTPException(413, "too large")
    code, text = await kk.ingest_webhook({k.lower(): v for k, v in request.headers.items()}, body)
    return JSONResponse({"ok": code == 200, "detail": text}, status_code=code)


@app.get("/obs/alerts")
def obs_alerts():
    return FileResponse(STATIC / "alerts.html", headers={"Cache-Control": "no-store"})


@app.get("/api/alerts")
def alerts_get():
    return {"config": alert_engine.cfg, "types": alerts_mod.TYPES, "labels": alerts_mod.LABEL, "anims": alerts_mod.ANIMS, "layouts": alerts_mod.LAYOUTS,
            "vars": alerts_mod.VARS, "fonts": list(obs_mod.FONTS), "variants": list(alerts_mod.VARIANTS), "defaults": alerts_mod.DEFAULT_TYPES,
            "status": alert_engine.status(), "log": list(alert_engine.log)[:100]}


@app.post("/api/alerts/config")
async def alerts_save(request: Request):
    b = await request.json()
    if not isinstance(b, dict) or not isinstance(b.get("config"), dict):
        raise HTTPException(400, "config object required")       # never let a malformed body reset the saved alerts to defaults
    return {"config": alert_engine.save(b["config"])}


@app.post("/api/alerts/preview")
async def alerts_preview(request: Request):
    b = await request.json()
    t = str(b.get("type") or "follow")
    if t not in alerts_mod.TYPES:
        raise HTTPException(400, "unknown alert type")
    return {"alert": alert_engine.preview(t, b.get("event"))}


@app.post("/api/alerts/test")
async def alerts_test(request: Request):
    """Queue a TEST alert (flagged; never reaches the inbox, stats, points, credits or chat). Used by the Suite UI and the Host !alert command."""
    b = await request.json()
    t = str(b.get("type") or "follow").lower()
    if t not in alerts_mod.TYPES:
        raise HTTPException(400, "unknown alert type: " + ", ".join(alerts_mod.TYPES))
    ev = alerts_mod.test_event(t, str(b.get("user") or "penguin")[:40], b.get("amount"), b.get("variant") or [], source=str(b.get("source") or "ui")[:10],
                               tier=b.get("tier"), months=b.get("months"), message=str(b.get("message") or "")[:200], level=b.get("level"))
    ok, why = alert_engine.submit(ev)
    return {"ok": ok, "queued": ok, "text": f"test {t} {why}" if ok else f"test {t} not shown: {why}", "id": ev["id"]}


@app.get("/api/alerts/media")
def alerts_media_list():
    return {"files": alert_media.listing()}


@app.post("/api/alerts/media")
async def alerts_media_upload(request: Request, name: str = ""):
    """Raw file body (Content-Type: application/octet-stream) + ?name=file.ext -> stored in the alert media library."""
    if int(request.headers.get("content-length") or 0) > alert_media.MAX_BYTES + 1024:
        raise HTTPException(413, "file too large (max 25 MB)")
    data = await request.body()
    try:
        saved = alert_media.save(name, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"name": saved, "url": "/alert-media/" + saved}


@app.post("/api/alerts/media/delete")
async def alerts_media_delete(request: Request):
    return {"ok": alert_media.delete(str((await request.json()).get("name") or ""))}


@app.post("/api/alerts/import-host")
async def alerts_import_host(request: Request):
    """Copy the Host's alert sounds into the active profile ({apply:false} = preview only, {overwrite:true} replaces existing sounds)."""
    b = await request.json()
    prof = alert_engine.cfg["profiles"][alert_engine.cfg["active"]]["types"]
    rows = alert_media.import_host(prof, apply=b.get("apply", True) is not False, overwrite=bool(b.get("overwrite")))
    if b.get("apply", True) is not False:
        alert_engine.save(alert_engine.cfg)
    return {"rows": rows}


@app.post("/api/alerts/fire")
async def alerts_fire(request: Request):
    """A REAL alert straight into the queue without a chat row (Host: intro clips, goal reached, anything not in the activity feed).
    Body: {type,user,id?,amount?,tier?,months?,message?,level?,rank_colour?,avatar?,first_time?}. Test/sim flagged items are refused here."""
    b = await request.json()
    t = str(b.get("type") or "")
    if t not in alerts_mod.TYPES:
        raise HTTPException(400, "unknown alert type")
    if b.get("test") or b.get("sim"):
        raise HTTPException(400, "test events go through /api/alerts/test")
    ev = {k: b[k] for k in ("id", "user", "display", "amount", "tier", "months", "message", "level", "rank_colour", "avatar", "first_time", "recipient", "refollow") if k in b}
    ev["type"] = t
    ok, why = alert_engine.submit(ev)
    return {"ok": ok, "queued": ok, "text": why}


@app.post("/api/alerts/testall")
async def alerts_testall():
    ids = [alert_engine.submit(alerts_mod.test_event(t, "penguin", source="ui"))[0] for t in alerts_mod.TYPES]
    return {"ok": True, "queued": sum(1 for x in ids if x), "text": f"test-all queued {sum(1 for x in ids if x)} of {len(ids)}"}


@app.post("/api/alerts/stress")
async def alerts_stress(request: Request):
    n = int(min(200, max(1, alerts_mod._int((await request.json()).get("n"), 30))))
    import random
    ok = 0
    for i in range(n):
        t = random.choice(alerts_mod.TYPES)
        ok += 1 if alert_engine.submit(alerts_mod.test_event(t, f"viewer{i}", random.randint(1, 50), source="ui"))[0] else 0
    return {"ok": True, "queued": ok, "text": f"stress: {ok} of {n} queued"}


@app.post("/api/alerts/control")
async def alerts_control(request: Request):
    a = str((await request.json()).get("action") or "")
    if a == "skip":
        alert_engine.skip()
    elif a == "clear":
        return {"ok": True, "cleared": alert_engine.clear(), "text": "queue cleared"}
    elif a in ("pause", "resume"):
        alert_engine.pause(a == "pause")
    elif a.startswith("profile:") and a[8:] in alert_engine.cfg["profiles"]:
        alert_engine.save(dict(alert_engine.cfg, active=a[8:]))
    else:
        raise HTTPException(400, "unknown action")
    return {"ok": True, "text": a + " done", "status": alert_engine.status()}


@app.get("/obs/poll")
def obs_poll():
    return _live_page()


@app.get("/obs/predict")
def obs_predict():
    return _live_page()


@app.get("/obs/hype")
def obs_hype():
    return _live_page()


@app.get("/api/live-state")
async def live_state():
    """Current poll / prediction / hype train from the Host (null when none or the Host is down)."""
    d = await host_feed.live_state()
    return {"poll": d.get("poll"), "prediction": d.get("prediction"), "hype": d.get("hype")}


@app.get("/obs/{kind}")
def obs_page(kind: str):
    if kind not in obs_mod.KINDS:
        return HTMLResponse("not found", status_code=404)
    return HTMLResponse((STATIC / "obs.html").read_text("utf-8").replace("__KIND__", kind))


@app.get("/api/obs/{kind}")
def obs_settings(kind: str):
    if kind not in obs_mod.KINDS:
        return JSONResponse({"detail": "unknown widget"}, status_code=404)
    return {"settings": _obs_get(kind), "defaults": obs_mod.DEFAULTS[kind], "fonts": list(obs_mod.FONTS), "sizes": obs_mod.SIZES,
            "muted": sorted(pipeline.rules["muted"]), "presets": [{"name": n, "desc": p["desc"], "settings": obs_mod.sanitize(kind, p["settings"])}
                                                                  for n, p in obs_mod.PRESETS[kind].items()]}


@app.post("/api/obs/{kind}")
async def obs_save(kind: str, request: Request):
    if kind not in obs_mod.KINDS:
        return JSONResponse({"detail": "unknown widget"}, status_code=404)
    b = await request.json()
    st = obs_mod.sanitize(kind, b.get("settings"))
    store.kv_set("obs:" + kind, st)
    hub.emit({"type": "obs.changed", "kind": kind, "settings": st})
    return {"settings": st}


@app.post("/api/obs/chat/import")
async def obs_import(request: Request):
    b = await request.json()
    st, err = obs_mod.from_synchra(b.get("doc"))
    if err:
        return JSONResponse({"detail": err}, status_code=400)
    if b.get("save", True):
        store.kv_set("obs:chat", st)
        hub.emit({"type": "obs.changed", "kind": "chat", "settings": st})
    return {"settings": st}


@app.get("/api/obs/{kind}/export")
def obs_export(kind: str):
    if kind not in obs_mod.KINDS:
        return JSONResponse({"detail": "unknown widget"}, status_code=404)
    return obs_mod.to_synchra(kind, _obs_get(kind))


# Dashboard layouts ("Profile" menu), stored on the server so every window/PC sees the same ones ---------
DASH_DEFAULTS = {"Default": {"panels": ["activity", "chat"], "widths": [50, 50], "src": "all"}, "Chat only": {"panels": ["chat"], "widths": [100], "src": "all"},
                 "Wide chat": {"panels": ["activity", "chat"], "widths": [30, 70], "src": "all"}}


def _dash_layout(o):
    o = o if isinstance(o, dict) else {}
    panels = [p for p in (o.get("panels") or []) if p in ("activity", "chat")][:2] or ["activity", "chat"]
    widths = [min(90, max(10, int(w))) for w in (o.get("widths") or [])][:len(panels)]
    widths += [50] * (len(panels) - len(widths))
    src = o.get("src") if o.get("src") in ("all", *obs_mod.PROVIDERS) else "all"
    fs = {k: min(40, max(10, int((o.get("fs") or {}).get(k) or 14))) for k in ("activity", "chat")}
    sp = o.get("split") if isinstance(o.get("split"), dict) else {}
    split = {"on": bool(sp.get("on")), "dir": "col" if sp.get("dir") == "col" else "row",
             "a": sp.get("a") if sp.get("a") in ("all", *obs_mod.PROVIDERS) else "all", "b": sp.get("b") if sp.get("b") in ("all", *obs_mod.PROVIDERS) else "all",
             "kind": sp.get("kind") if sp.get("kind") in ("source", "flow", "events") else "source"}
    return {"panels": panels, "widths": widths, "src": src, "fs": fs, "split": split}


def _dash_state():
    d = store.kv_get("dash", None) or {}
    profs = dict(DASH_DEFAULTS)
    profs.update({k: _dash_layout(v) for k, v in (d.get("profiles") or {}).items()})
    active = d.get("active") if d.get("active") in profs else "Default"
    return {"profiles": profs, "active": active, "builtin": list(DASH_DEFAULTS)}


@app.get("/api/dash")
def dash_get():
    return _dash_state()


@app.post("/api/dash")
async def dash_set(request: Request):
    b = await request.json()
    name = str(b.get("name") or "").strip()[:40]
    if not name:
        return JSONResponse({"detail": "name required"}, status_code=400)
    d = store.kv_get("dash", None) or {"profiles": {}}
    d.setdefault("profiles", {})[name] = _dash_layout(b.get("layout"))
    if b.get("activate", True):
        d["active"] = name
    store.kv_set("dash", d)
    return _dash_state()


@app.delete("/api/dash/{name}")
def dash_delete(name: str):
    d = store.kv_get("dash", None) or {"profiles": {}}
    d.get("profiles", {}).pop(name, None)
    if d.get("active") == name:
        d["active"] = "Default"
    store.kv_set("dash", d)
    return _dash_state()


@app.post("/api/dash/active")
async def dash_active(request: Request):
    b = await request.json()
    d = store.kv_get("dash", None) or {"profiles": {}}
    d["active"] = b.get("name")
    store.kv_set("dash", d)
    return _dash_state()


@app.get("/api/viewers")
def viewers_get():
    return {"counts": viewers_mod.counts}


@app.get("/api/status")
def status():
    return {"ok": True, "uptime_s": int(time.time() - START), "stats": pipeline.stats,
            "queue": inbox.q.qsize(), "connectors": [c.describe() for c in connectors.values()],
            "mode": config.settings()["priority_mode"],
            "twitch_connect_url": (secrets_store.get("site_url") or "https://innocentpenguin.com") + "/auth/twitch/login?multi=1"}


# messages / search ---------------------------------------------------
@app.get("/api/setup")
def setup_info():
    """Non-secret setup state for the launcher: which secrets exist (booleans only) + plain settings."""
    s = config.settings()
    keys = ("priority_mode", "ai_provider", "ai_model", "ai_daily_cap_usd", "voice_enabled", "discord_channels",
            "tiktok_enabled", "tiktok_user", "kick_enabled", "kick_channel", "kick_chatroom_id", "channel", "bot_accounts", "my_names")
    return {"settings": {k: s[k] for k in keys},
            "has": {"discord": bool(secrets_store.get("discord_token")), "youtube": bool(secrets_store.get("youtube_token")),
                    "ai": bool(secrets_store.get("ai_key")), "twitch": bool(secrets_store.get("twitch_tokens"))},
            "sources": {k: secrets_store.source(k) for k in ("twitch_tokens", "discord_token", "youtube_token", "ai_key")}}


@app.get("/api/prestream")
def prestream_checks():
    """Readiness for the Pinguino Console: {ts, items:[{id,label,status pass|warn|fail,detail}]}."""
    return {"ts": time.time(), "items": prestream.run(connectors, store, pipeline, inbox)}


_ISTATE = {"connected": "connected", "needs_auth": "needs_auth", "error": "error", "disabled": "off", "disconnected": "off",
           "connecting": "unknown", "reconnecting": "error", "waiting": "unknown"}


@app.get("/api/integrations")
def integrations():
    """Items for the Suite's Integrations hub (never contains secrets)."""
    out = []
    for iid, name, plat, label in help_text.INTEGRATIONS:
        c = connectors.get(plat)
        d = c.describe() if c else {"status": "disconnected", "detail": ""}
        it = {"id": iid, "name": name, "group": "Chat platforms", "status": _ISTATE.get(d["status"], "unknown"),
              "detail": (d.get("detail") or "")[:160], "test": f"/api/test/{plat}", "help": help_text.for_item("conn-" + plat)}
        if label:
            it.update(connect_url=(secrets_store.get("site_url") or "https://innocentpenguin.com") + "/auth/twitch/login?multi=1",
                      connect_label=label)
        out.append(it)
    return {"items": out}


@app.post("/api/test/{platform}")
def test_platform(platform: str):
    c = connectors.get(platform)
    if not c:
        raise HTTPException(404, "unknown platform")
    d = c.describe()
    if d["status"] != "connected":
        raise HTTPException(409, f"{d['label']} is {d['status']}: {d.get('detail') or ''}"[:200])
    return {"ok": True, "detail": d.get("detail", "")}


@app.get("/api/help/all")
def help_all():
    return {"module": "multi", "items": help_text.HELP, "secrets": help_text.SECRETS}


@app.get("/api/messages")
def messages(limit: int = 200, platform: str = "", min_tier: str = "", before: float = 0):
    return store.recent(min(limit, 1000), platform or None, min_tier or None, before or None)


@app.get("/api/search")
def search(q: str):
    return store.search(q) if q.strip() else []


@app.get("/api/viewer/{platform}/{user_id}")
def viewer(platform: str, user_id: str):
    return {"count": store.user_count(platform, user_id), "history": store.user_history(platform, user_id, 30)}


@app.get("/api/messages/{mid:path}/explain")
def explain(mid: str):
    m = store.get_message(mid)
    if not m:
        raise HTTPException(404)
    msg = ChatMessage(**{k: m[k] for k in ChatMessage.__dataclass_fields__ if k in m})
    d = prio.score(msg, prio.Context(user_count=store.user_count(msg.platform, msg.user_id)), pipeline.rules)
    return d.to_dict()


# cards ---------------------------------------------------------------
@app.get("/api/cards")
def get_cards():
    return cards.view()


@app.get("/api/recap")
def recap():
    """Unanswered recap for after the stream: open + missed + snoozed cards, highest score first."""
    r = cards.recap()
    return {"count": len(r), "cards": r}


@app.post("/api/cards/{cid:path}/{action}")
async def card_action(cid: str, action: str, request: Request):
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    fn = {"answer": lambda: cards.answer(cid, body.get("via", "manual")), "dismiss": lambda: cards.dismiss(cid),
          "reopen": lambda: cards.reopen(cid), "snooze": lambda: cards.snooze(cid, body.get("seconds", 300)),
          "tier": lambda: cards.set_tier(cid, body.get("tier", "medium"))}.get(action)
    if not fn:
        raise HTTPException(400, "unknown action")
    c = fn()
    if not c:
        raise HTTPException(404)
    if action in ("answer", "dismiss", "tier"):
        await asyncio.to_thread(learning.refresh, store)
    return c


@app.post("/api/hotkey/{action}")
async def hotkey(action: str):
    """Act on the top open card (highest score, newest). Target for global hotkeys, Stream Deck, AutoHotkey."""
    if action not in ("answer", "dismiss", "snooze"):
        raise HTTPException(400, "unknown action")
    opened = sorted((c for c in cards.cards.values() if c["state"] == "open"), key=lambda c: (-c["score"], -c["created"]))
    if not opened:
        return {"ok": False, "reason": "no open cards"}
    cid = opened[0]["id"]
    c = cards.answer(cid, "hotkey") if action == "answer" else cards.dismiss(cid) if action == "dismiss" else cards.snooze(cid)
    await asyncio.to_thread(learning.refresh, store)
    return {"ok": True, "card": c["id"], "state": c["state"]}


# learning (bounded, explainable, resettable) -----------------------------
@app.get("/api/learning")
def get_learning():
    rep = learning.refresh(store)
    return {"enabled": store.kv_get("learning_enabled", True) is not False,
            "min_evidence": learning.MIN_EVIDENCE, "rules": rep, "applied": store.kv_get("learned", {})}


@app.post("/api/learning/reset")
def reset_learning():
    learning.reset(store)
    return {"ok": True}


@app.post("/api/learning/enabled")
async def set_learning(request: Request):
    store.kv_set("learning_enabled", bool((await request.json()).get("enabled", True)))
    return get_learning()


# sending (always to ONE explicit platform; never broadcast) --------------
_RECENT_SENDS = {}
@app.post("/api/send")
async def send(request: Request):
    b = await request.json()
    platform, text = b.get("platform"), (b.get("text") or "").strip()
    if platform not in connectors:
        raise HTTPException(400, "choose one platform that supports sending (no broadcast to all)")
    if not text or len(text) > 500:
        raise HTTPException(400, "empty or too long")
    conn = connectors[platform]
    if not conn.capabilities.get("send"):
        raise HTTPException(400, f"{platform} is read-only")
    reply_to = b.get("reply_to") or None
    if reply_to and not conn.capabilities.get("reply"):
        reply_to = None
    now = time.time()                                   # Ivan's rule: never send the same line twice (identical text within 30 s is dropped; a failed send is not retried elsewhere)
    for k in [k for k, t in _RECENT_SENDS.items() if now - t > 30]:
        del _RECENT_SENDS[k]
    key = (platform, " ".join(text.lower().split()))
    if key in _RECENT_SENDS:
        return {"ok": True, "duplicate": True, "id": ""}
    _RECENT_SENDS[key] = now
    if platform == "twitch" and not reply_to:           # plain lines go through the Host so its global duplicate guard covers every bot
        r = await host_feed.say(text)
        if r is not None:
            if not r.get("ok"):
                _RECENT_SENDS.pop(key, None)             # refused, nothing went out: the same line may be tried again
                raise HTTPException(502, str(r.get("via") or "Host could not send"))
            return {"ok": True, "id": "", "duplicate": bool(r.get("duplicate")), "via": r.get("via")}
    try:
        mid = await conn.send(text, reply_to)
    except Exception as e:
        _RECENT_SENDS.pop(key, None)                     # the platform rejected it (not a timeout): allow a retry
        raise HTTPException(502, str(e))
    me = conn.user["login"] if getattr(conn, "user", None) else "me"
    own = ChatMessage(id=mid, platform=platform, channel=config.settings()["channel"],
                      user_id=conn.user["user_id"] if getattr(conn, "user", None) else "me", user=me, display=me,
                      text=text, ts=time.time(), reply_to=reply_to or "", is_self=True)
    pipeline.ingest(own)
    if b.get("card_id"):
        cards.answer(b["card_id"], via="typed")
    return {"ok": True, "id": mid}


# moderation (Twitch only, explicit action on one message/user; audited) ---
@app.post("/api/mod/{action}")
async def mod_action(action: str, request: Request):
    b = await request.json()
    m = store.get_message(b.get("message_id", ""))
    if not m:
        raise HTTPException(404, "unknown message")
    conn = connectors.get(m["platform"])
    if m["platform"] != "twitch" or not hasattr(conn, "moderate"):
        raise HTTPException(400, f"quick moderation is not available for {m['platform']}")
    try:
        await conn.moderate(action, user_id=m["user_id"], message_id=m["id"].split(":")[-1],
                            seconds=int(b.get("seconds", 600)), reason=b.get("reason", ""))
    except Exception as e:
        console_log.warn("mod", f"{action} on {m['user']} failed: {e}")
        raise HTTPException(502, str(e))
    store.log_event("mod", {"action": action, "user": m["user"], "message_id": m["id"], "seconds": b.get("seconds")})
    console_log.info("mod", f"{action} {m['user']} ({m['platform']})")
    return {"ok": True}


# pins: messages the streamer wants kept on top of the chat page ------------
@app.get("/api/pins")
def pins_get():
    return {"pins": store.kv_get("pins", [])}


@app.post("/api/pins")
async def pins_set(request: Request):
    b = await request.json()
    pins = [p for p in store.kv_get("pins", []) if p["id"] != b.get("message_id")]
    if b.get("pin", True):
        m = store.get_message(b.get("message_id", ""))
        if not m:
            raise HTTPException(404, "unknown message")
        pins = ([{"id": m["id"], "platform": m["platform"], "user": m["user"], "display": m["display"], "text": m["text"],
                  "color": m.get("color", "")}] + pins)[:5]
    store.kv_set("pins", pins)
    hub.emit({"type": "pins.changed", "pins": pins})
    return {"pins": pins}


# dashboard tile numbers for the Suite (chat rate + top chatters) ----------
@app.get("/api/dashboard")
def dashboard():
    now = time.time()
    per, mins = store.stats_since(now - 3600)
    bots = {x.lower() for x in config.settings()["bot_accounts"]}
    cur = int(now // 60)
    series = [mins.get(cur - i, 0) for i in range(14, -1, -1)]      # oldest -> newest, last 15 minutes
    humans = [p for p in per if (p["user"] or "").lower() not in bots]
    top = sorted(humans, key=lambda p: -p["n"])[:5]
    by_platform = {}
    for p in per:
        by_platform[p["platform"]] = by_platform.get(p["platform"], 0) + p["n"]
    return {"rate_per_min": round(sum(series[-5:]) / 5, 1), "last_minute": series[-1], "series_15m": series,
            "messages_last_hour": sum(p["n"] for p in per), "unique_chatters_hour": len(humans),
            "top_chatters": [{"user": p["display"] or p["user"], "platform": p["platform"], "messages": p["n"]} for p in top],
            "by_platform": by_platform, "open_cards": len(cards.view()["open"])}


# feed snapshot for an auxiliary device (read by the master over Link; contract pending with Units 01/04) --
@app.get("/api/feed")
def feed(since: float = 0, limit: int = 200):
    rows = [m for m in store.recent(min(limit, 500)) if m["ts"] > since]
    return {"ts": time.time(), "messages": rows}


# chat look -----------------------------------------------------------------
@app.get("/api/chatstyle")
def chatstyle_get():
    return {"style": chatstyle.sanitize(config.settings()["chat_style"]), "defaults": chatstyle.DEFAULT_STYLE}


@app.post("/api/chatstyle")
async def chatstyle_set(request: Request):
    b = await request.json()
    style = chatstyle.sanitize(b.get("style"))
    config.save_settings({"chat_style": style})
    hub.emit({"type": "chatstyle.changed", "style": style})
    return {"style": style}


@app.post("/api/chatstyle/reset")
def chatstyle_reset():
    return _set_style(chatstyle.sanitize(None))


# presets, undo, import/export of the chat look ------------------------------
def _set_style(style, remember=True):
    if remember:
        store.kv_set("style_prev", chatstyle.sanitize(config.settings()["chat_style"]))
    config.save_settings({"chat_style": style})
    hub.emit({"type": "chatstyle.changed", "style": style})
    return {"style": style}


@app.get("/api/chatstyle/presets")
def chatstyle_presets():
    mine = store.kv_get("style_presets", {}) or {}
    return {"builtin": [{"name": n, "desc": p["desc"], "style": chatstyle.sanitize(p["style"])} for n, p in presets_mod.PRESETS.items()],
            "mine": [{"name": n, "desc": "Saved by you", "style": st} for n, st in mine.items()],
            "can_undo": bool(store.kv_get("style_prev"))}


@app.post("/api/chatstyle/apply")
async def chatstyle_apply(request: Request):
    name = str((await request.json()).get("name", ""))
    st = presets_mod.preset_style(name) or (store.kv_get("style_presets", {}) or {}).get(name)
    if not st:
        raise HTTPException(404, "unknown look")
    return _set_style(chatstyle.sanitize(st))


@app.post("/api/chatstyle/save-preset")
async def chatstyle_save_preset(request: Request):
    b = await request.json()
    name = str(b.get("name", "")).strip()[:40]
    if not name:
        raise HTTPException(400, "give the look a name")
    mine = store.kv_get("style_presets", {}) or {}
    if name not in mine and len(mine) >= 30:
        raise HTTPException(400, "30 saved looks is the limit - delete one first")
    mine[name] = chatstyle.sanitize(b.get("style") or config.settings()["chat_style"])
    store.kv_set("style_presets", mine)
    return {"saved": name, "count": len(mine)}


@app.post("/api/chatstyle/delete-preset")
async def chatstyle_delete_preset(request: Request):
    name = str((await request.json()).get("name", ""))
    mine = store.kv_get("style_presets", {}) or {}
    mine.pop(name, None)
    store.kv_set("style_presets", mine)
    return {"count": len(mine)}


@app.post("/api/chatstyle/undo")
def chatstyle_undo():
    prev = store.kv_get("style_prev")
    if not prev:
        raise HTTPException(404, "nothing to undo")
    return _set_style(chatstyle.sanitize(prev), remember=False)


@app.get("/api/chatstyle/export")
def chatstyle_export():
    return {"pinguino_chat_look": 1, "style": chatstyle.sanitize(config.settings()["chat_style"])}


@app.post("/api/chatstyle/import")
async def chatstyle_import(request: Request):
    b = await request.json()
    src = b.get("style") if isinstance(b.get("style"), dict) else b
    if not isinstance(src, dict) or not any(k in src for k in ("base", "platform", "role", "event", "keywords")):
        raise HTTPException(400, "that does not look like a chat look file")
    return _set_style(chatstyle.sanitize(src))


# panes: split chat halves and extra pop-out windows, each with its own filter and look -------------
def _panes():
    return store.kv_get("panes", {}) or {}


@app.get("/api/panes")
def panes_list():
    return {"panes": _panes(), "geom": store.kv_get("geom", {}) or {}}


@app.get("/api/panes/{pid}")
def pane_get(pid: str):
    p = _panes().get(panes_mod.pane_id(pid))
    if not p:
        raise HTTPException(404, "unknown pane")
    return p


@app.post("/api/panes/{pid}")
async def pane_set(pid: str, request: Request):
    pid = panes_mod.pane_id(pid)
    if not pid:
        raise HTTPException(400, "bad pane id")
    allp = _panes()
    if pid not in allp and len(allp) >= 12:
        raise HTTPException(400, "12 panes is the limit - delete one first")
    allp[pid] = panes_mod.sanitize(await request.json(), allp.get(pid))
    store.kv_set("panes", allp)
    hub.emit({"type": "pane.changed", "id": pid, "pane": allp[pid]})
    return allp[pid]


@app.delete("/api/panes/{pid}")
def pane_delete(pid: str):
    allp = _panes()
    allp.pop(panes_mod.pane_id(pid), None)
    store.kv_set("panes", allp)
    hub.emit({"type": "pane.changed", "id": panes_mod.pane_id(pid), "pane": None})
    return {"ok": True}


@app.post("/api/splits/apply")
async def split_apply(request: Request):
    b = await request.json()
    try:
        built = panes_mod.build_split(str(b.get("mode", "flow")), b.get("platforms"), bool(b.get("aot")))
    except ValueError:
        raise HTTPException(400, "unknown split mode (flow, platform, events, people)")
    allp = _panes()
    for pid, p in built.items():
        old = allp.get(pid) or {}
        p["look"] = old.get("look", {})            # each half keeps its own look tweaks across mode changes
        p["geom"] = old.get("geom")
        allp[pid] = p
        hub.emit({"type": "pane.changed", "id": pid, "pane": p})
    store.kv_set("panes", allp)
    return {"panes": built}


@app.post("/api/geom/{label}")
async def geom_set(label: str, request: Request):
    g = panes_mod.sanitize({"geom": await request.json()}).get("geom")
    if not g:
        raise HTTPException(400, "need x, y, w, h")
    label = panes_mod.pane_id(label)
    allg = store.kv_get("geom", {}) or {}
    if allg.get(label) != g:
        allg[label] = g
        store.kv_set("geom", allg)
    return g


# stream events pushed by other modules (Host: follow, redeem...) -------------
@app.post("/api/events")
async def events_in(request: Request):
    b = await request.json()
    ev = str(b.get("type", ""))
    if ev not in ("follow", "redeem", "sub", "resub", "gift", "raid", "announcement", "raid_out", "poll", "prediction", "hype", "streak"):
        raise HTTPException(400, "unknown event type")
    plat = b.get("platform", "twitch")
    if plat not in connectors:
        raise HTTPException(400, "unknown platform")
    n = int(time.time() * 1000)
    user = str(b.get("user", "someone"))[:60]
    text = str(b.get("text") or {"follow": f"{user} followed", "redeem": f"{user} redeemed a reward", "sub": f"{user} subscribed",
                                  "resub": f"{user} resubscribed", "gift": f"{user} gifted subs", "raid": f"{user} is raiding",
                                  "announcement": user, "streak": f"{user} hit a watch streak"}.get(ev, f"{ev} {user}"))[:300]
    m = ChatMessage(id=f"evt:{plat}:{n}", platform=plat, channel=config.settings()["channel"], user_id=str(b.get("user_id") or user),
                    user=user.lower(), display=user, text=text, ts=time.time(), raw_type=ev, event=ev, amount=int(b.get("amount") or 0))
    inbox.put(m)
    return {"ok": True, "id": m.id}


# assisted chat -----------------------------------------------------------
def _stored(mid):
    m = store.get_message(mid or "")
    if not m:
        raise HTTPException(404, "unknown message")
    return m


@app.post("/api/assist/suggest")
async def assist_suggest(request: Request):
    m = _stored((await request.json()).get("message_id"))
    hist = [h for h in store.user_history(m["platform"], m["user_id"], 6) if h["id"] != m["id"]]
    return await pipeline.assist.suggest(m, hist)


@app.post("/api/assist/translate")
async def assist_translate(request: Request):
    return await pipeline.assist.translate(_stored((await request.json()).get("message_id")))


@app.get("/api/templates")
def templates_get():
    return {"templates": pipeline.assist.templates()}


@app.post("/api/templates")
async def templates_set(request: Request):
    return {"templates": pipeline.assist.set_templates((await request.json()).get("templates", []))}


@app.post("/api/cards/manual")
async def card_manual(request: Request):
    return cards.mark(_stored((await request.json()).get("message_id")))


@app.get("/api/chatter/{platform}/{user_id}")
def chatter(platform: str, user_id: str):
    hist = store.user_history(platform, user_id, 50)
    if not hist:
        raise HTTPException(404, "never seen")
    last = hist[0]
    mine = [c for c in cards.cards.values() if c["platform"] == platform and c["user_id"] == user_id]
    count = lambda st: sum(1 for c in mine if c["state"] == st)
    return {"platform": platform, "user_id": user_id, "user": last["user"], "display": last.get("display") or last["user"],
            "first_seen": min(h["ts"] for h in hist), "last_seen": last["ts"], "messages": store.user_count(platform, user_id),
            "badges": sorted({b for h in hist for b in h.get("badges", [])}), "color": last.get("color", ""),
            "note": store.kv_get("note:" + last["user"].lower(), ""), "muted": last["user"].lower() in set(pipeline.rules["muted"]),
            "cards": {"answered": count("answered"), "open": count("open"), "missed": count("missed"), "dismissed": count("dismissed")},
            "recent": [{"id": h["id"], "text": h["text"], "ts": h["ts"]} for h in hist[:6]]}


# new-chatter ding ------------------------------------------------------
@app.get("/api/ding")
def ding_info():
    return pipeline.ding.info()


@app.post("/api/ding/settings")
async def ding_settings(request: Request):
    b = await request.json()
    patch = {}
    if "platforms" in b:
        patch["ding_platforms"] = [p for p in b["platforms"] if p in ("twitch", "youtube")]
    if "first_ever" in b:
        patch["ding_first_ever"] = bool(b["first_ever"])
    if "returning" in b:
        patch["ding_returning"] = bool(b["returning"])
    for key, name in (("sound", "ding_sound"), ("first_sound", "ding_first_sound"), ("returning_sound", "ding_returning_sound")):
        if key in b:
            path = str(b[key]).strip().strip('"')
            if path and not (path.lower().endswith((".mp3", ".wav")) and os.path.isfile(path)):
                raise HTTPException(400, "choose an existing .mp3 or .wav file")
            patch[name] = path
    if b.get("scope") in ("stream", "ever"):
        patch["ding_scope"] = b["scope"]
    for key, name in (("volume", "ding_volume"), ("returning_volume", "ding_returning_volume"), ("master_volume", "ding_master_volume")):
        if key in b:
            patch[name] = max(0, min(100, int(b[key])))
    if "cooldown_s" in b:
        patch["ding_cooldown_s"] = max(0.2, min(30.0, float(b["cooldown_s"])))
    config.save_settings(patch)
    console_log.info("ding", "settings changed: on for " + (", ".join(config.settings()["ding_platforms"]) or "nothing"))
    return pipeline.ding.info()


@app.post("/api/ding/test")
async def ding_test(request: Request):
    b = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    pipeline.ding.test(b.get("kind", "new"))
    return {"ok": True}


@app.get("/api/newchatters")
def new_chatters(since: float = 0):
    """Recent new / returning chatters (for other modules, e.g. a bot that wants to welcome them)."""
    return {"ts": time.time(), "items": [x for x in pipeline.ding.recent if x["ts"] > since]}


@app.post("/api/ding/reset")
def ding_reset():
    pipeline.ding.new_stream("reset by user")
    return pipeline.ding.info()


@app.post("/api/ding/pick")
async def ding_pick():
    """Opens a file dialog on this PC (Multi runs locally) and returns the chosen sound path."""
    def pick():
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askopenfilename(title="Choose the new-chatter sound", filetypes=[("Sound", "*.mp3 *.wav")])
        finally:
            root.destroy()
    path = await asyncio.to_thread(pick)
    return {"path": path or ""}


# chat pop (a sound on every message) ------------------------------------
@app.get("/api/pop")
def pop_info():
    return pipeline.pop.info()


@app.post("/api/pop/settings")
async def pop_settings(request: Request):
    b = await request.json()
    patch = {}
    if "platforms" in b:
        patch["pop_platforms"] = [p for p in b["platforms"] if p in ("twitch", "youtube", "discord")]
    if "sound" in b:
        path = str(b["sound"]).strip().strip('"')
        if path and not (path.lower().endswith((".mp3", ".wav")) and os.path.isfile(path)):
            raise HTTPException(400, "choose an existing .mp3 or .wav file")
        patch["pop_sound"] = path
    if "volume" in b:
        cur = dict(config.settings()["pop_volume"])
        cur.update({k: max(0, min(100, int(v))) for k, v in b["volume"].items() if k in ("twitch", "youtube", "discord")})
        patch["pop_volume"] = cur
    if "master_volume" in b:
        patch["ding_master_volume"] = max(0, min(100, int(b["master_volume"])))
    if "cooldown_s" in b:
        patch["pop_cooldown_s"] = max(0.1, min(10.0, float(b["cooldown_s"])))
    if "own" in b:
        patch["pop_own"] = bool(b["own"])
    if "roles" in b:
        patch["pop_roles"] = [r for r in b["roles"] if r in ("mod", "vip", "sub", "viewer")]
    config.save_settings(patch)
    console_log.info("pop", "settings changed: on for " + (", ".join(config.settings()["pop_platforms"]) or "nothing"))
    return pipeline.pop.info()


@app.post("/api/sounds/reset")
def sounds_reset():
    """Put every ding and chat-pop setting back to its default (the sound files themselves are not touched)."""
    import copy
    config.save_settings({k: copy.deepcopy(v) for k, v in config.DEFAULTS.items() if k.startswith(("ding_", "pop_"))})
    console_log.info("sounds", "ding and pop settings reset to defaults")
    return {"ding": pipeline.ding.info(), "pop": pipeline.pop.info()}


@app.post("/api/pop/test")
async def pop_test(request: Request):
    b = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    pipeline.pop.test(b.get("platform", "twitch"))
    return {"ok": True}


# settings / rules ----------------------------------------------------
@app.get("/api/settings")
def get_settings():
    return config.settings()


@app.post("/api/settings")
async def post_settings(request: Request):
    return config.save_settings(await request.json())


@app.get("/api/rules")
def get_rules():
    return {"rules": pipeline.rules, "defaults": prio.DEFAULT_RULES}


@app.post("/api/rules")
async def post_rules(request: Request):
    r = prio.save_rules(await request.json())
    pipeline.reload_rules()
    return r


@app.post("/api/rules/reset")
async def reset_rules(request: Request):
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    r = prio.reset_rules(body.get("key"))
    pipeline.reload_rules()
    return r


@app.post("/api/viewers/{user}/mute")
async def mute(user: str, request: Request):
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    cur = set(pipeline.rules["muted"])
    (cur.add if body.get("muted", True) else cur.discard)(user.lower())
    prio.save_rules({"muted": sorted(cur)})
    pipeline.reload_rules()
    return {"muted": sorted(cur)}


@app.get("/api/viewers/{user}/note")
def note_get(user: str):
    return {"user": user.lower(), "note": store.kv_get("note:" + user.lower(), "")}


@app.post("/api/viewers/{user}/note")
async def note_set(user: str, request: Request):
    """Streamer's private note about a viewer (local only, max 500 chars; empty clears it)."""
    note = str((await request.json()).get("note", ""))[:500]
    store.kv_set("note:" + user.lower(), note)
    return {"user": user.lower(), "note": note}


# windows / monitors / profiles ------------------------------------------
@app.get("/api/monitors")
def monitors():
    return win.list_monitors()


@app.get("/api/windows")
def windows_list():
    mons = win.list_monitors()
    return [dict(w, placed=win.place(w, mons)) for w in store.load_windows()]


@app.post("/api/windows")
async def windows_create(request: Request):
    w = win.new_window(**(await request.json()))
    store.save_window(win.describe_geometry(w, win.list_monitors()))
    hub.emit({"type": "layout.changed"})
    return w


@app.put("/api/windows/{wid}")
async def windows_update(wid: str, request: Request):
    cur = next((w for w in store.load_windows() if w["id"] == wid), None)
    if not cur:
        raise HTTPException(404)
    patch = await request.json()
    cur.update({k: v for k, v in patch.items() if k in win.WINDOW_DEFAULTS})
    if any(k in patch for k in ("x", "y", "w", "h")):
        win.describe_geometry(cur, win.list_monitors())
    store.save_window(cur)
    hub.emit({"type": "layout.changed", "id": wid})
    return cur


@app.delete("/api/windows/{wid}")
def windows_delete(wid: str):
    shell.close(wid)
    store.delete_window(wid)
    hub.emit({"type": "layout.changed"})
    return {"ok": True}


@app.post("/api/windows/{wid}/launch")
def windows_launch(wid: str):
    w = next((w for w in store.load_windows() if w["id"] == wid), None)
    if not w:
        raise HTTPException(404)
    shell.open(w, win.place(w, win.list_monitors()))
    return {"ok": True}


@app.post("/api/windows/restore")
def windows_restore():
    mons, n = win.list_monitors(), 0
    for w in store.load_windows():
        if w["visible"]:
            shell.open(w, win.place(w, mons))
            n += 1
    return {"opened": n}


@app.get("/api/profiles")
def profiles():
    return {"builtin": list(win.PROFILE_DEFAULTS), "saved": list(store.load_profiles())}


@app.post("/api/profiles/{name}/apply")
def profile_apply(name: str):
    saved = store.load_profiles()
    spec = saved.get(name) or win.PROFILE_DEFAULTS.get(name)
    if spec is None:
        raise HTTPException(404)
    for w in store.load_windows():
        shell.close(w["id"])
        store.delete_window(w["id"])
    mons, out = win.list_monitors(), []
    for s in spec:
        w = win.describe_geometry(win.new_window(**s), mons)
        store.save_window(w)
        shell.open(w, win.place(w, mons))
        out.append(w)
    store.kv_set("active_profile", name)
    hub.emit({"type": "layout.changed", "profile": name})
    return out


@app.post("/api/profiles/{name}/save")
def profile_save(name: str):
    store.save_profile(name, store.load_windows())
    return {"ok": True}


# auth ----------------------------------------------------------------
@app.get("/auth/callback", response_class=HTMLResponse)
def auth_callback():
    """The site redirects here with the tokens in the URL FRAGMENT (never sent to a server log);
    this page forwards them to POST /auth/token over localhost, then clears the address bar."""
    return """<!doctype html><title>Connecting</title><body style="font:16px sans-serif;background:#111;color:#eee">
<p id=m>Connecting Twitch...</p><script>
const p=new URLSearchParams(location.hash.slice(1));history.replaceState(null,'','/auth/callback');
fetch('/auth/token',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(p))})
.then(r=>r.json()).then(j=>{m.textContent=j.ok?'Connected. You can close this window.':'Failed: '+j.error});
</script>"""


@app.post("/auth/token")
async def auth_token(request: Request):
    b = await request.json()
    if not b.get("access_token"):
        return {"ok": False, "error": "no access_token"}
    secrets_store.put("twitch_tokens", {k: b[k] for k in ("access_token", "refresh_token", "client_id") if k in b})
    if b.get("site_url"):
        secrets_store.put("site_url", b["site_url"])
    tw = connectors.get("twitch")
    if tw:
        tw.state["detail"] = "token saved"
    return {"ok": True}


@app.get("/api/checks")
async def api_checks():
    return {"checks": await asyncio.to_thread(checks.run, connectors.get("twitch"))}


@app.post("/api/open-connect")
def open_connect():
    """Open the site's Connect URL in the user's default browser (works from embedded/native shells too)."""
    url = checks.site_url() + "/auth/twitch/login?multi=1"
    return {"ok": bool(webbrowser.open(url)), "url": url}


@app.post("/api/secrets/discord")
async def set_discord(request: Request):
    """Write-only: stores the bot token in Credential Manager; never echoed back."""
    b = await request.json()
    tok = (b.get("token") or "").strip()
    if b.get("clear"):
        secrets_store.delete("discord_token")
    elif len(tok) > 20:
        secrets_store.put("discord_token", tok)
    elif "channels" not in b:
        raise HTTPException(400, "token looks too short")
    if "channels" in b:
        config.save_settings({"discord_channels": [str(c) for c in b["channels"] if str(c).isdigit()]})
    return {"ok": True, "has_token": bool(secrets_store.get("discord_token"))}


@app.get("/api/claims")
def claims():
    """Streamer-first contract: open medium/high cards the streamer may answer personally. Bots/Router poll this
    and stay quiet on these message ids until `expires`. Read-only, nothing here can post."""
    ttl, now = config.settings()["claim_ttl_s"], time.time()
    out = [{"message_id": c["message_id"], "platform": c["platform"], "user_id": c["user_id"], "tier": c["tier"],
            "expires": c["created"] + ttl} for c in cards.cards.values()
           if c["state"] == "open" and c["tier"] in ("medium", "high") and c["created"] + ttl > now]
    return {"ttl_s": ttl, "claims": out}


@app.post("/api/voice/transcript")
async def voice_transcript(request: Request):
    """Called by Listen (or any ASR) with recent transcript text. Emits reply.suggested; never answers a card."""
    if not config.settings()["voice_enabled"]:
        return {"enabled": False, "suggestions": []}
    text = str((await request.json()).get("text", ""))[:2000]
    sug = voice.match(text, cards.cards.values())
    for s in sug:
        hub.emit({"type": "reply.suggested", **s})
    return {"enabled": True, "suggestions": sug}


@app.post("/api/voice/confirm/{card_id}")
def voice_confirm(card_id: str):
    if card_id not in cards.cards:
        raise HTTPException(404, "no such card")
    cards.answer(card_id, via="voice")
    return {"ok": True}


@app.get("/api/ai")
def ai_usage():
    return pipeline.advisor.usage()


@app.post("/api/secrets/youtube")
async def set_youtube(request: Request):
    """Write-only OAuth access token for YouTube live chat. Body: {token|clear}."""
    b = await request.json()
    if b.get("clear"):
        secrets_store.delete("youtube_token")
    elif len((b.get("token") or "").strip()) > 20:
        secrets_store.put("youtube_token", b["token"].strip())
    else:
        raise HTTPException(400, "token looks too short")
    return {"ok": True, "has_token": bool(secrets_store.get("youtube_token"))}


@app.post("/api/secrets/ai")
async def set_ai_key(request: Request):
    """Write-only AI key (Credential Manager). Body: {key|clear}."""
    b = await request.json()
    if b.get("clear"):
        secrets_store.delete("ai_key")
    elif len((b.get("key") or "").strip()) > 8:
        secrets_store.put("ai_key", b["key"].strip())
    else:
        raise HTTPException(400, "key looks too short")
    return {"ok": True, "has_key": bool(secrets_store.get("ai_key"))}


@app.post("/auth/disconnect")
def auth_disconnect():
    secrets_store.delete("twitch_tokens")
    return {"ok": True}


# dev helper: feed a fake message through the real pipeline ----------------
@app.post("/api/dev/inject")
async def dev_inject(request: Request):
    b = await request.json()
    n = int(time.time() * 1000)
    m = ChatMessage(id=b.get("id") or f"twitch:dev:{n}", platform=b.get("platform", "twitch"), channel="dev",
                    user_id=b.get("user_id") or b.get("user", "viewer"), user=b.get("user", "viewer"),
                    display=b.get("user", "viewer"), text=b["text"], ts=time.time(), badges=b.get("badges", []),
                    first_time=b.get("first_time", False), reply_to=b.get("reply_to", ""),
                    reply_to_user=b.get("reply_to_user", ""), color=b.get("color", ""), emotes=b.get("emotes", []),
                    event=b.get("event", ""), amount=int(b.get("amount", 0)))
    inbox.put(m)
    return {"ok": True, "id": m.id}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    origin = ws.headers.get("origin", "")
    if not origin_ok(origin) or not host_ok(ws.headers.get("host")):
        await ws.close(code=1008)
        return
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "connectors": [c.describe() for c in connectors.values()], "viewers": viewers_mod.counts,
                            "cards": cards.view(), "ts": time.time()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="warning")
