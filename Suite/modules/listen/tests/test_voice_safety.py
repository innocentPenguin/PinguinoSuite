"""HARD RULE: no voice command may start/stop the stream or touch OBS."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice  # noqa: E402


class NoStreamControl(unittest.TestCase):
    def test_allowed_and_refused(self):
        ok = voice.action_allowed
        self.assertTrue(ok({"type": "marker", "label": "clip"}))
        self.assertTrue(ok({"type": "call", "module": "spotify", "path": "/api/chat-command"}))
        for m, p in [("obs", "/api/anything"), ("link", "/api/obs/StartStream"), ("host", "/api/stream/start"), ("spotify", "/api/go-live"),
                     ("voice", "/api/obs/scene"), ("", "/api/chat-command"), ("host", "/api/run")]:
            self.assertFalse(ok({"type": "call", "module": m, "path": p}), (m, p))

    def test_run_action_refuses_before_any_network(self):
        r = voice.run_action({"phrase": "go live", "action": {"type": "call", "module": "link", "path": "/api/obs/StartStream", "body": {}}}, "go live", {}, None)
        self.assertFalse(r["ok"])
        self.assertIn("refused", r["detail"])


if __name__ == "__main__":
    unittest.main()
