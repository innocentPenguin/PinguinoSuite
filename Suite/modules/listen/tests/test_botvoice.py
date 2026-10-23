"""Listen drops bot speech: fake Voice server on a temp port (slow, 404, empty, overlapping, adjacent), speaking.json fallback."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LISTEN_DATA_DIR"] = tempfile.mkdtemp()   # never the real ears.db
import botvoice  # noqa: E402


class Fake:
    def __init__(self):
        self.mode, self.intervals, self.hits, self.since, self.speaking = "ok", [], 0, [], False
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.hits += 1
                outer.since.append(self.path)
                if outer.mode == "slow":
                    time.sleep(2.5)
                if outer.mode == "404":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                b = json.dumps({"now": time.time(), "speaking": outer.speaking, "intervals": outer.intervals}).encode() if outer.mode != "junk" else b"not json"
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                except OSError:
                    pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


class BotVoice(unittest.TestCase):
    def setUp(self):
        botvoice.reset_cache()
        self.f = Fake()

    def tearDown(self):
        self.f.srv.shutdown()

    def test_overlap_adjacent_and_empty(self):
        self.f.intervals = [[100.0, 104.0]]
        self.assertTrue(botvoice.is_bot(103.0, 105.0, base=self.f.url))     # overlaps the end
        botvoice.reset_cache()
        self.assertTrue(botvoice.is_bot(101.0, 102.0, base=self.f.url))     # inside
        botvoice.reset_cache()
        self.assertFalse(botvoice.is_bot(104.0, 106.0, base=self.f.url))    # adjacent: not an overlap
        self.assertFalse(botvoice.is_bot(96.0, 100.0, base=self.f.url))
        botvoice.reset_cache()
        self.f.intervals = []
        self.assertFalse(botvoice.is_bot(101.0, 102.0, base=self.f.url))

    def test_cached_for_two_seconds_and_asks_since_minus_5(self):
        self.f.intervals = [[100.0, 104.0]]
        botvoice.is_bot(110.0, 111.0, base=self.f.url)
        botvoice.is_bot(110.5, 111.5, base=self.f.url)
        self.assertEqual(self.f.hits, 1)
        self.assertIn("since=105.000", self.f.since[0])
        botvoice.is_bot(90.0, 91.0, base=self.f.url)   # older than the cached window: asks again
        self.assertEqual(self.f.hits, 2)

    def test_unreachable_falls_back(self):
        for mode in ("404", "junk"):
            botvoice.reset_cache()
            self.f.mode = mode
            self.assertTrue(botvoice.is_bot(1.0, 2.0, fallback=lambda: True, base=self.f.url))
            self.assertFalse(botvoice.is_bot(1.0, 2.0, fallback=lambda: False, base=self.f.url))
            self.assertFalse(botvoice.is_bot(1.0, 2.0, base=self.f.url))
        self.assertTrue(botvoice.is_bot(1.0, 2.0, fallback=lambda: True, base="http://127.0.0.1:1"))   # refused connection

    def test_slow_voice_times_out_fast(self):
        self.f.mode = "slow"
        t = time.time()
        self.assertTrue(botvoice.is_bot(1.0, 2.0, fallback=lambda: True, base=self.f.url))
        self.assertLess(time.time() - t, 2.0)

    def test_cache_not_used_for_a_segment_that_ended_after_it_was_fetched(self):
        now = time.time()
        self.f.intervals = []
        self.assertFalse(botvoice.is_bot(now - 1.0, now - 0.2, base=self.f.url))   # fetched now; segment ended 0.2 s ago: too fresh to trust a cache
        self.f.intervals = [[now - 0.4, now]]    # the bot started a moment later
        self.assertTrue(botvoice.is_bot(now - 0.8, now - 0.1, base=self.f.url))
        self.assertEqual(self.f.hits, 2)
        # an old segment is happy with the cache
        botvoice.reset_cache()
        botvoice.is_bot(now - 60, now - 59, base=self.f.url)
        botvoice.is_bot(now - 59, now - 58, base=self.f.url)
        self.assertEqual(self.f.hits, 3)

    def test_speaking_flag_is_an_open_interval(self):
        now = time.time()
        self.f.speaking = True
        self.assertTrue(botvoice.is_bot(now - 1.0, now - 0.2, base=self.f.url))
        botvoice.reset_cache()
        self.f.speaking = False
        self.assertFalse(botvoice.is_bot(now - 1.0, now - 0.2, base=self.f.url))

    def test_failure_is_cached_and_does_not_wait_again(self):
        self.f.mode = "slow"
        t = time.time()
        self.assertTrue(botvoice.is_bot(1.0, 2.0, fallback=lambda: True, base=self.f.url))
        self.assertLess(time.time() - t, 2.0)
        t = time.time()
        for _ in range(5):
            self.assertTrue(botvoice.is_bot(3.0, 4.0, fallback=lambda: True, base=self.f.url))
        self.assertLess(time.time() - t, 0.3)    # no more waiting on the hung Voice
        self.assertEqual(self.f.hits, 1)
        botvoice.reset_cache()                    # (the real code retries after FAIL_S)
        self.f.mode = "ok"
        self.assertFalse(botvoice.is_bot(1.0, 2.0, base=self.f.url))


class Wiring(unittest.TestCase):
    def test_setting_default_and_endpoint_validation(self):
        import config as cfg
        import server
        from fastapi.testclient import TestClient
        self.assertEqual(cfg.settings()["bot_speech"], "drop")
        c = TestClient(server.app, base_url="http://127.0.0.1:8765")
        self.assertEqual(c.post("/api/settings", json={"bot_speech": "bogus"}).status_code, 400)
        self.assertEqual(c.post("/api/settings", json={"bot_speech": "tag"}).json()["bot_speech"], "tag")
        c.post("/api/settings", json={"bot_speech": "drop"})


if __name__ == "__main__":
    unittest.main()
