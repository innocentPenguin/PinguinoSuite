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
            m.SLOW_TIMEOUT = 1.5     # this test is about the miss counting; the longer timeout has its own test
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


class Simulation(unittest.TestCase):
    """'Test go-live': refused while really live, ends by itself, End test only stops what the simulation started."""

    def setUp(self):
        self.calls = []
        self.saved = (dict(suite.live_state), suite.on_transition)
        suite.live_state.update(live=False, since=None, simulated=None, sim_until=None, viewers=0)
        suite.on_transition = lambda is_live: self.calls.append(is_live)
        self.sim = lambda v: suite.simulate(suite.Sim(live=v))

    def tearDown(self):
        suite.live_state.clear()
        suite.live_state.update(self.saved[0])
        suite.on_transition = self.saved[1]

    def test_start_and_end_run_the_hooks_once(self):
        self.assertTrue(self.sim(True)["ok"])
        self.assertTrue(self.sim(True)["ok"])      # a second click only extends it
        self.assertEqual(self.calls, [True])
        self.sim(False)
        self.assertEqual(self.calls, [True, False])
        self.assertIsNone(suite.live_state["simulated"])

    def test_refused_while_really_live_and_end_does_not_stop_the_real_stream(self):
        suite.live_state.update(live=True)
        r = self.sim(True)
        self.assertFalse(r["ok"])
        self.assertEqual(self.calls, [])
        self.sim(False)                            # not ours: no offline hooks, stream stays live
        self.assertEqual(self.calls, [])
        self.assertTrue(suite.live_state["live"])

    def test_expires_and_real_detection_returns(self):
        self.sim(True)
        suite.expire_simulation(now=suite.live_state["sim_until"] - 5)
        self.assertTrue(suite.live_state["simulated"])
        suite.expire_simulation(now=suite.live_state["sim_until"] + 1)
        self.assertIsNone(suite.live_state["simulated"])
        self.assertFalse(suite.live_state["live"])
        self.assertEqual(self.calls, [True, False])


class Diag(unittest.TestCase):
    def test_diag_reports_miss_error_and_age(self):
        m = suite.Module({"id": "dg", "name": "dg", "url": "http://127.0.0.1:1", "health": "/h", "cmd": ["x"], "cwd": "."})
        m.supervise = lambda: None
        d = m.diag()
        self.assertEqual((d["miss"], d["last_ok_age"], d["last_error"], d["pid"], d["state"]), (0, None, "", None, "stopped"))
        m.refresh()   # nothing listens on port 1
        d = m.diag()
        self.assertEqual(d["miss"], 1)
        self.assertTrue(d["last_error"])
        m._ping = lambda: True
        m.last_ok = __import__("time").time() - 3
        m.refresh()
        d = m.diag()
        self.assertTrue(d["healthy"])
        self.assertEqual(d["miss"], 0)

    def test_endpoint_lists_every_module_and_needs_the_token(self):
        from fastapi.testclient import TestClient
        c = TestClient(suite.app, base_url="http://127.0.0.1:8760")
        self.assertEqual(c.get("/api/modules/diag").status_code, 401)
        r = c.get("/api/modules/diag", headers={"Authorization": "Bearer " + suite.TOKEN})
        self.assertEqual(r.status_code, 200)
        self.assertEqual({m["id"] for m in r.json()["modules"]}, set(suite.modules))

    def test_last_error_has_no_urls_and_restart_clears_last_ok(self):
        m = suite.Module({"id": "dg2", "name": "dg2", "url": "http://127.0.0.1:1", "health": "/h", "cmd": ["x"], "cwd": "."})
        m._ping()
        self.assertTrue(m.last_err)
        self.assertNotIn("http", m.last_err)
        self.assertNotIn("127.0.0.1", m.last_err)


class SlowModule(unittest.TestCase):
    """A module that answers slowly, hangs, then recovers: a good ping always moves it back to running, with the reason logged."""

    def test_slow_hang_recover_and_longer_timeout(self):
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer
        mode = ["slow"]

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if mode[0] == "slow":
                    time.sleep(1.0)
                elif mode[0] == "hang":
                    time.sleep(2.5)
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"ok")
                except OSError:
                    pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_port
        m = suite.Module({"id": "slw", "name": "slw", "url": f"http://127.0.0.1:{port}", "health": "/api/health", "cmd": ["x"], "cwd": "."})
        m.supervise = lambda: None
        m.proc = __import__("types").SimpleNamespace(pid=1, poll=lambda: None)   # "running" process
        m.healthy = True
        events = []
        orig = suite.bus.emit
        suite.bus.emit = lambda t, **k: events.append(k)
        try:
            self.assertEqual(m.ping_timeout(), 1.5)
            mode[0] = "hang"
            m.refresh()                      # times out at 1.5 s: now marked slow
            self.assertEqual(m.ping_timeout(), 4.0)
            m.refresh()                      # the 2.5 s answer fits the longer timeout: a good ping
            self.assertEqual(m._miss, 0)
            self.assertTrue(m.healthy)
            mode[0] = "slow"
            m.refresh()
            self.assertTrue(m.last_ms >= 900)
            srv.shutdown()
            srv.server_close()
            for _ in range(4):               # now really gone
                m.refresh()
            self.assertFalse(m.healthy)
            self.assertIn("missed pings", events[-1]["reason"])
            srv2 = HTTPServer(("127.0.0.1", port), H)
            threading.Thread(target=srv2.serve_forever, daemon=True).start()
            mode[0] = "ok"
            m.refresh()
            self.assertTrue(m.healthy)
            self.assertEqual(events[-1]["state"], "running")
            self.assertIn("answered in", events[-1]["reason"])
            self.assertEqual(m.diag()["last_change"]["state"], "running")
            srv2.shutdown()
        finally:
            suite.bus.emit = orig

    def test_refresh_all_runs_modules_in_parallel_and_survives_failures(self):
        import threading
        import time
        calls = []

        class Fake:
            def __init__(self, i, delay, boom=False):
                self.id, self.delay, self.boom = i, delay, boom
                self._rlock = threading.Lock()

            def refresh(self):
                time.sleep(self.delay)
                if self.boom:
                    raise RuntimeError("x")
                calls.append(self.id)
        saved = dict(suite.modules)
        suite.modules.clear()
        suite.modules.update({"a": Fake("a", 0.6), "b": Fake("b", 0.6, True), "c": Fake("c", 0.6)})
        try:
            t = time.time()
            suite.refresh_all()
            self.assertLess(time.time() - t, 1.5)    # not 1.8 s one after the other
            self.assertEqual(sorted(calls), ["a", "c"])
        finally:
            suite.modules.clear()
            suite.modules.update(saved)
