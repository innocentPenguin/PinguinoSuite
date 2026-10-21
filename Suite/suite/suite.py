"""PinguinoSuite - the host app. Supervises modules (PinguinoListen, ...), detects when the channel goes live,
tells modules about it, and serves the dashboard. Run via PinguinoSuite.bat (or autostart with Windows)."""
# INDEX-BEGIN (line numbers are of this file)
# INDEX: Suite core (FastAPI, 127.0.0.1:8760): module supervision, vault/help/prestream/devices/console APIs, serves the shell UI. Routes + public functions:
# Related: Suite/modules.json (module manifests), Docs/MODULE_CONTRACT.md, Suite/suite/{vault,helpdb,prestream,device,consolelog,integrations}.py, App/src/index.html
#   203  def module_token
#   232  def load_settings
#   243  def save_settings
#   275  def tail_lines
#   303  class Bus
#   328  def kill_tree
#   343  class Module
#   465  def discover_specs
#   488  def on_transition
#   499  def apply_stream
#   519  def twitch_loop
#   534  def process_control
#   576  def run_prestream
#   602  def prestream_loop
#   621  def reconcile_devices
#   642  def status_loop
#   660  def device_sync_loop
#   678  def health_loop
#   696  def autostart_enabled
#   708  def set_autostart
#   725  def lifespan
#   755  def guard
#   781  GET    /
#   782  def index
#   788  GET    /theme.css
#   789  def theme_css
#   797  GET    /bootstrap.js
#   798  def bootstrap_js
#   806  GET    /api/capabilities
#   807  def capabilities
#   813  WEBSOCKET /ws
#   814  def ws
#   830  GET    /api/state
#   831  def state
#   837  class Opt
#   843  GET    /api/modules/{mid}/probe
#   844  def module_probe
#   900  def declared_secrets
#   922  def vault_prestream_items
#   950  GET    /api/prefs
#   951  def prefs_get
#   956  POST   /api/prefs
#   957  def prefs_set
#   961  POST   /api/prefs/reset
#   962  def prefs_reset
#   966  GET    /api/help
#   967  def help_get
#   985  GET    /api/help/all
#   986  def help_all
#   991  GET    /api/vault
#   992  def vault_list
#  1012  class VaultValue
#  1016  GET    /api/vault/{name}
#  1017  def vault_read
#  1035  POST   /api/vault/import-plaintext
#  1036  def vault_import
#  1044  class Scrub
#  1049  POST   /api/vault/scrub
#  1050  def vault_scrub
#  1063  class Passphrase
#  1067  POST   /api/vault/backup
#  1068  def vault_backup
#  1078  POST   /api/vault/restore
#  1079  def vault_restore
#  1089  POST   /api/vault/{name}/set
#  1090  def vault_set
#  1107  POST   /api/vault/{name}/delete
#  1108  def vault_delete
#  1115  POST   /api/vault/{name}/test
#  1116  def vault_test
#  1132  GET    /api/integrations
#  1133  def integrations_get
#  1168  class PostReq
#  1173  POST   /api/modules/{mid}/post
#  1174  def module_post
#  1195  GET    /api/modules/{mid}/get
#  1196  def module_get
#  1211  GET    /api/modules/{mid}/logs
#  1212  def module_logs
#  1218  class DevConfig
#  1227  class Setup
#  1233  GET    /api/setup
#  1234  def setup_get
#  1240  POST   /api/setup
#  1241  def setup_post
#  1252  class ExportReq
#  1257  POST   /api/export
#  1258  def export_config
#  1280  def backup_cfg
#  1285  def backup_list
#  1293  def run_backup
#  1308  def backup_loop
#  1321  GET    /api/backup/auto
#  1322  def backup_auto_get
#  1326  POST   /api/backup/auto
#  1327  def backup_auto_set
#  1335  POST   /api/backup/auto/run
#  1336  def backup_auto_run
#  1344  POST   /api/import
#  1345  def import_config
#  1357  GET    /api/device
#  1358  def device_get
#  1362  POST   /api/device/config
#  1363  def device_config
#  1368  POST   /api/device/take
#  1369  def device_take
#  1376  POST   /api/device/release
#  1377  def device_release
#  1383  POST   /api/device/peer
#  1384  def device_peer
#  1390  class Streaming
#  1394  POST   /api/device/streaming
#  1395  def device_streaming
#  1400  GET    /api/device/lease
#  1401  def device_lease
#  1407  POST   /api/voice/dispatch
#  1408  def voice_dispatch
#  1428  GET    /api/console
#  1429  def console_get
#  1434  GET    /api/prestream/schedule
#  1435  def prestream_schedule_get
#  1439  POST   /api/prestream/schedule
#  1440  def prestream_schedule_set
#  1447  GET    /api/prestream
#  1448  def prestream_get
#  1452  POST   /api/prestream/run
#  1453  def prestream_run
#  1457  GET    /api/events/log
#  1458  def event_log
#  1469  POST   /api/modules/{mid}/enable
#  1470  def module_enable
#  1488  POST   /api/modules/{mid}/options
#  1489  def module_options
#  1496  POST   /api/modules/{mid}/{action}
#  1497  def module_action
#  1508  class Chan
#  1512  POST   /api/channel
#  1513  def set_channel
#  1520  class Sim
#  1524  POST   /api/simulate
#  1525  def simulate
#  1537  class Auto
#  1541  POST   /api/windows-autostart
#  1542  def windows_autostart
#  1547  POST   /api/quit
#  1548  def quit_suite
#  1560  def open_app
#  1571  def start_tray
#  1591  def already_running
# INDEX-END
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
import integrations  # noqa: E402
import vault as vaultlib  # noqa: E402
import helpdb  # noqa: E402
import prefs as prefslib  # noqa: E402
import templates as tplib  # noqa: E402

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
prefs_store = prefslib.Prefs(Path(DATA_DIR) / "prefs.json")
templates_store = tplib.Templates(Path(DATA_DIR) / "templates.json")  # saved settings templates per settings area
livedetect.ENV_FILES.append(ROOT.parent / "PinguinoSite" / ".env")  # frozen core: __file__ is inside the bundle, ROOT is the real Suite folder
try:
    vault = vaultlib.Vault(Path(DATA_DIR) / "vault.bin")  # encrypted key store (DPAPI on Windows, OS keychain elsewhere)
    console_log.redact = vault.redact
    livedetect.vault_get = lambda n: vault.get(n, by="core")
