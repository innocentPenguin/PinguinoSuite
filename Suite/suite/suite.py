"""PinguinoSuite - the host app. Supervises modules (PinguinoListen, ...), detects when the channel goes live,
tells modules about it, and serves the dashboard. Run via PinguinoSuite.bat (or autostart with Windows)."""
import asyncio
import json
import hmac
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
import livedetect  # noqa: E402
import consolelog  # noqa: E402
import prestream  # noqa: E402
import device  # noqa: E402
import portable  # noqa: E402

FROZEN = getattr(sys, "frozen", False)
# Frozen (bundled sidecar): the Suite data/modules folder is passed in by the shell.
ROOT = Path(os.environ["PINGUINO_SUITE_DIR"]) if FROZEN and os.environ.get("PINGUINO_SUITE_DIR") else Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
SETTINGS = ROOT / "suite_settings.json"
PORT = int(os.environ.get("PINGUINO_PORT", "8760"))
PY = os.environ.get("PINGUINO_PYTHON") or (("python" if os.name == "nt" else "python3") if FROZEN else sys.executable)
IS_WIN = os.name == "nt"
# Per-launch API token. The Tauri shell passes one in; standalone mode makes its own and injects it into the page it serves.
TOKEN = os.environ.get("PINGUINO_API_TOKEN") or secrets.token_urlsafe(32)


def module_token(mid):
    """Per-module secret derived from the core token: a module never receives (or can forge) the core API token."""
    return hmac.new(TOKEN.encode(), f"module:{mid}".encode(), "sha256").hexdigest()[:40]
# Who may call: the core's own origin plus the Tauri webview origins (Windows/macOS/Linux).
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}", "tauri://localhost",
                   "http://tauri.localhost", "https://tauri.localhost"}
# Shared data root handed to every module: PINGUINO_DATA_DIR if the user set it, else Data/runtime
# (the folder that holds bots.json, chat_settings.json, host_secrets.json... and that Host and Pipeline default to).
DATA_DIR = os.environ.get("PINGUINO_DATA_DIR") or str(ROOT.parent / "Data" / "runtime")
console_log = consolelog.Console(Path(DATA_DIR) / "console", LOGS)  # live log stream for the Console page
CONSOLE_DIR = Path(DATA_DIR) / "console"
devices = device.Devices(Path(DATA_DIR) / "device.json", existing_install=SETTINGS.exists() or (Path(DATA_DIR) / "bots.json").exists())  # this install: stable id, master/auxiliary role, peers
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
# UI source: single copy lives in the Tauri app so the two can't drift.
UI_INDEX = ROOT.parent / "App" / "src" / "index.html"  # only copy of the UI (the old Suite/suite/static copy was retired)
UI_INDEX = UI_INDEX if UI_INDEX.exists() else None
DEFAULT_SETTINGS = {"channel": "innocentpenguin_", "poll_secs": 20, "offline_grace_secs": 180, "modules": {}}


# ------------------------------------------------------------------ settings
def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    for f in (SETTINGS, SETTINGS.with_name(SETTINGS.name + ".bak")):  # corrupt/missing file -> last good backup
        try:
            s.update(json.loads(f.read_text("utf8")))
            break
        except Exception:
            continue
    return s


def save_settings(s):
    """Atomic write (temp + replace) keeping the previous good file as .bak, so a crash never leaves half a file."""
    tmp = SETTINGS.with_name(SETTINGS.name + ".tmp")
    tmp.write_text(json.dumps(s, indent=2), "utf8")
    if SETTINGS.exists():
        try:
            shutil.copyfile(SETTINGS, SETTINGS.with_name(SETTINGS.name + ".bak"))
        except OSError:
            pass
    os.replace(tmp, SETTINGS)


# ------------------------------------------------------------------ structured log (JSONL, rotated)
EVENT_LOG = LOGS / "events.jsonl"
_log_lock = threading.Lock()


