"""Audit rounds 2-3 regressions. Temp data dir, fake player and fake sounddevice: nothing is played."""
import io
import os
import sys
import tempfile
import time
import types
import unittest
import wave
from unittest import mock

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

import brain as B
import config
import engine
import server
import textproc
from test_voice import FakePlayer, FakeSapi, mk, wait


class Engine(unittest.TestCase):
    def test_wasapi_play_uses_auto_convert(self):
        calls = {}
        sd = types.SimpleNamespace(
            query_devices=lambda d=None: {"hostapi": 1, "name": "x"},
            query_hostapis=lambda i=None: {"name": "Windows WASAPI"},
            WasapiSettings=lambda **kw: ("wasapi", kw),
            play=lambda a, sr, device=None, extra_settings=None: calls.update(device=device, extra=extra_settings),
            wait=lambda: None, stop=lambda: None)
        p = engine.Player(enabled=True)
        with mock.patch.dict(sys.modules, {"sounddevice": sd}):
            self.assertTrue(p._play_sd(engine.np_to_wav(np.zeros(100, dtype=np.float32)), 0.0, 62))
        self.assertEqual(calls["device"], 62)
        self.assertEqual(calls["extra"], ("wasapi", {"auto_convert": True}))

    def test_non_wasapi_has_no_extra_settings(self):
        calls = {}
        sd = types.SimpleNamespace(
            query_devices=lambda d=None: {"hostapi": 0}, query_hostapis=lambda i=None: {"name": "MME"},
            WasapiSettings=lambda **kw: "w", play=lambda a, sr, device=None, extra_settings=None: calls.update(extra=extra_settings),
            wait=lambda: None, stop=lambda: None)
        with mock.patch.dict(sys.modules, {"sounddevice": sd}):
            engine.Player(enabled=True)._play_sd(engine.np_to_wav(np.zeros(100, dtype=np.float32)), 0.0, 3)
        self.assertIsNone(calls["extra"])

    def test_24_bit_wav_rejected(self):
        bio = io.BytesIO()
        with wave.open(bio, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(3)
            w.setframerate(22050)
            w.writeframes(b"\x00\x01\x02" * 100)
        with self.assertRaises(ValueError):
            engine.wav_to_np(bio.getvalue())


class Pipeline(unittest.TestCase):
    def say(self, b, ev):
        r = b.handle({"kind": "follow", "user": "alice", **ev})
        return r

    def test_spoken_numbers_cannot_carry_text(self):
        b, sapi, pl = mk()
        b.cfg["personas"][b.cfg["default_persona"]]["templates"]["raid"] = ["{user} raids with {viewers} viewers tier {tier}"]
        b.cfg["events"]["raid"]["min_amount"] = 0
        b.handle({"kind": "raid", "user": "alice", "amount": 10, "viewers": "buy my stuff", "tier": "free money"})
        wait(pl, 1)
        said = sapi.calls[0][0]
        self.assertNotIn("buy", said)
        self.assertNotIn("money", said)
        self.assertIn("10 viewers", said)

    def test_priority_is_clamped(self):
        b, sapi, pl = mk()
        pl.delay = 0.3
        b.handle({"kind": "say", "message": "first line here", "manual": True})
        r = b.handle({"kind": "say", "message": "second line here", "manual": True, "priority": 99999})
        self.assertEqual(r["outcome"], "queued")
        self.assertTrue(all(i["priority"] <= 9 for i in b.q))
        r = b.handle({"kind": "say", "message": "third line here", "manual": True, "priority": "high"})
        self.assertEqual(r["outcome"], "queued")

    def test_bad_display_name_is_masked_and_secret_names_dropped(self):
        b, sapi, pl = mk()
        b.cfg["events"]["follow"]["cooldown_s"] = 0
        b.handle({"kind": "follow", "user": "Asshole99"})
        b.handle({"kind": "follow", "user": "oauth:" + "abcdefghijklmnop1234"})
        wait(pl, 2)
        for text, _, _ in sapi.calls:
            self.assertNotIn("asshole", text.lower())
            self.assertNotIn("abcdefghijk", text)

    def test_command_variable_is_scrubbed(self):
        b, sapi, pl = mk()
        b.cfg["events"]["command"]["enabled"] = True
        b.cfg["personas"][b.cfg["default_persona"]]["templates"]["command"] = ["{user} ran {command}"]
        b.cfg["events"]["command"]["only_live"] = False
        b.handle({"kind": "command", "user": "bob", "what": "oauth:" + "abcdefghijklmnop1234", "message": ""})
        wait(pl, 1)
        self.assertNotIn("abcdefghijk", sapi.calls[0][0])

    def test_master_off_speaks_nothing_for_every_entry(self):
        b, sapi, pl = mk(master=False)
        for ev in ({"kind": "say", "message": "hello there", "manual": True}, {"kind": "raid", "user": "a", "amount": 50},
                   {"kind": "timer", "message": "tick tock", "manual": True}):
            self.assertEqual(b.handle(ev)["outcome"], "master_off")
        time.sleep(0.2)
        self.assertEqual((pl.played, sapi.calls), ([], []))

    def test_history_file_rotates(self):
        b, _, _ = mk(master=False)
        hp = config.path("history.jsonl")
        hp.write_bytes(b"x" * 5_000_100)
        b.handle({"kind": "say", "message": "hello there", "manual": True})
        self.assertTrue(config.path("history.1.jsonl").exists())
        self.assertLess(hp.stat().st_size, 5000)


class Server(unittest.TestCase):
    def test_intervals_safe_while_worker_appends(self):
        b, _, _ = mk(master=False)
        server.brain = b
        stop = [False]

        def spam():
            while not stop[0]:
                b.intervals.append((time.time(), time.time() + 1))
        import threading
        t = threading.Thread(target=spam)
        t.start()
        try:
            for _ in range(300):
                server.g_intervals(None, {})
        finally:
            stop[0] = True
            t.join()

    def test_history_n_clamped(self):
        b, _, _ = mk(master=False)
        server.brain = b
        self.assertEqual(server.g_history(None, {"n": "-5"}), {"history": b.tail(1)})
        server.g_history(None, {"n": "99999999"})

    def test_message_cap(self):
        c = config.defaults()
        t, _ = textproc.clean_message("word " * 100000, c)
        self.assertLess(len(t), 2100)


if __name__ == "__main__":
    unittest.main()
