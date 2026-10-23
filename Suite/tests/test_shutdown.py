"""Core shutdown hygiene: on stop, no module process (or its children) survives, ports are free, pid files are gone,
the health loop ends, and nothing can start a module afterwards."""
import os
import socket
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def port_open(p):
    try:
        socket.create_connection(("127.0.0.1", p), timeout=0.5).close()
        return True
    except OSError:
        return False


# a fake module: answers /health and keeps a grandchild process alive (like Listen's ffmpeg / yt-dlp)
SCRIPT = textwrap.dedent("""
    import subprocess, sys, time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    open(sys.argv[2], "w").write(str(child.pid))
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
""")


class Shutdown(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = dict(suite.modules)
        suite.modules.clear()
        suite.SHUTDOWN.clear()
        self.mods = []
        for i in range(2):
            port = free_port()
            childfile = self.tmp / f"child{i}.pid"
            spec = {"id": f"fake{i}", "name": f"fake{i}", "url": f"http://127.0.0.1:{port}", "health": "/health", "cwd": ".",
                    "cmd": ["{py}", "-c", SCRIPT, str(port), str(childfile)]}
            m = suite.Module(spec)
            suite.modules[m.id] = m
            self.mods.append((m, port, childfile))

    def tearDown(self):
        suite.SHUTDOWN.set()
        for m, _, _ in self.mods:
            try:
                m.stop()
            except Exception:  # noqa: BLE001
                pass
        suite.SHUTDOWN.clear()
        suite.modules.clear()
        suite.modules.update(self.saved)

    def _up(self):
        for m, port, childfile in self.mods:
            m.start()
        end = time.time() + 20
        while time.time() < end and not all(port_open(p) and cf.exists() and cf.read_text() for _, p, cf in self.mods):
            time.sleep(0.2)
        self.assertTrue(all(port_open(p) for _, p, _ in self.mods), "fake modules did not come up")

    def test_everything_is_gone_after_shutdown(self):
        self._up()
        children = [int(cf.read_text()) for _, _, cf in self.mods]
        pids = [m.proc.pid for m, _, _ in self.mods]
        self.assertTrue(all(suite.pid_alive(p) for p in pids + children))
        self.assertTrue(all(m._pidfile().exists() for m, _, _ in self.mods))
        loop = threading.Thread(target=suite.health_loop, daemon=True)
        loop.start()
        suite.shutdown_all()
        loop.join(8)
        self.assertFalse(loop.is_alive(), "the health loop did not end")
        time.sleep(0.5)
        for (m, port, _), pid in zip(self.mods, pids):
            self.assertFalse(suite.pid_alive(pid), f"{m.id} is still running")
            self.assertFalse(port_open(port), f"{m.id} still holds port {port}")
            self.assertFalse(m._pidfile().exists(), f"{m.id} left a pid file")
            self.assertFalse(m.wanted)
        for c in children:
            self.assertFalse(suite.pid_alive(c), "a module's child process survived")

    def test_nothing_starts_after_shutdown_began(self):
        suite.shutdown_all()
        m, port, _ = self.mods[0]
        m.start()                       # e.g. a health pass that was already running when shutdown began
        time.sleep(0.5)
        self.assertIsNone(m.proc)
        self.assertFalse(port_open(port))

    def test_one_failing_stop_does_not_leave_the_others_running(self):
        self._up()
        pids = [m.proc.pid for m, _, _ in self.mods]
        first = self.mods[0][0]
        real = first.stop

        def boom(*a, **k):
            raise RuntimeError("taskkill not found")
        first.stop = boom
        try:
            suite.shutdown_all()
        finally:
            first.stop = real
        time.sleep(0.5)
        self.assertFalse(suite.pid_alive(pids[1]))      # the second module was still stopped


if __name__ == "__main__":
    unittest.main()
