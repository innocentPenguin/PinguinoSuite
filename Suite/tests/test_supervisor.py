"""Core supervisor: never spawn a second copy while a hung one holds the module's port."""
import os
import socket
import sys
import tempfile
import unittest

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402


class PortGuard(unittest.TestCase):
    def test_busy_port_means_no_spawn(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            m = suite.Module({"id": "t", "name": "t", "url": f"http://127.0.0.1:{port}", "cmd": ["{py}", "-c", "raise SystemExit"], "cwd": "."})
            self.assertEqual(m.port(), port)
            m._ping = lambda: False
            m.start()
            self.assertIsNone(m.proc)
            self.assertTrue(m.wanted)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()


class Hysteresis(unittest.TestCase):
    """A busy module missing one health ping must not flip to 'starting' (the shell would swap its page for a card and lose the user's place)."""

    def test_one_or_three_missed_pings_keep_it_running_the_fourth_does_not(self):
        m = suite.Module({"id": "h", "name": "h", "url": "http://127.0.0.1:1", "cmd": ["x"], "cwd": "."})
        m.healthy = True
        m.supervise = lambda: None
        m._ping = lambda: False
        for _ in range(3):
            m.refresh()
            self.assertTrue(m.healthy)
        m.refresh()
        self.assertFalse(m.healthy)

    def test_an_answer_resets_the_count(self):
        m = suite.Module({"id": "h2", "name": "h2", "url": "http://127.0.0.1:1", "cmd": ["x"], "cwd": "."})
        m.healthy = True
        m.supervise = lambda: None
        for ok in (False, False, True, False, False, False):
            m._ping = lambda ok=ok: ok
            m.refresh()
        self.assertTrue(m.healthy)


class Recovery(unittest.TestCase):
    """A module that went 'starting' (slow, then failing) must return to 'running' once its health answers 200 again."""

    def test_slow_then_failing_then_healthy(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        mode = ["slow"]

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if mode[0] == "slow":
                    import time
                    time.sleep(2.0)   # longer than the 1.5 s ping timeout
                code = 503 if mode[0] == "fail" else 200
                try:
                    self.send_response(code)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"ok")
                except OSError:
                    pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            m = suite.Module({"id": "rec", "name": "rec", "url": f"http://127.0.0.1:{srv.server_port}", "health": "/api/health", "cmd": ["x"], "cwd": "."})
            m.healthy = True
            m.supervise = lambda: None
            events = []
            orig = suite.bus.emit
            suite.bus.emit = lambda *a, **k: events.append(k.get("state"))
            try:
                for _ in range(4):
                    m.refresh()           # slow: every ping times out
                self.assertFalse(m.healthy)
                mode[0] = "fail"
                m.refresh()
                self.assertFalse(m.healthy)
                mode[0] = "ok"
                m.refresh()
                self.assertTrue(m.healthy)
                self.assertEqual(m._miss, 0)
                self.assertEqual(events[-1], "running")
            finally:
                suite.bus.emit = orig
        finally:
            srv.shutdown()

    def test_one_broken_refresh_does_not_stop_the_others(self):
        a = suite.Module({"id": "ra", "name": "a", "url": "http://127.0.0.1:1", "cmd": ["x"], "cwd": "."})
        b = suite.Module({"id": "rb", "name": "b", "url": "http://127.0.0.1:1", "cmd": ["x"], "cwd": "."})
        seen = []

        def boom():
            raise RuntimeError("boom")
        a.refresh = boom
        b.refresh = lambda: seen.append("b")
        saved = dict(suite.modules)
        suite.modules.clear()
        suite.modules.update({"ra": a, "rb": b})
        try:
            suite.refresh_all()
        finally:
            suite.modules.clear()
            suite.modules.update(saved)
        self.assertEqual(seen, ["b"])
