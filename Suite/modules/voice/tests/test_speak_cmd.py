import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import server


class FakeBrain:
    def __init__(self, cfg):
        self.cfg, self.got = cfg, []

    def handle(self, ev):
        self.got.append(ev)
        return {"outcome": "queued"}


class SpeakCommand(unittest.TestCase):
    def setUp(self):
        self.old = server.brain
        self.cfg = config.defaults()
        server.brain = FakeBrain(self.cfg)

    def tearDown(self):
        server.brain = self.old

    def call(self, cmd, role="mod"):
        return server.p_chat_command(None, {"command": cmd, "args": "hello chat", "user": "kara", "role": role})

    def test_off_by_default_for_both_names(self):
        self.assertFalse(self.cfg["tts"]["enabled"])
        self.call("!speak")
        self.call("!tts")
        self.assertEqual(server.brain.got, [])

    def test_speak_is_an_alias_when_enabled(self):
        self.cfg["tts"]["enabled"] = True
        self.call("!speak")
        self.call("!tts")
        self.assertEqual([e["message"] for e in server.brain.got], ["hello chat"] * 2)

    def test_role_check_and_silent_reply(self):
        self.cfg["tts"]["enabled"] = True
        r = self.call("!speak", role="viewer")
        self.assertEqual(server.brain.got, [])
        self.assertEqual(r["say"], "")
        self.assertEqual(self.call("!speak")["say"], "")   # never posts to chat itself


if __name__ == "__main__":
    unittest.main()