def _jsonl_log(ev, max_bytes=2_000_000, keep=3):
    """One JSON object per line: every bus event. Rotates events.jsonl -> .1 -> .2 -> .3 past max_bytes."""
    try:
        with _log_lock:
            if EVENT_LOG.exists() and EVENT_LOG.stat().st_size > max_bytes:
                for i in range(keep, 0, -1):
                    src = EVENT_LOG if i == 1 else EVENT_LOG.with_name(f"{EVENT_LOG.name}.{i - 1}")
                    if src.exists():
                        os.replace(src, EVENT_LOG.with_name(f"{EVENT_LOG.name}.{i}"))
            with open(EVENT_LOG, "a", encoding="utf8") as f:
                f.write(json.dumps(ev, default=str) + "\n")
    except OSError:
        pass


def tail_lines(path, n):
    """Last n lines of a text file without reading all of it (reads at most ~64 KB per 200 lines)."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - max(4096, n * 320)))
            data = f.read()
    except OSError:
        return []
    return data.decode("utf8", "replace").splitlines()[-n:]


# ------------------------------------------------------------------ event bus (the seed of a Streamer.bot-style core)
def _event_to_console(ev):
    """Every core event also goes to the Console (crashes/failures louder than routine state changes)."""
    t, extra = ev["type"], {k: v for k, v in ev.items() if k not in ("type", "ts", "id")}
    mid = ev.get("id", "core")
    lvl = "info"
    if t == "module":
        lvl = {"failed": "error", "crashed": "warn"}.get(ev.get("state"), "info")
    elif t == "hook" and not ev.get("ok"):
        lvl = "warn"
    elif t == "prestream":
        lvl = "error" if ev.get("fail") else "warn" if ev.get("warn") else "info"
    msg = t + (": " + ", ".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
    console_log.log(lvl, t, msg, module=mid)


class Bus:
    def __init__(self):
        self.clients, self.loop, self.history = set(), None, []

    def emit(self, type_, **data):
        ev = {"type": type_, "ts": time.time(), **data}
        self.history = (self.history + [ev])[-200:]
        _jsonl_log(ev)
        _event_to_console(ev)
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._send(ev), self.loop)
        return ev

    async def _send(self, ev):
        for ws in list(self.clients):
            try:
                await ws.send_json(ev)
            except Exception:
                self.clients.discard(ws)


bus = Bus()


# ------------------------------------------------------------------ modules
def kill_tree(proc):
    """Stop a module and its children on any OS."""
    if IS_WIN:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:  # noqa: BLE001
            pass


class Module:
    def __init__(self, spec):
        self.spec = spec
        self.id = spec["id"]
        self.proc = None
        self.healthy = False
        self.wanted = False   # set by start(), cleared by stop(): a wanted module that dies is restarted
        self.crashes = []     # timestamps of recent unexpected exits (circuit breaker)
        self.retry_at = 0.0
        self.failed = False
        self.deferred = False  # singleton waiting for this device to become master

    @property
    def singleton(self):
        return bool(self.spec.get("singleton"))

    def opts(self):
        o = dict(self.spec.get("defaults", {}))
        o.update(load_settings()["modules"].get(self.id, {}))
        if self.spec.get("defaults", {}).get("always_start"):  # manifest pins these on; saved settings can't turn them off
            o["enabled"] = o["start_with_suite"] = True
        return o

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running or self._ping():
            return
        if self.singleton and not devices.is_master():  # only the master device runs bots/Host/Spotify: never two instances
            self.deferred = True
            console_log.log("info", "device", f"{self.id} not started: this device is not the master ({devices.state()['master_name']} is)", module=self.id)
            return
        self.deferred = False
        self.wanted, self.failed = True, False
        cmd = [PY if c == "{py}" else c for c in self.spec["cmd"]]
        log = open(LOGS / f"{self.id}.log", "ab")
        if IS_WIN:
            extra = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            extra = {"start_new_session": True}
        self.proc = subprocess.Popen(cmd, cwd=ROOT / self.spec["cwd"], stdout=log, stderr=log,
                                     env={**os.environ, "PINGUINO_API_TOKEN": module_token(self.spec["id"]), "PINGUINO_DATA_DIR": DATA_DIR, "PINGUINO_CORE_URL": f"http://127.0.0.1:{PORT}"}, **extra)
        bus.emit("module", id=self.id, state="starting")

    def stop(self, deferred=False):
        self.wanted, self.failed = False, False
        self.deferred = deferred  # True when stopped only because this device lost the master role: restart on promotion
        if self.running:
            kill_tree(self.proc)
        self.proc, self.healthy = None, False
        bus.emit("module", id=self.id, state="stopped")

    def _ping(self):
        try:
            return requests.get(self.spec["url"] + self.spec.get("health", "/"), timeout=1.5).ok
        except Exception:
            return False

    def supervise(self):
        """Restart a wanted module that exited on its own: backoff 2/5/15/30/60s, give up after 5 crashes in 5 min."""
        if not self.wanted or self.failed or self.proc is None or self.proc.poll() is None:
            return
        now = time.time()
        if not self.retry_at:
            self.crashes = [t for t in self.crashes if now - t < 300] + [now]
            if len(self.crashes) > 5:
                self.failed = True
                bus.emit("module", id=self.id, state="failed", detail="crashed 5 times in 5 minutes; start it manually")
                return
            self.retry_at = now + (2, 5, 15, 30, 60)[min(len(self.crashes), 5) - 1]
            bus.emit("module", id=self.id, state="crashed", exit=self.proc.poll(), retry_in=round(self.retry_at - now))
        elif now >= self.retry_at:
            self.retry_at, self.proc = 0.0, None
            self.start()

    def refresh(self):
        self.supervise()
        was = self.healthy
        self.healthy = self._ping()
        if self.healthy != was:
            bus.emit("module", id=self.id, state="running" if self.healthy else ("starting" if self.running else "stopped"))

    def call(self, hook):
        """POST a module's on_live / on_offline hook, retrying while it boots."""
        spec = self.spec.get(hook)
        if not spec or (self.singleton and not devices.is_master()):
            return
        for _ in range(40):
            try:
                r = requests.post(self.spec["url"] + spec["post"], headers=(lambda t: {"Authorization": f"Bearer {t}", "X-Pinguino-Token": t, "x-link-token": t})(module_token(self.spec["id"])), timeout=10)
                bus.emit("hook", id=self.id, hook=hook, ok=r.ok, detail=r.text[:160])
                return
            except Exception:
                time.sleep(3)
        bus.emit("hook", id=self.id, hook=hook, ok=False, detail="module never answered")

    def public(self):
        st = "running" if self.healthy else "starting" if self.running else "stopped"
        return {"id": self.id, "name": self.spec["name"], "desc": self.spec.get("desc", ""), "url": self.spec["url"], "ui": self.spec.get("ui"), "state": st, "options": self.opts()}