except Exception as _e:  # noqa: BLE001  (no key store on this OS: the vault endpoints answer 503, everything else works)
    vault = None
    console_log.log("warn", "vault", f"key vault unavailable: {str(_e)[:120]}")
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
        lvl = "warn" if ev.get("fail") or ev.get("warn") else "info"   # per-item failures are already logged as errors
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
        self.port_warned = 0.0
        self.last_try = 0.0

    @property
    def singleton(self):
        return bool(self.spec.get("singleton"))

    def port(self):
        try:
            return int(self.spec["url"].rsplit(":", 1)[1].split("/")[0])
        except (KeyError, ValueError, IndexError):
            return 0

    def opts(self):
        o = dict(self.spec.get("defaults", {}))
        o.update(load_settings()["modules"].get(self.id, {}))
        if self.spec.get("defaults", {}).get("always_start") and not o.get("override_off"):  # manifest pins these on unless the user unlocked and switched them off
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
        port = self.port()
        if port and integrations.tcp("127.0.0.1", port):    # something holds the port but does not answer health: a hung old copy. Spawning another would only crash on bind.
            if time.time() - self.port_warned > 60:
                self.port_warned = time.time()
                console_log.log("error", "supervisor", f"{self.id}: port {port} is held by a process that does not answer; not starting a second copy. Stop that process (or restart the Suite) to recover.", module=self.id)
            return
        cmd = [PY if c == "{py}" else c for c in self.spec["cmd"]]
        log = open(LOGS / f"{self.id}.log", "ab")
        if IS_WIN:
            extra = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            extra = {"start_new_session": True}
        self.proc = subprocess.Popen(cmd, cwd=ROOT / self.spec["cwd"], stdout=log, stderr=log,
                                     env={**os.environ, "PINGUINO_API_TOKEN": module_token(self.spec["id"]), "PINGUINO_DATA_DIR": DATA_DIR, "PINGUINO_CORE_URL": f"http://127.0.0.1:{PORT}"}, **extra)
        bus.emit("module", id=self.id, state="starting")
        if self.spec.get("on_start"):   # manifest hook fired once after launch (Listen: start the mic even when not live)
            threading.Thread(target=self.call, args=("on_start",), daemon=True).start()

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
        if self.wanted and not self.failed and self.proc is None and not self.deferred and time.time() - self.last_try > 15 and not self._ping():
            self.last_try = time.time()      # wanted but nothing running (e.g. start was skipped because a hung copy held the port): try again
            self.start()
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


