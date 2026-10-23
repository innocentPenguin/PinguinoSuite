"""Opt-in watchdog: if the Suite core that started this Listen disappears (crash, hard kill) for longer than GRACE_S, Listen closes the
mic/GPU and exits instead of running on forever. Off unless PINGUINO_LISTEN_WATCHDOG=1, and only when the core's pid file exists (a standalone
Listen has none, so it is never touched). A restarted core rewrites the pid file with its own pid, so a normal restart is not mistaken for a death."""
import json
import os
import threading
import time
from pathlib import Path

GRACE_S = 30
POLL_S = 5


def enabled(env=None):
    return (env or os.environ).get("PINGUINO_LISTEN_WATCHDOG") == "1"


def core_file(env=None):
    d = (env or os.environ).get("PINGUINO_DATA_DIR")
    return Path(d) / "pids" / "core.json" if d else None


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259          # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


class CoreWatch:
    """tick() is called every POLL_S; on_gone() runs once when the core has been missing for GRACE_S. Injectable for tests."""

    def __init__(self, read_pid, alive, on_gone, now=time.time, grace=GRACE_S):
        self.read_pid, self.alive, self.on_gone, self.now, self.grace = read_pid, alive, on_gone, now, grace
        self.seen = False      # the core was seen alive at least once: without that this Listen was not started by a core
        self.gone_since = None
        self.fired = False

    def tick(self):
        if self.fired:
            return
        pid = self.read_pid()
        if pid and self.alive(pid):
            self.seen, self.gone_since = True, None
            return
        if not self.seen:
            return
        if self.gone_since is None:
            self.gone_since = self.now()
        elif self.now() - self.gone_since >= self.grace:
            self.fired = True
            self.on_gone()


def start(on_gone, env=None):
    """Start the watchdog thread if it is enabled; returns the CoreWatch or None."""
    f = core_file(env)
    if not enabled(env) or not f:
        return None

    def read():
        try:
            return json.loads(f.read_text("utf8")).get("pid")
        except (OSError, ValueError, AttributeError):
            return None
    w = CoreWatch(read, pid_alive, on_gone)

    def loop():
        while not w.fired:
            try:
                w.tick()
            except Exception:  # noqa: BLE001  (a watchdog must never take Listen down by itself)
                pass
            time.sleep(POLL_S)
    threading.Thread(target=loop, daemon=True, name="corewatch").start()
    return w