def discover_specs():
    """Registry = modules.json (explicit) + modules/<dir>/module.json manifests (drop-in). See Docs/MODULE_CONTRACT.md."""
    specs = {}
    for mf in sorted((ROOT / "modules").glob("*/module.json")):
        try:
            spec = json.loads(mf.read_text("utf8"))
            spec.setdefault("cwd", f"modules/{mf.parent.name}")
            specs[spec["id"]] = spec
        except Exception as e:  # noqa: BLE001
            print(f"[Pinguino] bad manifest {mf}: {e}", file=sys.stderr)
    for spec in json.loads((ROOT / "modules.json").read_text("utf8")):
        specs[spec["id"]] = spec
    return specs


modules = {mid: Module(spec) for mid, spec in discover_specs().items()}


# ------------------------------------------------------------------ go-live handling
live_state = {"live": False, "since": None, "title": "", "game": "", "viewers": 0, "simulated": None, "error": None}
_offline_since = None


def on_transition(is_live):
    bus.emit("live" if is_live else "offline", **{k: live_state[k] for k in ("title", "game", "viewers")})
    for m in modules.values():
        o = m.opts()
        if not (o.get("enabled") and o.get("react_to_live")):
            continue
        if is_live:
            m.start()
        threading.Thread(target=m.call, args=("on_live" if is_live else "on_offline",), daemon=True).start()


def apply_stream(info):
    """info: dict from Twitch or None. Debounces short drops so a reconnect doesn't stop everything."""
    global _offline_since
    now = time.time()
    was = live_state["live"]
    if info:
        _offline_since = None
        live_state.update(title=info["title"], game=info["game"], viewers=info["viewers"])
        if not was:
            live_state.update(live=True, since=info["started"] if info["started"] else now)
            on_transition(True)
        return
    if was:
        _offline_since = _offline_since or now
        if now - _offline_since >= load_settings()["offline_grace_secs"]:
            live_state.update(live=False, since=None, viewers=0)
            _offline_since = None
            on_transition(False)


