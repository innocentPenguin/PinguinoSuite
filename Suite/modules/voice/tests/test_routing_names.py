"""Routing check (fake devices, nothing played) and spoken-name cleanup."""
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine
import server
import textproc
from test_voice import mk, wait


def dev(i, name, api="Windows WASAPI"):
    return {"index": i, "name": name, "api": api}


FULL = [dev(1, "CABLE Input (VB-Audio Virtual Cable)"), dev(2, "Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)"), dev(3, "Speakers (Yeti)")]


class Routing(unittest.TestCase):
    def setUp(self):
        self.b, _, _ = mk(master=False)
        server.brain = self.b

    def check(self, raw, device=""):
        self.b.cfg["output"]["device"] = device
        with mock.patch.object(engine, "_raw_outputs", return_value=raw):
            return server.g_routing_check(None, {})

    def test_everything_present(self):
        r = self.check(FULL, "Voicemeeter AUX Input")
        self.assertEqual(r["status"], "pass")
        self.assertEqual([c["id"] for c in r["checks"]], ["voice", "music", "play_on"])
        self.assertIn("resolves to", r["checks"][2]["detail"])

    def test_missing_planned_devices_say_what_to_do(self):
        r = self.check([dev(3, "Speakers (Yeti)")])
        self.assertEqual(r["status"], "warn")
        self.assertIn("CABLE In 16ch", r["checks"][0]["detail"])
        self.assertIn("VB-Cable", r["checks"][1]["detail"])
        self.assertIn("System default", r["checks"][2]["detail"])

    def test_play_on_missing_device_fails_in_words(self):
        r = self.check(FULL, "Voicemeeter VAIO3")
        self.assertEqual(r["status"], "fail")
        self.assertIn("system default", r["checks"][2]["detail"])

    def test_no_devices_at_all(self):
        r = self.check([], "")
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["devices"], [])
        self.assertIn("No audio output device", r["checks"][2]["detail"])

    def test_route_registered(self):
        self.assertIn("/api/routing-check", server.GET)


class Names(unittest.TestCase):
    def test_cleanup(self):
        cases = {"xXDragonSlayerXx": "Dragon Slayer", "cool_guy_1234": "cool guy", "Dragon2": "Dragon", "🔥🔥": "someone",
                 "🔥Fire_Fox🔥": "Fire Fox", "HTTPServerGuy": "HTTP Server Guy", "Ünal_Çelik": "Ünal Çelik", "a.b-c": "a b c",
                 "Xavier": "Xavier", "": "someone", "___": "someone"}
        for raw, want in cases.items():
            self.assertEqual(textproc.clean_name(raw), want, raw)
        self.assertEqual(textproc.clean_name("Dragon_99", False), "Dragon_99")

    def test_nickname_override_wins(self):
        b, sapi, pl = mk()
        b.cfg["nicknames"]["xxdragon99"] = "Big D"
        b.cfg["events"]["follow"]["cooldown_s"] = 0
        b.cfg["personas"][b.cfg["default_persona"]]["templates"]["follow"] = ["{user} followed"]
        b.handle({"kind": "follow", "user": "xxDragon99"})
        wait(pl, 1)
        self.assertTrue(sapi.calls[0][0].startswith("Big D followed"))

    def test_emoji_name_spoken_as_someone(self):
        b, sapi, pl = mk()
        b.cfg["personas"][b.cfg["default_persona"]]["templates"]["follow"] = ["{user} followed"]
        b.handle({"kind": "follow", "user": "🔥🔥🔥"})
        wait(pl, 1)
        self.assertTrue(sapi.calls[0][0].startswith("someone followed"))


if __name__ == "__main__":
    unittest.main()
