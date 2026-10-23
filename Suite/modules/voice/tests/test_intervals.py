"""Speech intervals: what Listen reads to skip the bot's own voice. Temp data dir, fake player (nothing is played)."""
import json
import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import server
from test_voice import FakePlayer, mk, wait


class Spy(FakePlayer):
    """Records what speaking.json says while the 'playback' is running."""
    def play(self, wav, secs, device=""):
        self.during = json.loads(config.path("speaking.json").read_text())
        return super().play(wav, secs, device)


class Intervals(unittest.TestCase):
    def setUp(self):
        self.b, self.s, _ = mk()
        self.b.player = Spy()
        server.brain = self.b

    def speak(self):
        t0 = time.time()
        self.b.handle({"kind": "say", "message": "hello there friends", "manual": True})
        wait(self.b.player, 1)
        time.sleep(0.3)
        return t0, time.time()

    def test_played_line_gives_interval_and_flag(self):
        t0, t1 = self.speak()
        self.assertTrue(self.b.player.during["speaking"])
        self.assertGreater(self.b.player.during["until"], t0)
        after = json.loads(config.path("speaking.json").read_text())
        self.assertFalse(after["speaking"])
        r = server.g_intervals(None, {})
        self.assertEqual(len(r["intervals"]), 1)
        a, e = r["intervals"][0]
        self.assertGreaterEqual(a, t0 - 0.3)
        self.assertLessEqual(a, t1)
        self.assertGreater(e, a)
        self.assertGreaterEqual(e - a, 1.0)      # the 1 s tail covers transcription lag
        self.assertFalse(r["speaking"])
        self.assertGreaterEqual(r["now"], t1 - 0.5)

    def test_since_filter(self):
        self.speak()
        a, e = server.g_intervals(None, {})["intervals"][0]
        self.assertEqual(len(server.g_intervals(None, {"since": str(e - 0.01)})["intervals"]), 1)
        self.assertEqual(server.g_intervals(None, {"since": str(e + 5)})["intervals"], [])
        with self.assertRaises(ValueError):
            server.g_intervals(None, {"since": "soon"})

    def test_list_is_trimmed_to_100(self):
        for i in range(250):
            self.b.intervals.append((i, i + 1))
        r = server.g_intervals(None, {})["intervals"]
        self.assertEqual(len(r), 100)
        self.assertEqual(r[-1], [249, 250])

    def test_failed_playback_still_records_interval_and_clears_flag(self):
        class Boom(FakePlayer):
            def play(self, *a, **k):
                raise RuntimeError("device gone")
        self.b.player = Boom()
        self.b.handle({"kind": "say", "message": "hello there friends", "manual": True})
        time.sleep(0.5)
        self.assertEqual(len(self.b.intervals), 1)
        self.assertFalse(json.loads(config.path("speaking.json").read_text())["speaking"])


if __name__ == "__main__":
    unittest.main()
