"""PinguinoSuite as a Spotify Connect device: runs go-librespot as a child process (design: Docs/SPOTIFY_CONNECT.md).
No thread of its own: Engine.tick() calls apply() + tick() every second or two. Nothing here ever raises into the engine.
INDEX
What: child-process manager (config.yml writer, login code, health, back-off restarts, volume/output), output device lists.
  API: Connect.apply, tick, start, stop, restart, set_volume, set_output, ready_device, info, outputs; find_binary, write_config, list_outputs
Related: engine.py (player_live, _set_volume, prestream), server.py (/api/connect*), config_schema.py (connect_* settings)
"""
import atexit
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import console_log
import store

DEVICE_NAME = "PinguinoSuite"
BACKOFF_S = (2, 5, 15, 60, 60)                 # delays before restart 1..5, then we give up
HEALTH_S = 3.0
STABLE_S = 30.0                               # ready this long = the crash counter starts again
LOGIN_RE = re.compile(r"(?:visit the following link|authorize|open the link)[^h]*(https?://\S+)", re.I)
CODE_RE = re.compile(r"\bcode[\"':= ]+([A-Z0-9]{4,10}(?:-[A-Z0-9]{3,6})?)\b")
BAD_LINE = re.compile(r"\b(error|failed|fatal|panic)\b", re.I)
CRED_BAD = re.compile(r"(unknown|invalid|unsupported|unrecogni[sz]ed)[^\n]{0,60}credential|credential[^\n]{0,60}(unknown|invalid|unsupported)", re.I)
OUTPUT_BAD = re.compile(r"(wasapi|audio|output|device)[^\n]{0,80}(not found|no such|failed|error|unavailable|cannot)", re.I)
BITRATES = (96, 160, 320)
MOD = Path(__file__).parent


def platform_dir():
    return "win" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux"


def find_binary(base=None, platform=None):
    """bin/<os>/go-librespot[.exe] first, then bin/go-librespot[.exe] (the layout the spike left). SPOTIFY_CONNECT_BIN overrides (tests)."""
    env = os.environ.get("SPOTIFY_CONNECT_BIN")
    if env:
        return Path(env) if Path(env).exists() else None
    base = Path(base) if base else MOD / "bin"
    plat = platform or platform_dir()
    exe = "go-librespot.exe" if plat == "win" else "go-librespot"
    for p in (base / plat / exe, base / exe):
        if p.is_file():
            return p
    return None


def backend_for(platform=None):
    return {"win": "wasapi", "mac": "audio-toolbox"}.get(platform or platform_dir(), "alsa")


def _q(s):
    return json.dumps(str(s), ensure_ascii=False)          # a JSON string is a valid YAML double-quoted scalar


def write_config(path, port, volume, output="", bitrate=160, normalize=True, platform=None, credentials="device_auth", name=DEVICE_NAME):
    """The config.yml go-librespot reads. No secrets in it (login lives in state.json next to it, written by go-librespot)."""
    br = bitrate if bitrate in BITRATES else min(BITRATES, key=lambda b: abs(b - int(bitrate or 160)))
    lines = [f"device_name: {_q(name)}", "device_type: computer", "zeroconf_enabled: false",
             "credentials:", f"  type: {credentials}",
             f"audio_backend: {backend_for(platform)}"]
    if output:
        lines.append(f"audio_device: {_q(output)}")
    lines += [f"bitrate: {br}", "volume_steps: 100", f"initial_volume: {max(0, min(100, int(volume)))}", "ignore_last_volume: true",
              f"normalisation_disabled: {'false' if normalize else 'true'}", "log_level: info",
              "server:", "  enabled: true", "  address: 127.0.0.1", f"  port: {int(port)}"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_http(method, url, body=None, timeout=2.5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(200000)
            try:
                return r.status, (json.loads(raw) if raw else {})
            except ValueError:
                return r.status, {}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def free_port(want):
    for p in (want, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return want


def _popen_default(cmd, cwd):
    kw = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "cwd": cwd, "bufsize": 1,
          "text": True, "encoding": "utf-8", "errors": "replace"}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x08000000                # CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    if str(cmd[0]).endswith(".py"):
        cmd = [sys.executable, "-u"] + list(cmd)
    return subprocess.Popen(cmd, **kw)


def _stale_kill(pid):
    """Kill a leftover go-librespot from a previous module run (pid file); anything with another name is left alone."""
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=8,
                                 creationflags=0x08000000).stdout.lower()
            if "go-librespot" in out or ("python" in out and os.environ.get("SPOTIFY_CONNECT_BIN")):
                subprocess.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True, timeout=8, creationflags=0x08000000)
                return True
        else:
            out = subprocess.run(["ps", "-p", str(int(pid)), "-o", "comm=,args="], capture_output=True, text=True, timeout=8).stdout.lower()
            if "go-librespot" in out or ("python" in out and os.environ.get("SPOTIFY_CONNECT_BIN")):
                os.kill(int(pid), 15)
                return True
    except Exception:
        pass
    return False


