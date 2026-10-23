import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine

E = lambda i, n, a: {"index": i, "name": n, "api": a}
ENTRIES = [
    E(0, "CABLE Input (VB-Audio Virtual C", "MME"),
    E(1, "Voicemeeter AUX Input (VB-Audio", "MME"),
    E(5, "CABLE Input (VB-Audio Virtual Cable)", "Windows DirectSound"),
    E(9, "Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)", "Windows DirectSound"),
    E(14, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI"),
    E(15, "Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)", "Windows WASAPI"),
    E(16, "Headphones (High Definition Audio Device)", "Windows WASAPI"),
]


class Devices(unittest.TestCase):
    def test_dedupe_prefers_wasapi_and_is_stable(self):
        a = engine.dedupe_devices(ENTRIES)
        b = engine.dedupe_devices(list(reversed(ENTRIES)))
        self.assertEqual(a, b)
        self.assertEqual([d["index"] for d in a], [14, 16, 15])
        self.assertEqual(len({d["name"] for d in a}), 3)

    def test_pick_case_insensitive_substring_wasapi_first(self):
        self.assertEqual(engine.pick_device("cable input", ENTRIES), 14)
        self.assertEqual(engine.pick_device("VOICEMEETER aux", ENTRIES), 15)
        self.assertEqual(engine.pick_device("  headphones ", ENTRIES), 16)

    def test_pick_missing_or_empty(self):
        self.assertIsNone(engine.pick_device("nothing here", ENTRIES))
        self.assertIsNone(engine.pick_device("", ENTRIES))
        self.assertIsNone(engine.pick_device("cable", []))

    def test_pick_without_wasapi_falls_back_to_directsound_then_mme(self):
        self.assertEqual(engine.pick_device("cable", ENTRIES[:3]), 5)
        self.assertEqual(engine.pick_device("cable", ENTRIES[:1]), 0)

    def test_missing_device_warns_once_and_uses_default(self):
        p = engine.Player(enabled=True)
        p.ws = mock.Mock(SND_FILENAME=1, SND_ASYNC=2, SND_PURGE=4)
        with mock.patch.object(engine, "_raw_outputs", return_value=ENTRIES), \
                mock.patch.object(engine.console_log, "warn") as w:
            self.assertTrue(p.play(b"RIFFxxxx", 0.0, device="no such device"))
            self.assertTrue(p.play(b"RIFFxxxx", 0.0, device="no such device"))
        self.assertTrue(w.called)
        self.assertEqual(w.call_args[1].get("dedupe_s"), 300)
        self.assertIn("not found, using the default", w.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