PS_SKIP = {"up", "disk", "errors", "keys"}  # per-device facts: another device being fine says nothing about this one
local_prestream = {}   # this device's own latest checks, unmerged (also published to peers)
last_integrations = []  # this device's own integration list, unmerged


def _compute_prestream(slot=None, scheduled=False):
    mods = [{"id": m.id, "spec": m.spec, "state": m.public()["state"], "always_start": bool(m.spec.get("defaults", {}).get("always_start"))}
            for m in modules.values()]
    return prestream.run_checks(mods, module_token, CONSOLE_DIR, lambda: console_log.errors_since(1800), ROOT, slot, scheduled, extra=vault_prestream_items())


def run_prestream(slot=None, scheduled=False):
    """Run all readiness checks, post the result to the Console and the event bus (toast), keep it for /api/prestream.
    Green on any peer device overrides this device's warn/fail for the same item (device.green_merge)."""
    global last_prestream
    rep = _compute_prestream(slot, scheduled)
    device.green_merge(rep["items"], devices.peer_statuses(), lambda i: f"{i['module']}:{i['id']}", "status", {"pass"}, lambda i: i["id"] in PS_SKIP, "p")
    rep["summary"] = {s: sum(1 for i in rep["items"] if i["status"] == s) for s in ("pass", "warn", "fail")}
    for i in rep["items"]:
        k = f"{i['module']}:{i['id']}"
        if i["status"] != "pass" and not i.get("help") and helpdb.resolve(k, i["module"], i["id"], specs=_specs())[0] is None:
            _warn_nohelp(k, i["label"])
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
            due = prestream.due_slot(datetime.now(timezone.utc), done, prestream.clean_schedule(load_settings().get("prestream")))
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


