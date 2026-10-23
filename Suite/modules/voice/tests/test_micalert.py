"""Mic-lost alert: fixed line, once per distinct alert, OFF by default, master decides. Fake Listen and fake player."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import server
from test_voice import mk, wait

ALERT = {"alert": None}


class FakeListen(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"mic_alert": ALERT["alert"]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class MicAlert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeListen)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.old = server.LISTEN_URL
        server.LISTEN_URL = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        server.LISTEN_URL = cls.old

    def run_loop(self, steps):
        n = [0]

        def sleep(_):
            if n[0] < len(steps):
                ALERT["alert"] = steps[n[0]]
            n[0] += 1
        ALERT["alert"] = steps[0]
        server.mic_loop(sleep=sleep, stop=lambda: n[0] > len(steps))

    def test_default_off_and_one_fixed_line_per_alert(self):
        a, b = {"kind": "missing", "message": "SECRET-ish text oauth:abcdefghijklmnop"}, {"kind": "fallback", "message": "other"}
        for enabled, expect in ((False, 0), (True, 2)):
            self.b, self.s, self.pl = mk()
            server.brain = self.b
            self.b.cfg["events"]["mic_alert"]["enabled"] = enabled
            self.b.cfg["events"]["mic_alert"]["cooldown_s"] = 0
            self.b.cfg["limits"]["dedupe_s"] = 0
            self.run_loop([a, a, None, b])
            time.sleep(0.5)
            self.assertEqual(len(self.s.calls), expect)
            for text, _, _ in self.s.calls:
                self.assertNotIn("SECRET", text)

    def test_master_off_is_silent(self):
        self.b, self.s, self.pl = mk(master=False)
        server.brain = self.b
        self.b.cfg["events"]["mic_alert"]["enabled"] = True
        self.run_loop([{"kind": "missing", "message": "x"}])
        time.sleep(0.3)
        self.assertEqual(self.s.calls, [])

    def test_listen_down_is_quiet(self):
        old = server.LISTEN_URL
        server.LISTEN_URL = "http://127.0.0.1:1"
        try:
            self.b, self.s, self.pl = mk()
            server.brain = self.b
            n = [0]
            server.mic_loop(sleep=lambda _: n.__setitem__(0, n[0] + 1), stop=lambda: n[0] > 1)
        finally:
            server.LISTEN_URL = old
        self.assertEqual(self.s.calls, [])

    def test_default_config_has_it_off(self):
        self.assertFalse(config.defaults()["events"]["mic_alert"]["enabled"])


if __name__ == "__main__":
    unittest.main()
