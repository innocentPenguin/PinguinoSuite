"""Module isolation: a restarted core adopts running modules, quit leaves them alone, stop only kills the port owner, one module's death is its own."""
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def serve():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def mod(port, mid="t"):
    return suite.Module({"id": mid, "name": mid, "url": f"http://127.0.0.1:{port}", "cmd": ["{py}", "-c", "raise SystemExit"], "cwd": "."})


class Adopt(unittest.TestCase):
    def setUp(self):
        self.srv = serve()
        self.port = self.srv.server_address[1]
        self.kills = []
        self._k, self._l = suite.kill_pid_tree, suite.listening_pid
        suite.kill_pid_tree = lambda pid: self.kills.append(pid)
        suite.listening_pid = lambda port: 4242

    def tearDown(self):
        suite.kill_pid_tree, suite.listening_pid = self._k, self._l
        self.srv.shutdown()
        self.srv.server_close()

    def test_running_module_is_adopted_not_respawned(self):
        m = mod(self.port)
        m.start()
        self.assertIsNone(m.proc)
        self.assertTrue(m.wanted and m.adopted)
        self.assertEqual(m.adopt_pid, 4242)

    def test_stop_kills_the_port_owner_only(self):
        m = mod(self.port)
        m.start()
        m.stop()
        self.assertEqual(self.kills, [4242])
        self.assertFalse(m.adopted or m.wanted)

    def test_stop_refuses_when_the_port_owner_changed(self):
        m = mod(self.port)
        m.start()
        suite.listening_pid = lambda port: 999   # pid was reused by something else
        m.stop()
        self.assertEqual(self.kills, [])

    def test_dead_adopted_module_is_restarted_and_others_untouched(self):
        a, b = mod(self.port, "a"), mod(self.port, "b")
        a.start()
        b.start()
        started = []
        a._ping = lambda: False
        a.start = lambda: started.append("a")
        a.last_try = 0
        a.refresh()
        self.assertEqual(started, ["a"])
        self.assertTrue(b.wanted and b.adopted and not b.failed)

    def test_five_deaths_in_five_minutes_marks_failed(self):
        a = mod(self.port, "a")
        a._ping = lambda: False
        a.start = lambda: None
        for _ in range(7):
            a.wanted, a.adopted, a.failed, a.last_try = True, True, False, 0
            a.refresh()
            if a.failed:
                break
        self.assertTrue(a.failed)


class Quit(unittest.TestCase):
    def test_default_quit_leaves_modules(self):
        stopped = []
        real_stop, real_exit = suite.Module.stop, os._exit
        suite.Module.stop = lambda self, deferred=False: stopped.append(self.id)
        os._exit = lambda code: None
        try:
            suite._shutdown()
            self.assertEqual(stopped, [])
            suite._shutdown(True)
            self.assertEqual(sorted(stopped), sorted(suite.modules))
        finally:
            suite.Module.stop, os._exit = real_stop, real_exit


if __name__ == "__main__":
    unittest.main()
