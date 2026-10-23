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

    def host_call(self, **kw):
        body = {"command": "speak", "args": "hello chat", "user": "kara", "redeem": False, **kw}
        return server.p_chat_command(None, body)

    def test_host_numeric_roles(self):
        """The Host sends role as a number string, not a name."""
        self.cfg["tts"]["enabled"] = True
        self.host_call(role="1")
        self.host_call(role="2")
        self.assertEqual(server.brain.got, [])          # viewer, vip: below mod
        self.host_call(role="3", isMod=True)
        self.host_call(role="4", isMod=True, isBroadcaster=True)
        self.assertEqual([e["role"] for e in server.brain.got], ["mod", "broadcaster"])

    def test_redeem_lets_anyone_but_still_needs_the_switch(self):
        self.host_call(role="1", redeem=True)
        self.assertEqual(server.brain.got, [])          # tts.enabled is off
        self.cfg["tts"]["enabled"] = True
        self.host_call(role="1", redeem=True)
        self.host_call(role="1")
        self.assertEqual(len(server.brain.got), 1)
        self.assertEqual(server.brain.got[0]["role"], "viewer")

    def test_role_of_fallbacks(self):
        self.assertEqual(server.role_of({"isMod": True, "user": "ivan", "channel": "ivan"}), "broadcaster")
        self.assertEqual(server.role_of({"isSub": True}), "sub")
        self.assertEqual(server.role_of({"role": "weird"}), "viewer")
        self.assertEqual(server.role_of({"role": None}), "viewer")


if __name__ == "__main__":
    unittest.main()
