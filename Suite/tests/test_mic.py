"""Listen: the mic is saved by name and resolved at every start; a dead or missing mic raises an alert instead of recording nothing."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules", "listen"))
import live  # noqa: E402

DEVS = [
    {"index": 1, "name": "Microphone (Voicemeeter Out B1)", "api": "MME", "rate": 44100},
    {"index": 4, "name": "Microphone (Blue Yeti)", "api": "MME", "rate": 44100},
    {"index": 9, "name": "Microphone (Blue Yeti)", "api": "Windows WASAPI", "rate": 48000},
]


class Resolve(unittest.TestCase):
    def test_name_survives_index_shift(self):
        st = {"device": 2, "device_name": "Microphone (Blue Yeti)", "device_hostapi": "Windows WASAPI"}
        r = live.resolve_device(st, DEVS, 1)
        self.assertEqual((r["index"], r["how"]), (9, "name"))

    def test_case_and_substring(self):
        self.assertEqual(live.resolve_device({"device_name": "microphone (blue yeti)"}, DEVS, 1)["how"], "name_ci")
        r = live.resolve_device({"device_name": "Blue Yeti"}, DEVS, 1)
        self.assertEqual((r["how"], r["index"]), ("name_part", 4))

    def test_legacy_index_only_when_no_name(self):
        self.assertEqual(live.resolve_device({"device": 4}, DEVS, 1)["index"], 4)

    def test_missing_mic_falls_back_to_default_and_says_so(self):
        r = live.resolve_device({"device_name": "Rode NT-USB"}, DEVS, 4)
        self.assertEqual((r["how"], r["index"], r["wanted"]), ("default_fallback", 4, "Rode NT-USB"))

    def test_nothing_chosen_is_the_plain_default(self):
        self.assertEqual(live.resolve_device({}, DEVS, 4)["how"], "default")

    def test_no_input_devices(self):
        self.assertIsNone(live.resolve_device({"device_name": "x"}, [], 0))


class Watchdog(unittest.TestCase):
    def make(self):
        events = []
        m = live.Live(None, events.append)
        m._last_loud = 100.0
        return m, events

    def test_silence_raises_one_alert_then_clears(self):
        m, ev = self.make()
        m._health(110.0, 0.0001)
        self.assertEqual(ev, [])
        m._health(131.0, 0.0001)
        self.assertEqual(m.alert["kind"], "silent")
        self.assertEqual(len(ev), 1)
        m._health(140.0, 0.0001)
        self.assertEqual(len(ev), 1)
        m._health(141.0, 0.05)
        self.assertIsNone(m.alert)
        self.assertEqual(ev[-1], {"type": "mic_alert", "alert": None})

    def test_no_blocks_at_all_counts_as_silence(self):
        m, ev = self.make()
        m._health(135.0, None)
        self.assertEqual(m.alert["kind"], "silent")

    def test_reopen_tried_once(self):
        m, ev = self.make()
        calls = []
        m.resolver = lambda: calls.append(1)
        m._reopen = lambda: calls.append("reopen")
        m._health(131.0, None)
        m.alert = None
        m._last_loud = 0
        m._health(200.0, None)
        self.assertEqual(calls.count("reopen"), 1)


if __name__ == "__main__":
    unittest.main()