def status_loop():
    """Every minute: take this device's own integration + pre-stream state and publish a compact copy to peers (via the heartbeat)."""
    global last_integrations, local_prestream
    time.sleep(20)
    while True:
        try:
            last_integrations = _integrations_local()
            local_prestream = _compute_prestream()
            devices.set_status({"i": {x["id"]: x["status"] for x in last_integrations if not x["id"].startswith(("key:", "vault:")) and x["group"] != "API keys"},
                                "p": {f"{x['module']}:{x['id']}": x["status"] for x in local_prestream["items"] if x["id"] not in PS_SKIP}, "ts": time.time()})
        except Exception as e:  # noqa: BLE001
            console_log.log("debug", "device", f"status snapshot failed: {e}")
        time.sleep(60)


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
    threading.Thread(target=status_loop, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()
    bus.emit("suite", state="started")
    yield
    for m in modules.values():
        m.stop()


app = FastAPI(lifespan=lifespan)


MODULE_PATHS = {"/api/device/peer", "/api/device/streaming", "/api/device/lease", "/api/voice/dispatch"}


def _module_path(request):
    p = request.url.path
    return p in MODULE_PATHS or (p.startswith("/api/vault/") and ((request.method == "GET" and p.count("/") == 3) or (request.method == "POST" and p.count("/") == 4 and p.endswith("/set"))))  # GET /api/vault/<name>, POST /api/vault/<name>/set


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
            if not ok and _module_path(request):  # modules (Link, Host...) may call these with their own token
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
    return Response(f.read_text("utf8") + chr(10) + "/* this device's personalisation */" + chr(10) + prefs_store.css(), media_type="text/css", headers={"Cache-Control": "no-cache"})


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


_site_cache = {"t": 0.0, "item": None}


def _mod_headers(mid):
    tok = module_token(mid)
    return {"Authorization": f"Bearer {tok}", "X-Pinguino-Token": tok, "x-link-token": tok}


def _integrations_for(m):
    name = m.spec.get("name", m.id)
    if m.public()["state"] != "running":
        return [{"id": f"{m.id}:module", "module": m.id, "group": name, "name": name, "status": "off", "detail": "not running", "page": True}]
    try:
        h, base = _mod_headers(m.id), m.spec["url"]
        if m.spec.get("integrations"):
            out = integrations.from_items(m.id, requests.get(base + m.spec["integrations"], headers=h, timeout=5).json(), name)
        elif m.id == "link":
            out = integrations.from_link_status(requests.get(base + "/api/status", headers=h, timeout=5).json())
        else:
            st = requests.get(base + m.spec.get("health", "/"), headers=h, timeout=5).json()
            out = integrations.from_connectors(m.id, st) if isinstance(st, dict) and st.get("connectors") else integrations.from_prestream(m.id, (last_prestream or {}).get("items", []))
            for x in out:
                x["group"] = x["group"] if x["group"] != m.id else name
    except Exception as e:  # noqa: BLE001
        out = [{"id": f"{m.id}:error", "module": m.id, "group": name, "name": name, "status": "error", "detail": f"could not read status: {str(e)[:100]}"}]
    for x in out:
        x["page"] = True
    return out or [{"id": f"{m.id}:ok", "module": m.id, "group": name, "name": name, "status": "connected", "detail": "running", "page": True}]


def _site_item():
    if time.time() - _site_cache["t"] < 60 and _site_cache["item"]:
        return _site_cache["item"]
    try:
        r = requests.head("https://innocentpenguin.com", timeout=4, allow_redirects=True)
        st, d = ("connected", f"HTTP {r.status_code}") if r.status_code < 500 else ("error", f"HTTP {r.status_code}")
    except requests.RequestException as e:
        st, d = "error", f"unreachable: {str(e)[:80]}"
    _site_cache.update(t=time.time(), item={"id": "site:web", "module": "core", "group": "Site", "name": "innocentpenguin.com", "status": st, "detail": d,
                                            "connect_url": "https://innocentpenguin.com", "connect_label": "Open"})
    return _site_cache["item"]


# ------------------------------------------------------------------ key vault
def declared_secrets(m):
    """Manifest "secrets": ["NAME", ...] or [{name, label, test, required}] -> [{name, label, test, required}]."""
    out = []
    for s in m.spec.get("secrets", []):
        d = {"name": s} if isinstance(s, str) else dict(s)
        if vaultlib.NAME_RE.match(str(d.get("name", ""))):
            out.append({"name": d["name"], "label": d.get("label", d["name"]), "test": d.get("test"), "required": bool(d.get("required")), "module": m.id,
                        "help": helpdb.clean_help(d.get("help"))})
    return out


def _vault_or_503():
    if vault is None:
        raise HTTPException(503, "key vault unavailable on this device")
    return vault


def _plaintext_files():
    rt = Path(DATA_DIR)
    return [rt / "settings.json", rt / "chat_settings.json", rt / "host_secrets.json", rt / "bots_secrets.json"]


def vault_prestream_items():
    """Missing declared keys, reported by the pre-stream check (fail only for keys marked required by an always-start module)."""
    if vault is None:
        return []
    have, out = set(vault.names()), []
    for m in modules.values():
        miss = [s for s in declared_secrets(m) if s["name"] not in have]
        if miss:
            hard = any(s["required"] for s in miss) and bool(m.spec.get("defaults", {}).get("always_start"))
            out.append({"module": m.id, "id": "keys", "label": "API keys in the vault", "status": "fail" if hard else "warn",
                        "detail": "missing: " + ", ".join(s["name"] for s in miss)[:160]})
    return out


_nohelp_warned = set()


def _specs():
    return {m.id: m.spec for m in modules.values()}


def _warn_nohelp(key, shown=""):
    """A non-green item nobody wrote help for: say so once in the Console so the owner of that module fills it in."""
    if key and key not in _nohelp_warned:
        _nohelp_warned.add(key)
        console_log.log("warn", "help", f"no help written yet for '{key}'{(' (' + shown + ')') if shown else ''}: add \"help\" in the module manifest or on the item")


@app.get("/api/prefs")
def prefs_get():
    """This device's UI preferences (theme, layout, nav, dashboard cards, sounds, saved profiles)."""
    return prefs_store.load()


@app.post("/api/prefs")
def prefs_set(b: dict):
    return prefs_store.save(b)


@app.post("/api/prefs/reset")
def prefs_reset():
    return prefs_store.reset()


def _tpl(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except tplib.TemplateError as e:
        return JSONResponse({"ok": False, "error": e.msg, **e.extra}, status_code=e.status)


@app.get("/api/templates")
def templates_list(area: str):
    """Saved settings templates of one settings area (name, createdAt, values)."""
    r = _tpl(templates_store.list, area)
    return r if isinstance(r, JSONResponse) else {"ok": True, "area": area, "templates": r, "max": tplib.MAX_PER_AREA}


@app.post("/api/templates")
def templates_save(b: dict):
    """Save the current values of a settings area under a name. 409 {exists:true} when the name is taken and overwrite is not set."""
    r = _tpl(templates_store.save, b.get("area"), b.get("name"), b.get("values"), bool(b.get("overwrite")))
    return r if isinstance(r, JSONResponse) else {"ok": True, "template": r}


@app.post("/api/templates/rename")
def templates_rename(b: dict):
    r = _tpl(templates_store.rename, b.get("area"), b.get("id"), b.get("name"))
    return r if isinstance(r, JSONResponse) else {"ok": True, "template": r}


@app.post("/api/templates/delete")
def templates_delete(b: dict):
    r = _tpl(templates_store.delete, b.get("area"), b.get("id"))
    return r if isinstance(r, JSONResponse) else {"ok": True}


@app.get("/api/help")
def help_get(key: str = "", module: str = "", item: str = "", source: str = "", msg: str = ""):
    """Help for one clickable thing. key = item id ("core:obs", "multi:twitch", "module:host:failed"); for Console lines pass module/source/msg."""
    h, k = None, key
    if key.startswith("vault:"):  # a key row: the help its module wrote for that secret, else the generic key help
        nm = key[6:]
        h = next((d["help"] for m in modules.values() for d in declared_secrets(m) if d["name"] == nm and d.get("help")), None)
        if h is None and nm == "OBS_WS_PASSWORD":
            h = helpdb.CATALOG["obs"]
        if h is None:
            h = helpdb.CATALOG["vault_key"]
    if h is None:
        h, k = helpdb.resolve(key, module, item, source, msg[:300], _specs())
    if h is None:
        _warn_nohelp(k or f"{module}:{source}", msg[:60])
        return {"found": False, "key": k}
    return {"found": True, "key": k, "help": h}


@app.get("/api/help/all")
def help_all():
    """Index of every topic that has help (core + modules), for the Help page."""
    return {"topics": helpdb.topics(_specs())}


@app.get("/api/vault")
def vault_list():
    """Which keys are set / missing, when they were set and last read. Values are never returned."""
    v = _vault_or_503()
    decl = {}
    for m in modules.values():
        for s in declared_secrets(m):
            decl.setdefault(s["name"], []).append(s)
    names = sorted(set(v.names()) | set(decl))
    keys = []
    for n in names:
        info = v.info(n)
        d = decl.get(n, [])
        keys.append({"name": n, "set": info is not None, **(info or {}), "declared_by": [x["module"] for x in d],
                     "label": next((x["label"] for x in d if x["label"] != n), n), "testable": any(x.get("test") for x in d),
                     "required": any(x["required"] for x in d),
                     "help": next((x["help"] for x in d if x.get("help")), None) or (helpdb.CATALOG["obs"] if n == "OBS_WS_PASSWORD" else helpdb.CATALOG["vault_key"])})
    return {"backend": type(v.backend).__name__.replace("Backend", "").lower(), "is_master": devices.is_master(), "keys": keys,
            "plaintext": integrations.plaintext_summary(vaultlib.scan_plaintext(_plaintext_files()), v)}


class VaultValue(BaseModel):
    value: str


@app.get("/api/vault/{name}")
def vault_read(name: str, request: Request):
    """Module-facing: a module reads a key it declared in its manifest ("secrets"). The app token can NOT read values."""
    mod = getattr(request.state, "mod", None)
    if not mod:
        raise HTTPException(403, "values are only readable by the module that declares them")
    v = _vault_or_503()
    if not any(s["name"] == name for s in declared_secrets(modules[mod])):
        console_log.log("warn", "vault", f"{mod} asked for undeclared key {name} (denied)", module=mod)
        raise HTTPException(403, "key not declared in this module's manifest")
    if not devices.solo() and not devices.is_master():
        raise HTTPException(409, f"the vault is held by the master device ({devices.state()['master_name']})")
    val = v.get(name, by=mod)
    if val is None:
        raise HTTPException(404, "key not set")
    console_log.log("debug", "vault", f"{mod} read {name}", module=mod)
    return {"name": name, "value": val}


@app.post("/api/vault/import-plaintext")
def vault_import(overwrite: bool = False):
    """Copy secrets found in the plaintext config files into the vault. The files are NOT changed (scrub them after verifying)."""
    v = _vault_or_503()
    n = vaultlib.import_plaintext(v, _plaintext_files(), overwrite)
    console_log.log("info", "vault", f"imported {n} key(s) from plaintext files")
    return {"imported": n}


class Scrub(BaseModel):
    file: str
    confirm: bool = False


@app.post("/api/vault/scrub")
def vault_scrub(b: Scrub):
    """Blank vault-held secrets in ONE plaintext file. Only after the module that uses them was verified to read the vault."""
    v = _vault_or_503()
    f = next((p for p in _plaintext_files() if p.name == b.file), None)
    if not f or not f.is_file():
        raise HTTPException(404, "not a known plaintext file")
    if not b.confirm:
        raise HTTPException(400, "send confirm=true once the module is verified to read from the vault")
    n = vaultlib.scrub_plaintext(v, f)
    console_log.log("info", "vault", f"blanked {n} plaintext secret(s) in {f.name}")
    return {"blanked": n}


class Passphrase(BaseModel):
    passphrase: str


@app.post("/api/vault/backup")
def vault_backup(b: Passphrase):
    v = _vault_or_503()
    try:
        data = v.export_backup(b.passphrase)
    except vaultlib.VaultError as e:
        raise HTTPException(400, str(e))
    console_log.log("info", "vault", "vault backup exported (passphrase-encrypted)")
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": 'attachment; filename="pinguino-vault-backup.pgb"'})


@app.post("/api/vault/restore")
async def vault_restore(request: Request, merge: bool = True):
    v = _vault_or_503()
    try:
        n = v.restore_backup(await request.body(), request.headers.get("x-passphrase", ""), merge)
    except vaultlib.VaultError as e:
        raise HTTPException(400, str(e))
    console_log.log("info", "vault", f"vault restored from backup ({n} key(s) added)")
    return {"restored": n}


@app.post("/api/vault/{name}/set")
def vault_set(name: str, b: VaultValue, request: Request):
    """Set/rotate a key. The app token may write any name; a module token only names that module declared (e.g. a fresh Twitch token after re-sign-in)."""
    v = _vault_or_503()
    mod = getattr(request.state, "mod", None)
    if mod and not any(s["name"] == name for s in declared_secrets(modules[mod])):
        console_log.log("warn", "vault", f"{mod} tried to write undeclared key {name} (denied)", module=mod)
        raise HTTPException(403, "key not declared in this module's manifest")
    if mod and not devices.solo() and not devices.is_master():
        raise HTTPException(409, f"the vault is held by the master device ({devices.state()['master_name']})")
    try:
        v.set(name, b.value.strip())
    except vaultlib.VaultError as e:
        raise HTTPException(400, str(e))
    console_log.log("info", "vault", f"key {name} set" + (f" by {mod}" if mod else ""), module=mod or "core")
    return {"ok": True}


@app.post("/api/vault/{name}/delete")
def vault_delete(name: str):
    v = _vault_or_503()
    ok = v.delete(name)
    console_log.log("info", "vault", f"key {name} deleted" if ok else f"key {name} was not set")
    return {"ok": ok}


@app.post("/api/vault/{name}/test")
def vault_test(name: str):
    """Run the integration test the declaring module attached to this key (manifest "test" path, POSTed with the module token)."""
    v = _vault_or_503()
    if v.peek(name) is None:
        return {"ok": False, "detail": "key is not set"}
    for m in modules.values():
        for s in declared_secrets(m):
            if s["name"] == name and s.get("test"):
                try:
                    r = requests.post(m.spec["url"] + s["test"], json={}, headers=_mod_headers(m.id), timeout=15)
                    return {"ok": r.ok, "detail": r.text[:200]}
                except requests.RequestException as e:
                    return {"ok": False, "detail": f"module not answering: {str(e)[:100]}"}
    return {"ok": None, "detail": "this key has no test; the module checks it when it connects"}


@app.get("/api/integrations")
def integrations_get():
    """Every outside connection in one list: module-reported, plus Streamer.bot, OBS, the site and which API keys are set.
    An item that is green on any peer device overrides this device's warn/fail (shows which device); keys/vault items never merge."""
    items = _integrations_local()
    device.green_merge(items, devices.peer_statuses(), lambda i: i["id"], "status", {"connected"},
                       lambda i: i["id"].startswith(("key:", "vault:")) or i["id"].endswith(":module") or i["group"] == "API keys", "i")
    for i in items:
        if i["status"] in ("needs_auth", "error") and not i.get("help") and helpdb.resolve(i["id"], i.get("module", ""), i["id"].split(":", 1)[-1], specs=_specs())[0] is None:
            _warn_nohelp(i["id"], i["name"])
    return {"ts": time.time(), "items": items}


def _integrations_local():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_integrations_for, m) for m in modules.values()]
        site = pool.submit(_site_item)
        items = [x for f in futs for x in f.result()]
        items.append(site.result())
    for label, port, note in (("Streamer.bot", 8080, "legacy bridge; not needed once Host replaces it"), ("OBS", 4455, "OBS websocket")):
        up = integrations.tcp("127.0.0.1", port)
        items.append({"id": f"core:{label}", "module": "core", "group": "Streaming tools", "name": label, "status": "connected" if up else "off",
                      "detail": f"reachable on :{port}" if up else f"not reachable ({note})"})
    if vault is not None:
        have = set(vault.names())
        for m in modules.values():
            for s in declared_secrets(m):
                items.append({"id": f"key:{s['name']}", "module": m.id, "group": "API keys", "name": f"{s['label']}", "status": "connected" if s["name"] in have else "needs_auth",
                              "detail": f"in the vault ({m.spec.get('name', m.id)})" if s["name"] in have else "key missing: add it below"})
        pt = integrations.plaintext_summary(vaultlib.scan_plaintext(_plaintext_files()), vault)
        items.append({"id": "vault:plaintext", "module": "core", "group": "API keys", "name": "Plaintext keys on disk", "status": "needs_auth" if pt["total"] else "connected",
                      "detail": f"{pt['total']} key(s) still in config files ({pt['unmigrated']} not yet in the vault): import them below" if pt["total"] else "none"})
    return items