def twitch_loop():
    while True:
        s = load_settings()
        try:
            if live_state["simulated"] is None:
                apply_stream(livedetect.stream_info(s["channel"]))
                live_state["error"] = None
        except Exception as e:  # noqa: BLE001
            live_state["error"] = str(e)[:200]
        time.sleep(max(10, s["poll_secs"]))


CONTROL_DIR = Path(DATA_DIR) / "control"


def process_control():
    """File-drop trigger so a script can restart ONE module without the per-launch API token:
    create Data/runtime/control/<start|stop|restart>-<module id>. The core consumes (deletes) the file and acts.
    Only registered module ids are honoured; nothing else is read from the file."""
    try:
        files = list(CONTROL_DIR.iterdir()) if CONTROL_DIR.is_dir() else []
    except OSError:
        return
    for f in files:
        action, _, mid = f.name.partition("-")
        m = modules.get(mid)
        try:
            f.unlink()
        except OSError:
            continue
        if f.name == "prestream-run":  # run the pre-stream checks now; the result lands in console/prestream-last.json
            console_log.log("info", "prestream", "manual run requested (control file)")
            threading.Thread(target=run_prestream, kwargs={"slot": "manual"}, daemon=True).start()
            continue
        if not m or action not in ("start", "stop", "restart"):
            continue
        bus.emit("control", id=mid, action=action)
        if action in ("stop", "restart"):  # run in order on this one thread so a stop never races a later start
            m.stop()
        if action in ("start", "restart"):
            m.start()


last_prestream = {}


def run_prestream(slot=None, scheduled=False):
    """Run all readiness checks, post the result to the Console and the event bus (toast), keep it for /api/prestream."""
    global last_prestream
    mods = [{"id": m.id, "spec": m.spec, "state": m.public()["state"], "always_start": bool(m.spec.get("defaults", {}).get("always_start"))}
            for m in modules.values()]
    rep = prestream.run_checks(mods, module_token, CONSOLE_DIR, lambda: console_log.errors_since(1800), ROOT, slot, scheduled)
    last_prestream = rep
    try:  # a script (no app token) can read the latest result from here
        tmp = CONSOLE_DIR / "prestream-last.json.tmp"
        tmp.write_text(json.dumps(rep, indent=2), "utf8")
        os.replace(tmp, CONSOLE_DIR / "prestream-last.json")
    except OSError:
        pass
    for i in rep["items"]:
        if i["status"] != "pass":
            console_log.log("error" if i["status"] == "fail" else "warn", "prestream", f"{i['label']}: {i['detail'] or i['status']}", module=i["module"])
    sm = rep["summary"]
    bus.emit("prestream", slot=slot or "manual", scheduled=scheduled, passed=sm["pass"], warn=sm["warn"], fail=sm["fail"])
    return rep


def prestream_loop():
    done = set()
    while True:
        try:
            due = prestream.due_slot(datetime.now(timezone.utc), done)
            if due and not devices.is_master():
                done.add(due[1])  # auxiliary devices do not run the stream checks
                due = None
            if due:
                done.add(due[1])
                run_prestream(slot=due[0], scheduled=True)
        except Exception as e:  # noqa: BLE001
            console_log.log("error", "prestream", f"scheduler error: {e}")
        time.sleep(20)


_last_master = [None]


def reconcile_devices():
    """Start singleton modules when this device becomes master, stop them when it stops being master."""
    st = devices.state()
    if st["master_id"] != _last_master[0] or st["is_master"] != getattr(reconcile_devices, "was", None):
        reconcile_devices.was = st["is_master"]
        if st["master_id"] != _last_master[0]:
            console_log.log("info", "device", f"master is now {st['master_name']}" + (" (this device)" if st["is_master"] else ""))
            bus.emit("device", master=st["master_name"], is_master=st["is_master"])
        _last_master[0] = st["master_id"]
    for m in modules.values():
        if not m.singleton:
            continue
        if st["is_master"] and m.deferred and not m.running:
            o = m.opts()
            if o.get("enabled") and o.get("start_with_suite"):
                m.start()
        elif not st["is_master"] and not st["warming_up"] and (m.running or m.wanted):
            console_log.log("warn", "device", f"stopping {m.id}: {st['master_name']} is now master", module=m.id)
            m.stop(deferred=True)