def list_outputs():
    """Names of the PC's playback devices. Windows: WASAPI outputs via sounddevice if importable, else PowerShell endpoints; macOS: system_profiler."""
    names = []
    try:
        import sounddevice as sd
        apis = sd.query_hostapis()
        for d in sd.query_devices():
            api = apis[d["hostapi"]]["name"]
            if d["max_output_channels"] > 0 and ("WASAPI" in api if sys.platform.startswith("win") else True):
                names.append(d["name"])
    except Exception:
        names = []
    if not names:
        try:
            if sys.platform.startswith("win"):
                out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                      "Get-PnpDevice -Class AudioEndpoint -Status OK | Select-Object -ExpandProperty FriendlyName"],
                                     capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
                names = [x.strip() for x in out.splitlines() if x.strip()]
            elif sys.platform == "darwin":
                js = json.loads(subprocess.run(["system_profiler", "SPAudioDataType", "-json"], capture_output=True, text=True, timeout=10).stdout)
                for grp in js.get("SPAudioDataType", []):
                    for it in grp.get("_items", []):
                        if it.get("_name") and "output" in json.dumps(it).lower():
                            names.append(it["_name"])
        except Exception:
            names = []
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen


class Connect:
    def __init__(self, popen=None, http=None, clock=time.time, binary=None, outputs_fn=None, kill_stale=None, base=None):
        self.popen = popen or _popen_default
        self.http = http or default_http
        self.clock = clock
        self._binary = binary                        # fixed path (tests); None = look it up every time
        self._outputs_fn = outputs_fn or list_outputs
        self._kill_stale = kill_stale or _stale_kill
        self.base = base
        self.lock = threading.RLock()
        self.proc = None
        self.state = "off"                           # off | starting | waiting_login | ready | error
        self.enabled = False
        self.want = {"output": "", "port": 3678, "bitrate": 160, "normalize": True, "volume": 70}
        self.port = 0
        self.device_id = ""
        self.code = self.code_url = ""
        self.code_expires = 0
        self.last_error = ""
        self.restarts = 0
        self.tries = 0
        self.cred = "device_auth"
        self.output_note = ""
        self.output_applied = ""
        self.lines = []                              # last log lines (display only)
        self._next_start = 0.0
        self._health_at = 0.0
        self._ready_since = 0.0
        self._started_at = 0.0
        self._out_cache = (0.0, [])
        self._reader = None
        atexit.register(self.stop)

    # ---- paths
    def folder(self):
        p = store.folder() / "connect"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def binary(self):
        if self._binary:
            return Path(self._binary) if Path(self._binary).exists() else None
        return find_binary(self.base)

    def installed(self):
        b = self.binary()
        return bool(b and Path(b).exists())

    # ---- driven by the engine
    def apply(self, settings, volume=None):
        """Called every engine tick with the module settings: start/stop on connect_on, restart on a config change, output switch live."""
        with self.lock:
            self.enabled = bool(settings.get("connect_on"))
            want = {"output": str(settings.get("connect_output") or ""), "port": int(settings.get("connect_port") or 3678),
                    "bitrate": int(settings.get("connect_bitrate") or 160), "normalize": bool(settings.get("connect_normalize", True)),
                    "volume": int(volume if volume is not None else settings.get("player_volume", 70))}
            old = self.want
            self.want = want
            running = self.proc is not None
            if not self.enabled:
                if running or self.state != "off":
                    self.stop()
                return
            if running and (old["port"], old["bitrate"], old["normalize"]) != (want["port"], want["bitrate"], want["normalize"]):
                self.restart()
            elif running and old["output"] != want["output"]:
                self.set_output(want["output"])

    def start(self):
        with self.lock:
            if not self.enabled or self.proc is not None:
                return False
            b = self.binary()
            if not b:
                self.state, self.last_error = "error", "go-librespot is not installed on this PC (bin folder)"
                return False
            self.tries = 0 if self.state in ("off", "error") else self.tries
            return self._spawn(b)

    def _spawn(self, b):
        folder = self.folder()
        pidf = folder / "pid"
        try:
            old = int(pidf.read_text().strip())
            if old and self._kill_stale(old):
                console_log.info("connect", f"stopped a leftover go-librespot (pid {old})")
        except (OSError, ValueError):
            pass
        self.port = free_port(self.want["port"])
        try:
            write_config(folder / "config.yml", self.port, self.want["volume"], self.want["output"], self.want["bitrate"], self.want["normalize"],
                         credentials=self.cred)
            self.proc = self.popen([str(b), "--config_dir", str(folder)], str(folder))
        except Exception as e:                      # OSError (blocked exe), bad config dir...
            self.proc = None
            self.state, self.last_error = "error", f"could not start: {type(e).__name__}: {e}"[:200]
            console_log.error("connect", self.last_error, dedupe_s=30)
            return False
        try:
            pidf.write_text(str(getattr(self.proc, "pid", 0)))
        except OSError:
            pass
        self.state, self.device_id, self.code, self.code_url, self.last_error = "starting", "", "", "", ""
        self.output_note, self.output_applied = "", ""
        self._started_at, self._health_at, self._ready_since = self.clock(), 0.0, 0.0
        self._reader = threading.Thread(target=self._read, args=(self.proc,), daemon=True)
        self._reader.start()
        console_log.info("connect", f"started go-librespot on 127.0.0.1:{self.port}")
        return True

    def _read(self, proc):
        try:
            for raw in proc.stdout:
                self.feed(raw.rstrip("\r\n"))
        except Exception:
            pass

    def feed(self, line):
        """One line of go-librespot output (public so tests need no process)."""
        line = line[:400]
        if not line.strip():
            return
        with self.lock:
            self.lines.append(re.sub(r"https?://\S+", "<link>", line))
            del self.lines[:-30]
            m = LOGIN_RE.search(line)
            if m and self.state in ("starting", "waiting_login"):
                self.code_url = m.group(1)
            m = CODE_RE.search(line)
            if m and "pair" in line.lower():
                self.code = m.group(1)
            if CRED_BAD.search(line) and self.cred == "device_auth":
                self.cred = "interactive"          # this build does not know device_auth: next start uses the login-link flow
            if OUTPUT_BAD.search(line) and self.want["output"]:
                self.output_note = self._output_help()
        redacted = re.sub(r"https?://\S+", "<link>", line)         # the login link has a challenge in it: shown in the card, not in logs
        (console_log.warn if BAD_LINE.search(line) else console_log.info)("connect", "connect: " + redacted, dedupe_s=2)

    def _output_help(self):
        return ("Could not select the output device. In Windows open Settings > System > Sound > Volume mixer and set the output of "
                "PinguinoSuite to CABLE Input (VB-Audio Virtual Cable).") if sys.platform.startswith("win") else \
               "Could not select the output device: pick it in the system sound settings for this app."

    def tick(self):
        """One health/restart step; cheap, safe to call every second."""
        with self.lock:
            if not self.enabled:
                return
            now = self.clock()
            if self.proc is None:
                if self.state == "error" and self.tries > len(BACKOFF_S):
                    return                                   # gave up: only an explicit restart() continues
                if self.state == "error" and not self.installed():
                    return
                if now >= self._next_start and self.state in ("off", "error", "starting"):
                    b = self.binary()
                    if b:
                        self._spawn(b)
                    elif self.state == "off":
                        self.state, self.last_error = "error", "go-librespot is not installed on this PC (bin folder)"
                return
            rc = self.proc.poll()
            if rc is not None:
                return self._exited(rc, now)
            if now - self._health_at < HEALTH_S:
                return
            self._health_at = now
            self._health(now)

    def _exited(self, rc, now):
        self.proc = None
        tail = " | ".join(self.lines[-3:])[:200]
        self.tries += 1
        self.restarts += 1
        self.device_id = ""
        if self.tries > len(BACKOFF_S):
            self.state, self.last_error = "error", f"gave up after {len(BACKOFF_S)} restarts (exit {rc}). Press Restart. {tail}"[:300]
            console_log.error("connect", self.last_error, dedupe_s=60)
            return
        delay = BACKOFF_S[self.tries - 1]
        self._next_start = now + delay
        self.state, self.last_error = "error", f"go-librespot exited ({rc}); restarting in {delay} s. {tail}"[:300]
        console_log.warn("connect", self.last_error, dedupe_s=10)

    def _health(self, now):
        base = f"http://127.0.0.1:{self.port}"
        st, js = self.http("GET", base + "/status")                 # logged in beats a (maybe stale) pairing code
        if not (st == 200 and isinstance(js, dict) and js.get("device_id")) and self.state != "ready":
            st2, js2 = self.http("GET", base + "/auth/code")
            if st2 == 200 and isinstance(js2, dict) and (js2.get("url") or js2.get("code")):
                self.state = "waiting_login"
                self.code, self.code_url = str(js2.get("code") or self.code)[:40], str(js2.get("url") or self.code_url)[:600]
                self.code_expires = js2.get("expires_at") or 0
                return
        if st == 200 and isinstance(js, dict) and js.get("device_id"):
            if self.state != "ready":
                self.state, self.last_error = "ready", ""
                self._ready_since = now
                self.code = self.code_url = ""
                console_log.info("connect", "PinguinoSuite device is ready")
                if self.want["output"]:
                    self._apply_output(self.want["output"])
                self.http("POST", base + "/player/volume", {"volume": self.want["volume"]})
            self.device_id = str(js["device_id"])[:80]
            if self.tries and now - self._ready_since > STABLE_S:
                self.tries = 0
        elif self.state == "ready":                          # was fine, the API stopped answering
            self.state = "starting"
            self.device_id = ""
        elif self.state == "starting" and now - self._started_at > 60 and not self.last_error:
            self.last_error = "no answer from go-librespot yet"

    def _apply_output(self, name):
        st, _ = self.http("POST", f"http://127.0.0.1:{self.port}/player/output", {"device": name})
        if 200 <= st < 300:
            self.output_applied, self.output_note = name, ""
        else:
            self.output_applied = ""
            self.output_note = self._output_help()
            console_log.warn("connect", f"output switch answered HTTP {st}", dedupe_s=60)

    # ---- controls
    def stop(self):
        with self.lock:
            p, self.proc = self.proc, None
            was_ready = self.state == "ready"
            self.device_id = ""
            self.state = "off"
            if p is None:
                return
            if self.port and was_ready:
                self.http("POST", f"http://127.0.0.1:{self.port}/player/pause", {}, 1.0)       # best effort: don't leave a song hanging
            try:
                p.terminate()
                for _ in range(30):
                    if p.poll() is not None:
                        break
                    time.sleep(0.1)
                else:
                    p.kill()
            except Exception:
                pass
            try:
                (self.folder() / "pid").unlink()
            except OSError:
                pass
            console_log.info("connect", "go-librespot stopped")

    def restart(self):
        with self.lock:
            self.stop()
            self.tries = 0
            self._next_start = 0.0
            self.state = "off"
            return self.start() if self.enabled else False

    def set_volume(self, v):
        """True when go-librespot took the volume (0-100)."""
        with self.lock:
            if self.state != "ready":
                return False
            self.want["volume"] = max(0, min(100, int(v)))
            st, _ = self.http("POST", f"http://127.0.0.1:{self.port}/player/volume", {"volume": self.want["volume"]})
            return 200 <= st < 300

    def set_output(self, name):
        with self.lock:
            self.want["output"] = str(name or "")
            if self.state == "ready":
                self._apply_output(self.want["output"])
                write_config(self.folder() / "config.yml", self.port, self.want["volume"], self.want["output"], self.want["bitrate"],
                             self.want["normalize"], credentials=self.cred)

    def ready_device(self):
        """Spotify device id while go-librespot is up and logged in, else ''."""
        with self.lock:
            return self.device_id if self.enabled and self.state == "ready" and self.proc is not None else ""

    def outputs(self):
        now = self.clock()
        if now - self._out_cache[0] > 60 or not self._out_cache[1]:
            try:
                self._out_cache = (now, self._outputs_fn())
            except Exception:
                self._out_cache = (now, [])
        return list(self._out_cache[1])

    def info(self):
        with self.lock:
            return {"enabled": self.enabled, "installed": self.installed(), "state": self.state, "device_id": self.device_id,
                    "output": self.want["output"], "output_applied": self.output_applied, "output_note": self.output_note,
                    "port": self.port, "code": self.code, "code_url": self.code_url, "code_expires": self.code_expires,
                    "last_error": self.last_error, "restarts": self.restarts, "backend": backend_for(), "device_name": DEVICE_NAME,
                    "login_flow": self.cred, "log": self.lines[-5:]}