class PostReq(BaseModel):
    path: str
    body: dict | list | None = None


@app.post("/api/modules/{mid}/post")
def module_post(mid: str, b: PostReq):
    """POST to one of a module's /api/ paths on the UI's behalf (the Integrations 'Test' buttons)."""
    m = modules.get(mid)
    if not m:
        raise HTTPException(404)
    if not b.path.startswith("/api/") or ".." in b.path:
        raise HTTPException(400, "path must be under /api/")
    if m.singleton and not devices.is_master():
        raise HTTPException(409, "that module runs on the master device")
    try:
        r = requests.post(m.spec["url"] + b.path, json=b.body or {}, headers=_mod_headers(mid), timeout=15)
    except requests.RequestException as e:
        raise HTTPException(502, str(e)[:120])
    out = {"ok": r.ok, "status": r.status_code, "detail": r.text[:300]}
    try:
        out["json"] = r.json()      # the full parsed body: detail is cut at 300 chars, which breaks JSON such as a long sign-in URL
    except ValueError:
        pass
    return out


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


# ---- automatic config backups (no secrets): Data/backups/auto, newest N kept
AUTO_DIR = Path(DATA_DIR).parent / "backups" / "auto"


def backup_cfg():
    c = load_settings().get("backup") or {}
    return {"enabled": bool(c.get("enabled", True)), "every_hours": max(1, min(168, int(c.get("every_hours", 24) or 24))), "keep": max(1, min(60, int(c.get("keep", 7) or 7)))}