_link_warned = [False]


def device_sync_loop():
    """Tell paired devices about us (via the Link module, which owns the network transport); peers arrive on POST /api/device/peer."""
    link = modules.get("link")
    while True:
        time.sleep(device.HEARTBEAT_SECS)
        if not link or not link.healthy:
            continue
        try:
            tok = module_token("link")
            r = requests.post(link.spec["url"] + "/api/peer/broadcast", json={"type": "device-hb", "payload": devices.heartbeat()},
                              headers={"Authorization": f"Bearer {tok}", "x-link-token": tok}, timeout=5)
            if r.status_code == 404 and not _link_warned[0]:
                _link_warned[0] = True
                console_log.log("info", "device", "Link has no peer API yet; running as a single device")
        except Exception:  # noqa: BLE001
            pass


def health_loop():
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    tick = 0
    while True:
        process_control()
        reconcile_devices()
        console_log.ingest(list(modules))
        if tick % 4 == 0:  # health every ~4s, control files every second
            for m in modules.values():
                m.refresh()
        tick += 1
        time.sleep(1)


# ------------------------------------------------------------------ windows autostart
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled():
    if not IS_WIN:
        return False  # the Tauri shell owns autostart on every OS
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "PinguinoSuite")
            return True
    except OSError:
        return False


def set_autostart(on):
    if not IS_WIN:
        raise HTTPException(501, "autostart is handled by the app shell on this platform")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            py = Path(sys.executable).with_name("pythonw.exe")
            winreg.SetValueEx(k, "PinguinoSuite", 0, winreg.REG_SZ, f'"{py}" "{Path(__file__).resolve()}" --background')
        else:
            try:
                winreg.DeleteValue(k, "PinguinoSuite")
            except OSError:
                pass


# ------------------------------------------------------------------ app
@asynccontextmanager
async def lifespan(app):
    bus.loop = asyncio.get_running_loop()
    for m in modules.values():
        o = m.opts()
        if o.get("enabled") and o.get("start_with_suite"):
            m.start()
    threading.Thread(target=health_loop, daemon=True).start()
    threading.Thread(target=twitch_loop, daemon=True).start()
    threading.Thread(target=prestream_loop, daemon=True).start()
    threading.Thread(target=device_sync_loop, daemon=True).start()
    bus.emit("suite", state="started")
    yield
    for m in modules.values():
        m.stop()


app = FastAPI(lifespan=lifespan)


MODULE_PATHS = {"/api/device/peer", "/api/device/streaming", "/api/device/lease", "/api/voice/dispatch"}


@app.middleware("http")
async def guard(request: Request, call_next):
    """Local-only API: right Host (anti DNS-rebinding), allowed Origin (anti drive-by web pages), valid token."""
    if request.method != "OPTIONS":
        origin = request.headers.get("origin")
        if request.headers.get("host") not in ALLOWED_HOSTS or (origin and origin not in ALLOWED_ORIGINS):
            return JSONResponse({"detail": "forbidden origin"}, status_code=403)
        if request.url.path.startswith("/api/"):
            auth = request.headers.get("authorization", "")
            given = auth[7:] if auth.lower().startswith("bearer ") else request.headers.get("x-pinguino-token", "")
            ok = secrets.compare_digest(given, TOKEN)
            if not ok and request.url.path in MODULE_PATHS:  # modules (Link, Host...) may call these with their own token
                for mid in modules:
                    if secrets.compare_digest(given, module_token(mid)):
                        ok, request.state.mod = True, mid
                        break
            if not ok:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


app.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS), allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type", "X-Pinguino-Token", "X-Passphrase"])


@app.get("/")
def index():
    """Standalone/browser mode only (the Tauri shell loads the UI itself and gets the token via IPC)."""
    html = UI_INDEX.read_text("utf8") if UI_INDEX else "<h1>PinguinoSuite core</h1>"
    return HTMLResponse(html.replace("<head>", f'<head><meta name="pinguino-token" content="{TOKEN}">', 1))


