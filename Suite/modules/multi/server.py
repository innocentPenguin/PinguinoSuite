"""PinguinoMulti - unified chat core. REST + WS on 127.0.0.1:8766.
Run: run.bat   (UI at http://127.0.0.1:8766)"""
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
import console_log
import listen_bridge
import prestream
import voice
import secrets_store
import windows as win
from connectors.discord import Discord
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
cards = cards_mod.CardManager(store, hub.emit)
pipeline = Pipeline(store, cards, hub.emit)
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


@asynccontextmanager
async def lifespan(app):
    hub.loop = asyncio.get_running_loop()
    hub.loop.set_exception_handler(lambda loop, ctx: console_log.error(
        "server", f"unhandled: {ctx.get('message', '')} {repr(ctx.get('exception', ''))}", dedupe_s=60))
    console_log.info("server", f"Multi started on port {config.PORT}")
    store.prune(config.settings()["retention_days"])
    tw = Twitch(inbox, hub.emit)
    connectors["twitch"] = tw
    dc = Discord(inbox, hub.emit)
    connectors["discord"] = dc
    yt = YouTube(inbox, hub.emit)
    connectors["youtube"] = yt
    tt = TikTok(inbox, hub.emit)
    connectors["tiktok"] = tt
    tasks = [asyncio.create_task(inbox.run()), asyncio.create_task(tick_loop()), asyncio.create_task(tw.run()),
             asyncio.create_task(dc.run()), asyncio.create_task(yt.run()), asyncio.create_task(tt.run()),
             asyncio.create_task(listen_bridge.run(cards, hub.emit)), asyncio.create_task(prestream_file_loop())]
    yield
    console_log.info("server", "Multi stopping")
    tw.stop = dc.stop = yt.stop = tt.stop = True
    for t in tasks:
        t.cancel()
    for wid in list(shell.procs):
        shell.close(wid)


TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    console_log.error("server", f"{request.method} {request.url.path} failed: {type(exc).__name__}: {exc}", dedupe_s=60)
    return JSONResponse({"detail": "internal error"}, status_code=500)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8760", "http://localhost:8760", *TAURI_ORIGINS],
                   allow_methods=["*"], allow_headers=["*"])
STATIC = config.ROOT / "static"
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


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
    return hmac.compare_digest(got.encode(), want.encode())


@app.middleware("http")
async def local_only_writes(request: Request, call_next):
    """Anti DNS-rebinding (Host) + anti drive-by (Origin). Writes from our own page (Origin == Host, e.g. the
    embedded iframe) pass; any other writer (no Origin, or a Tauri origin) must present the module token."""
    if not host_ok(request.headers.get("host")):
        return HTMLResponse("forbidden host", status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if not origin_ok(origin):
            return HTMLResponse("forbidden origin", status_code=403)
        same_origin = bool(origin) and origin.split("://", 1)[-1] == request.headers.get("host")
        if not same_origin and not token_ok(request):
            return HTMLResponse("token required", status_code=401)
    return await call_next(request)


def _page():
    """index.html with the shared Suite theme linked after our own styles (our values stay as the fallback)."""
    core = os.environ.get("PINGUINO_CORE_URL", "http://127.0.0.1:8760").rstrip("/")
    html = (STATIC / "index.html").read_text("utf-8")
    return HTMLResponse(html.replace("<!--THEME-->", f'<link rel="stylesheet" href="{core}/theme.css">'))


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
            "tiktok_enabled", "tiktok_user", "channel", "bot_accounts", "my_names")
    return {"settings": {k: s[k] for k in keys},
            "has": {"discord": bool(secrets_store.get("discord_token")), "youtube": bool(secrets_store.get("youtube_token")),
                    "ai": bool(secrets_store.get("ai_key")), "twitch": bool(secrets_store.get("twitch_tokens"))},
            "sources": {k: secrets_store.source(k) for k in ("twitch_tokens", "discord_token", "youtube_token", "ai_key")}}


@app.get("/api/prestream")
def prestream_checks():
    """Readiness for the Pinguino Console: {ts, items:[{id,label,status pass|warn|fail,detail}]}."""
    return {"ts": time.time(), "items": prestream.run(connectors, store, pipeline, inbox)}


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
    try:
        mid = await conn.send(text, reply_to)
    except Exception as e:
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
                    reply_to_user=b.get("reply_to_user", ""), color=b.get("color", ""), emotes=b.get("emotes", []))
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
        await ws.send_json({"type": "hello", "connectors": [c.describe() for c in connectors.values()],
                            "cards": cards.view(), "ts": time.time()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="warning")