def backup_list():
    try:
        fs = sorted(AUTO_DIR.glob("pinguino-config-auto-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        fs = []
    return [{"name": f.name, "ts": f.stat().st_mtime, "size": f.stat().st_size} for f in fs]


def run_backup(why="scheduled"):
    data, man = portable.export_bundle(_roots(), [m.spec for m in modules.values()], False, "",
                                       {"name": devices.me["name"], "id": devices.me["id"], "platform": sys.platform})
    AUTO_DIR.mkdir(parents=True, exist_ok=True)
    name = time.strftime("pinguino-config-auto-%Y%m%d-%H%M%S") + ".zip"
    (AUTO_DIR / name).write_bytes(data)
    for old in backup_list()[backup_cfg()["keep"]:]:
        try:
            (AUTO_DIR / old["name"]).unlink()
        except OSError:
            pass
    console_log.log("info", "setup", f"config backup ({why}): {name}, {len(man['files'])} files, no secrets", "backup")
    return name


def backup_loop():
    time.sleep(90)
    while True:
        try:
            c = backup_cfg()
            last = (backup_list() or [{"ts": 0}])[0]["ts"]
            if c["enabled"] and devices.is_master() and time.time() - last > c["every_hours"] * 3600:
                run_backup()
        except Exception as e:  # noqa: BLE001
            console_log.log("warn", "setup", f"automatic backup failed: {e}", "backup")
        time.sleep(600)


@app.get("/api/backup/auto")
def backup_auto_get():
    return {**backup_cfg(), "files": backup_list(), "dir": str(AUTO_DIR)}


@app.post("/api/backup/auto")
def backup_auto_set(b: dict):
    s = load_settings()
    cur = backup_cfg()
    s["backup"] = {"enabled": bool(b.get("enabled", cur["enabled"])), "every_hours": b.get("every_hours", cur["every_hours"]), "keep": b.get("keep", cur["keep"])}
    save_settings(s)
    return backup_auto_get()


@app.post("/api/backup/auto/run")
def backup_auto_run():
    try:
        name = run_backup("manual")
    except portable.ExportError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "name": name, **backup_auto_get()}


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


@app.get("/api/prestream/schedule")
def prestream_schedule_get():
    return prestream.clean_schedule(load_settings().get("prestream"))


@app.post("/api/prestream/schedule")
def prestream_schedule_set(b: dict):
    s = load_settings()
    s["prestream"] = prestream.clean_schedule(b)
    save_settings(s)
    return s["prestream"]


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


@app.post("/api/modules/{mid}/enable")
def module_enable(mid: str, b: dict):
    """The on/off switch: on = enabled + starts with the Suite + start now; off = stop now + no autostart. Persisted.
    Modules the manifest pins on (always_start) only switch off via the UI's unlock; that is remembered as override_off."""
    m = modules.get(mid)
    if not m:
        raise HTTPException(404)
    on = bool(b.get("on"))
    s = load_settings()
    s["modules"].setdefault(mid, {}).update({"enabled": on, "start_with_suite": on, "override_off": (not on) and bool(m.spec.get("defaults", {}).get("always_start"))})
    save_settings(s)
    console_log.log("info", "core", f"module {mid} switched {'on' if on else 'off'}", "modules")
    if on:
        m.start()
    else:
        m.stop()
    return {"ok": True, "enabled": on}


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