@app.get("/theme.css")
def theme_css():
    """Shared colour tokens (App/src/theme.css): module pages link this so the whole Suite shares one palette. No token needed."""
    f = UI_INDEX.parent / "theme.css" if UI_INDEX else None
    if not f or not f.exists():
        raise HTTPException(404)
    return Response(f.read_text("utf8"), media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.get("/bootstrap.js")
def bootstrap_js():
    """Browser/standalone mode: index.html loads this to attach the per-launch token to API calls."""
    f = ROOT.parent / "App" / "src" / "bootstrap.js"
    if not f.exists():
        return Response(status_code=404)
    return Response(f.read_text("utf8"), media_type="application/javascript")


@app.get("/api/capabilities")
def capabilities():
    """Which platform features this build offers. UIs and modules must treat every entry as optional."""
    return {"api": 1, "platform": sys.platform, "autostart": "legacy-windows" if IS_WIN else "shell",
            "tray": "shell", "module_manifest": 1}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    origin = sock.headers.get("origin")
    ok = (sock.headers.get("host") in ALLOWED_HOSTS and (not origin or origin in ALLOWED_ORIGINS)
          and secrets.compare_digest(sock.query_params.get("token", ""), TOKEN))
    if not ok:
        await sock.close(code=1008)
        return
    await sock.accept()
    bus.clients.add(sock)
    try:
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        bus.clients.discard(sock)


@app.get("/api/state")
def state():
    s = load_settings()
    return {"live": live_state, "channel": s["channel"], "windows_autostart": autostart_enabled(),
            "modules": [m.public() for m in modules.values()], "events": bus.history[-60:]}


class Opt(BaseModel):
    enabled: bool | None = None
    start_with_suite: bool | None = None
    react_to_live: bool | None = None


@app.get("/api/modules/{mid}/probe")
def module_probe(mid: str):
    """The module's own health/status JSON, fetched by the core so the UI needs no cross-origin call to the module."""
    m = modules.get(mid)
    if not m:
        raise HTTPException(404)
    try:
        r = requests.get(m.spec["url"] + m.spec.get("health", "/"), timeout=2)
        return r.json()
    except Exception:
        raise HTTPException(502, "module not answering")


@app.get("/api/modules/{mid}/get")
def module_get(mid: str, path: str):
    """GET one of a module's /api/ paths on the UI's behalf (module token attached): lets the app read module data without cross-origin calls."""
    m = modules.get(mid)
    if not m:
        raise HTTPException(404)
    if not path.startswith("/api/") or ".." in path:
        raise HTTPException(400, "path must be under /api/")
    tok = module_token(mid)
    try:
        r = requests.get(m.spec["url"] + path, headers={"Authorization": f"Bearer {tok}", "X-Pinguino-Token": tok, "x-link-token": tok}, timeout=5)
        return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"))
    except requests.RequestException:
        raise HTTPException(502, "module not answering")


@app.get("/api/modules/{mid}/logs")
def module_logs(mid: str, lines: int = 200):
    if mid not in modules:
        raise HTTPException(404)
    return {"id": mid, "lines": tail_lines(LOGS / f"{mid}.log", max(1, min(lines, 2000)))}


class DevConfig(BaseModel):
    name: str | None = None
    priority: int | None = None
    role_pref: str | None = None


ROLES = {"streaming": ("master", 100), "gaming": ("auxiliary", 70), "mac": ("auxiliary", 50)}


class Setup(BaseModel):
    name: str
    role: str = "streaming"          # streaming | gaming | mac (priority presets for the master election)
    priority: int | None = None


@app.get("/api/setup")
def setup_get():
    """First-run wizard state: is this install set up, and where does everything live (nothing is hardcoded to a drive)."""
    return {"first_run": not devices.me.get("setup_done"), "device": devices.me, "data_dir": str(DATA_DIR), "suite_root": str(ROOT),
            "platform": sys.platform, "frozen": FROZEN}


@app.post("/api/setup")
def setup_post(b: Setup):
    role, prio = ROLES.get(b.role, ("auxiliary", 50))
    devices.configure(name=b.name.strip() or None, priority=b.priority if b.priority is not None else prio, role_pref=role, setup_done=True)
    console_log.log("info", "setup", f"device set up: {devices.me['name']} ({b.role})")
    return devices.state()


def _roots():
    return {"suite": ROOT, "data": Path(DATA_DIR)}


class ExportReq(BaseModel):
    include_secrets: bool = False
    passphrase: str = ""


@app.post("/api/export")
def export_config(b: ExportReq):
    """Download a config bundle (zip). Secrets are left out unless asked for, and then encrypted with the passphrase."""
    try:
        data, man = portable.export_bundle(_roots(), [m.spec for m in modules.values()], b.include_secrets, b.passphrase,
                                           {"name": devices.me["name"], "id": devices.me["id"], "platform": sys.platform})
    except portable.ExportError as e:
        raise HTTPException(400, str(e))
    name = time.strftime("pinguino-config-%Y%m%d-%H%M%S") + (".secrets" if b.include_secrets else "") + ".zip"
    try:
        out = Path(DATA_DIR) / "exports"
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(data)
    except OSError:
        pass
    console_log.log("info", "setup", f"config exported ({len(man['files'])} files{', with encrypted secrets' if b.include_secrets else ''})")
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/import")
async def import_config(request: Request, apply: bool = False):
    """Body = the bundle zip. Dry-run unless apply=true. Passphrase (if the bundle has secrets) in the X-Passphrase header."""
    body = await request.body()
    try:
        rep = portable.import_bundle(_roots(), [m.spec for m in modules.values()], body, request.headers.get("x-passphrase", ""), apply)
    except portable.ExportError as e:
        raise HTTPException(400, str(e))
    if apply:
        console_log.log("info", "setup", f"config imported from {rep.get('from') or 'a bundle'}: " + ", ".join(f"{f['arc']} {f['status']}" for f in rep["files"] if f["status"] != "same"))
    return rep


@app.get("/api/device")
def device_get():
    return devices.state()


@app.post("/api/device/config")
def device_config(b: DevConfig):
    devices.configure(b.name, b.priority, b.role_pref)
    return devices.state()


@app.post("/api/device/take")
def device_take():
    devices.take_control()
    console_log.log("info", "device", "manual: take control here")
    reconcile_devices()
    return devices.state()


@app.post("/api/device/release")
def device_release():
    devices.release_pin()
    reconcile_devices()
    return devices.state()


@app.post("/api/device/peer")
async def device_peer(request: Request):
    """Link delivers a peer's heartbeat here: body {"type": "device-hb", "payload": {...}} or the payload itself."""
    b = await request.json()
    return {"ok": devices.receive(b.get("payload", b) if isinstance(b, dict) else None)}


class Streaming(BaseModel):
    on: bool


@app.post("/api/device/streaming")
def device_streaming(b: Streaming):
    devices.set_streaming(b.on)
    return {"ok": True}


@app.get("/api/device/lease")
def device_lease():
    """For singleton modules (Host, Spotify): am I allowed to run on this device right now?"""
    st = devices.state()
    return {"is_master": st["is_master"], "master_id": st["master_id"], "master_name": st["master_name"], "device_id": devices.me["id"]}


@app.post("/api/voice/dispatch")
async def voice_dispatch(request: Request):
    """Voice commands: Listen (only Listen) asks the core to POST to another registered module's API with that module's token."""
    if getattr(request.state, "mod", None) != "listen":
        raise HTTPException(403, "only the listen module may dispatch voice commands")
    b = await request.json()
    m, path = modules.get(str(b.get("module", ""))), str(b.get("path", ""))
    if not m or not path.startswith("/api/") or ".." in path:
        raise HTTPException(400, "unknown module or bad path")
    if m.singleton and not devices.is_master():
        raise HTTPException(409, "that module runs on the master device")
    tok = module_token(m.id)
    try:
        r = requests.post(m.spec["url"] + path, json=b.get("body") or {}, timeout=10,
                          headers={"Authorization": f"Bearer {tok}", "X-Pinguino-Token": tok, "x-link-token": tok})
    except requests.RequestException as e:
        raise HTTPException(502, str(e)[:120])
    console_log.log("info" if r.ok else "warn", "voice", f"voice command -> {m.id}{path}: {r.status_code}", module="listen")
    return {"ok": r.ok, "status": r.status_code, "detail": r.text[:200]}


@app.get("/api/console")
def console_get(since: int = 0, limit: int = 300, min_level: str = "debug", module: str = "", q: str = ""):
    return {"seq": console_log.seq, "entries": console_log.query(since, max(1, min(limit, 2000)), min_level, module, q),
            "errors": console_log.errors_since(1800)}


@app.get("/api/prestream")
def prestream_get():
    return last_prestream or {"ts": None, "summary": {"pass": 0, "warn": 0, "fail": 0}, "items": []}


@app.post("/api/prestream/run")
def prestream_run():
    return run_prestream(slot="manual")


@app.get("/api/events/log")
def event_log(lines: int = 200):
    """Recent structured events (JSONL), newest last."""
    out = []
    for ln in tail_lines(EVENT_LOG, max(1, min(lines, 2000))):
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return {"events": out}


@app.post("/api/modules/{mid}/options")
def module_options(mid: str, b: Opt):
    s = load_settings()
    s["modules"].setdefault(mid, {}).update({k: v for k, v in b.model_dump().items() if v is not None})
    save_settings(s)
    return {"ok": True}


@app.post("/api/modules/{mid}/{action}")
def module_action(mid: str, action: str):
    m = modules.get(mid)
    if not m or action not in ("start", "stop", "restart"):
        raise HTTPException(404)
    if action in ("stop", "restart"):
        m.stop()
    if action in ("start", "restart"):
        m.start()
    return {"ok": True}


class Chan(BaseModel):
    channel: str


@app.post("/api/channel")
def set_channel(b: Chan):
    s = load_settings()
    s["channel"] = b.channel.strip().lower()
    save_settings(s)
    return {"ok": True}


class Sim(BaseModel):
    live: bool | None = None  # None = go back to real Twitch detection


@app.post("/api/simulate")
def simulate(b: Sim):
    """Test button: pretend we went live / offline without touching Twitch."""
    live_state["simulated"] = b.live
    if b.live is True and not live_state["live"]:
        live_state.update(live=True, since=time.time(), title="(simulated stream)", game="", viewers=0)
        on_transition(True)
    elif b.live is False and live_state["live"]:
        live_state.update(live=False, since=None, viewers=0)
        on_transition(False)
    return {"ok": True}


class Auto(BaseModel):
    on: bool


@app.post("/api/windows-autostart")
def windows_autostart(b: Auto):
    set_autostart(b.on)
    return {"ok": True, "on": autostart_enabled()}


@app.post("/api/quit")
def quit_suite():
    threading.Thread(target=lambda: (time.sleep(0.3), _shutdown()), daemon=True).start()
    return {"ok": True}


def _shutdown():
    for m in modules.values():
        m.stop()
    os._exit(0)


# ------------------------------------------------------------------ tray + main
def open_app():
    """Open the dashboard as a chromeless app window (Edge --app), falling back to the default browser."""
    url = f"http://127.0.0.1:{PORT}"
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        exe = Path(base or "") / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if exe.exists():
            subprocess.Popen([str(exe), f"--app={url}", "--window-size=1440,900"])
            return
    webbrowser.open(url)


def start_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        return
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=(24, 28, 38, 255), outline=(110, 168, 255, 255), width=3)
    d.ellipse((20, 22, 44, 52), fill=(240, 240, 245, 255))
    d.polygon([(28, 30), (36, 30), (32, 38)], fill=(255, 170, 40, 255))
    d.ellipse((24, 24, 28, 28), fill=(0, 0, 0, 255))
    d.ellipse((36, 24, 40, 28), fill=(0, 0, 0, 255))
    menu = pystray.Menu(
        pystray.MenuItem("Open PinguinoSuite", lambda: open_app(), default=True),
        pystray.MenuItem("Quit (stops all modules)", lambda: _shutdown()),
    )
    pystray.Icon("PinguinoSuite", img, "PinguinoSuite", menu).run_detached()


def already_running():
    try:
        return requests.get(f"http://127.0.0.1:{PORT}/api/capabilities", timeout=1).status_code in (200, 401)
    except Exception:
        return False


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:  # pythonw has no console: send output to a log
        sys.stdout = sys.stderr = open(LOGS / "suite.log", "a", buffering=1, encoding="utf8")
    headless = "--headless" in sys.argv  # launched by the Tauri shell: no tray/browser, the shell owns the window
    if already_running():
        if not headless:
            open_app()
        sys.exit(0)
    if not headless:
        start_tray()
        if "--background" not in sys.argv:
            threading.Timer(2.0, open_app).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
