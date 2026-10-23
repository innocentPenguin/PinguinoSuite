"""Speech backends per OS and the no-voice / no-device messages. Fake runner and fake devices: no synthesiser, no audio."""
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

import engine
import server
from test_voice import mk

SAY_VOICES = "Alex                en_US    # Most people recognize me by my voice.\nSamantha            en_US    # Hello, my name is Samantha.\nAmélie              fr_CA    # Bonjour, je m'appelle Amélie.\nGood News           en_US    # Congratulations\n"
ESPEAK = "Pty Language Age/Gen VoiceName File Other\n 5  en-us  --/M  English_(America) en-us\n 5  de  --/M  German de\n"


class Runner:
    def __init__(self, rc=0, voices=SAY_VOICES):
        self.calls, self.rc, self.voices = [], rc, voices

    def __call__(self, args, input=None, timeout=40):
        self.calls.append((list(args), input))
        if "?" in args or "--voices" in args:
            return self.rc, self.voices
        out = args[args.index("-o") + 1] if "-o" in args else args[args.index("-w") + 1]
        if self.rc == 0:
            with open(out, "wb") as f:
                f.write(engine.np_to_wav(np.zeros(2205, dtype=np.float32)))
        return self.rc, ""


class Backends(unittest.TestCase):
    def test_choice_by_platform(self):
        self.assertIsInstance(engine.make_backend("win32"), engine.Sapi)
        self.assertIsInstance(engine.make_backend("darwin"), engine.MacSay)
        self.assertIsInstance(engine.make_backend("linux"), engine.Espeak)
        self.assertEqual(engine.make_backend("win32").name, "Windows SAPI")

    def test_mac_voices_and_speak(self):
        r = Runner()
        m = engine.make_backend("darwin", r)
        self.assertEqual(m.voices(), ["Alex", "Samantha", "Amélie", "Good News"])
        wav = m.speak_to_wav("-v evil; rm -rf", "Samantha", 2)
        engine.wav_to_np(wav)
        args, text = r.calls[-1]
        self.assertEqual(args[0], "say")
        self.assertIn("Samantha", args)
        self.assertEqual(args[args.index("-r") + 1], "205")
        self.assertEqual(text, "-v evil; rm -rf")       # text only ever travels on stdin
        self.assertNotIn(text, args)

    def test_unknown_voice_falls_back_to_system_default(self):
        r = Runner()
        engine.make_backend("darwin", r).speak_to_wav("hi", "Microsoft David Desktop", 0)
        self.assertNotIn("-v", r.calls[-1][0])

    def test_failure_is_a_plain_error(self):
        m = engine.make_backend("darwin", Runner(rc=1, voices=""))
        self.assertEqual(m.voices(), [])
        with self.assertRaises(RuntimeError) as cm:
            m.speak_to_wav("hi", "", 0)
        self.assertIn("could not speak", str(cm.exception))

    def test_espeak(self):
        r = Runner(voices=ESPEAK)
        e = engine.Espeak(r, binary="espeak-ng")
        self.assertEqual(e.voices(), ["English_(America)", "German"])
        e.speak_to_wav("hello", "German", -3)
        args, text = r.calls[-1]
        self.assertEqual((args[0], text, args[-1]), ("espeak-ng", "hello", "--stdin"))
        self.assertEqual(args[args.index("-s") + 1], "130")

    def test_missing_binary_means_no_voices(self):
        self.assertEqual(engine.make_backend("linux", lambda a, input=None, timeout=40: (127, "")).voices(), [])

    def test_player_without_winsound_plays_through_sounddevice(self):
        p = engine.Player(enabled=True)
        p.ws, p.native = None, True
        with mock.patch.object(engine.Player, "_play_sd", return_value=True) as sd:
            self.assertTrue(p.play(b"x", 0.1, ""))
        sd.assert_called_once()
        self.assertIsNone(sd.call_args[0][2])
        with mock.patch.object(engine.Player, "_play_sd", side_effect=RuntimeError("no device")), mock.patch.object(engine.console_log, "warn"):
            self.assertFalse(p.play(b"x", 0.1, ""))

    def test_disabled_player_plays_nothing(self):
        p = engine.Player(enabled=False)
        p.native = True
        with mock.patch.object(engine.Player, "_play_sd") as sd:
            self.assertTrue(p.play(b"x", 0.1, ""))
        sd.assert_not_called()


class NoVoiceNoDevice(unittest.TestCase):
    def setUp(self):
        self.b, self.s, _ = mk(master=False)
        server.brain = self.b

    def test_voices_and_devices_hints(self):
        self.b.sapi.voices = lambda refresh=False: []
        with mock.patch.object(engine, "sapi", self.b.sapi):
            v = server.g_voices(None, {})
        self.assertFalse(v["ok"])
        self.assertIn("voice", v["hint"].lower())
        with mock.patch.object(engine, "devices", return_value=[]):
            d = server.g_devices(None, {})
        self.assertEqual(d["devices"], [])
        self.assertIn("No audio output device", d["hint"])

    def test_preview_without_voice_is_a_plain_message(self):
        def boom(*a, **k):
            raise RuntimeError("speech worker did not answer")
        self.b.sapi.speak_to_wav = boom
        self.b.sapi.voices = lambda refresh=False: []
        with self.assertRaises(ValueError) as cm:
            server.p_preview(None, {"text": "hello there"})
        self.assertIn("No voice is available", str(cm.exception))

    def test_soundcheck_without_device_off_windows(self):
        h = type("H", (), {"headers": {"origin": "http://x", "host": "x"}})()
        with mock.patch.object(engine, "devices", return_value=[]), mock.patch.object(server.sys, "platform", "darwin"):
            with self.assertRaises(ValueError) as cm:
                server.p_soundcheck(h, {})
        self.assertIn("No audio output device", str(cm.exception))

    def test_selftest_message(self):
        self.b.sapi.voices = lambda refresh=False: []
        self.b.preview = mock.Mock(side_effect=RuntimeError("x"))
        r = server.g_selftest(None, {})
        self.assertFalse(r["ok"])
        self.assertIn("No voice is available", r["error"])


if __name__ == "__main__":
    unittest.main()
