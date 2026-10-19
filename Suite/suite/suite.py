"""PinguinoSuite - the host app. Supervises modules (PinguinoListen, ...), detects when the channel goes live,
tells modules about it, and serves the dashboard. Run via PinguinoSuite.bat (or autostart with Windows)."""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
import livedetect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
SETTINGS = ROOT / "suite_settings.json"
PORT = 8760
PY = sys.executable
DEFAULT_SETTINGS = {"channel": "innocentpenguin_", "poll_secs": 20, "offline_grace_secs": 180, "modules": {}}


# ------------------------------------------------------------------ settings
def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        s.update(json.loads(SETTINGS.read_text("utf8")))
    except Exception:
        pass
    return s


def save_settings(s):
    SETTINGS.write_text(json.dumps(s, indent=2), "utf8")


# ------------------------------------------------------------------ event bus (the seed of a Streamer.bot-style core)
class Bus:
    def __init__(self):
        self.clients, self.loop, self.history = set(), None, []

    def emit(self, type_, **data):
        ev = {"type": type_, "ts": time.time(), **data}
        self.history = (self.history + [ev])[-200:]
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
class Module:
    def __init__(self, spec):
        self.spec = spec
        self.id = spec["id"]
        self.proc = None
        self.healthy = False

    def opts(self):
        o = dict(self.spec.get("defaults", {}))
        o.update(load_settings()["modules"].get(self.id, {}))
        return o

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running or self._ping():
            return
        cmd = [PY if c == "{py}" else c for c in self.spec["cmd"]]
        log = open(LOGS / f"{self.id}.log", "ab")
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        self.proc = subprocess.Popen(cmd, cwd=ROOT / self.spec["cwd"], stdout=log, stderr=log, creationflags=flags)
        bus.emit("module", id=self.id, state="starting")

    def stop(self):
        if self.running:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
        self.proc, self.healthy = None, False
        bus.emit("module", id=self.id, state="stopped")

    def _ping(self):
        try:
            return requests.get(self.spec["url"] + self.spec.get("health", "/"), timeout=1.5).ok
        except Exception:
            return False

    def refresh(self):
        was = self.healthy
        self.healthy = self._ping()
        if self.healthy != was:
            bus.emit("module", id=self.id, state="running" if self.healthy else ("starting" if self.running else "stopped"))

    def call(self, hook):
        """POST a module's on_live / on_offline hook, retrying while it boots."""
        spec = self.spec.get(hook)
        if not spec:
            return
        for _ in range(40):
            try:
                r = requests.post(self.spec["url"] + spec["post"], timeout=10)
                bus.emit("hook", id=self.id, hook=hook, ok=r.ok, detail=r.text[:160])
                return
            except Exception:
                time.sleep(3)
        bus.emit("hook", id=self.id, hook=hook, ok=False, detail="module never answered")

    def public(self):
        st = "running" if self.healthy else "starting" if self.running else "stopped"
        return {"id": self.id, "name": self.spec["name"], "desc": self.spec.get("desc", ""), "url": self.spec["url"], "state": st, "options": self.opts()}


modules = {m["id"]: Module(m) for m in json.loads((ROOT / "modules.json").read_text("utf8"))}


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


def health_loop():
    while True:
        for m in modules.values():
            m.refresh()
        time.sleep(4)


# ------------------------------------------------------------------ windows autostart
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "PinguinoSuite")
            return True
    except OSError:
        return False


def set_autostart(on):
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
    bus.emit("suite", state="started")
    yield
    for m in modules.values():
        m.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.websocket("/ws")
async def ws(sock: WebSocket):
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
        return requests.get(f"http://127.0.0.1:{PORT}/api/state", timeout=1).ok
    except Exception:
        return False


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:  # pythonw has no console: send output to a log
        sys.stdout = sys.stderr = open(LOGS / "suite.log", "a", buffering=1, encoding="utf8")
    if already_running():
        open_app()
        sys.exit(0)
    start_tray()
    if "--background" not in sys.argv:
        threading.Timer(2.0, open_app).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
