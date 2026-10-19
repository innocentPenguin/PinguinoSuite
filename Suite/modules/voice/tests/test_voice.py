"""Pinguino Voice tests: python -m unittest discover -s tests   (run from modules/voice). Uses a fake engine: no audio, no PowerShell."""
import os
import sys
import tempfile
import time
import unittest

os.environ["PINGUINO_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

import brain as B
import config
import engine
import textproc


class FakeSapi:
    def __init__(self):
        self.calls = []

    def voices(self, refresh=False):
        return ["Microsoft David Desktop", "Microsoft Zira Desktop"]

    def speak_to_wav(self, text, voice, rate):
        self.calls.append((text, voice, rate))
        return engine.np_to_wav(np.sin(np.arange(8000) / 10.0).astype(np.float32) * .5, 16000)


class FakePlayer:
    def __init__(self):
        self.played = []
        self.busy = False
        self.stops = 0
        self.delay = 0

    def play(self, wav, secs):
        time.sleep(self.delay)
        self.played.append(secs)
        return True

    def stop(self):
        self.stops += 1


def mk(**over):
    sapi, pl = FakeSapi(), FakePlayer()
    b = B.Brain(player=pl, sapi=sapi)
    c = config.defaults()
    c["master"] = True
    c["queue"]["gap_ms"] = 0
    for k, v in over.items():
        c[k].update(v) if isinstance(v, dict) else c.__setitem__(k, v)
    b.cfg = config.normalize(c)
    return b, sapi, pl


def wait(pl, n, t=5):
    end = time.time() + t
    while len(pl.played) < n and time.time() < end:
        time.sleep(0.02)


class Text(unittest.TestCase):
    def test_secrets(self):
        for s in ["my oauth:abcdefghijklmnop1234", "token abc123", "key sk-ABCDEFGHIJKLMNOP123456", "mail me a@b.com", "ip 192.168.1.5", "password is hunter2",
                  "aGVsbG8gd29ybGQgdGhpcyBpcyBsb25nIGJhc2U2NA=="]:
            out, found = textproc.scrub_secrets(s)
            self.assertTrue(found, s)
            self.assertNotIn("hunter2", out)
            self.assertNotIn("abcdefghijklmnop", out)

    def test_links_emoji_repeat(self):
        c = config.defaults()
        t, _ = textproc.clean_message("visit https://evil.com/x now \U0001F600\U0001F600 aaaaaaaa spam spam spam spam", c)
        self.assertIn("a link", t)
        self.assertNotIn("evil", t)
        self.assertNotIn("\U0001F600", t)
        self.assertNotIn("aaaa", t)

    def test_profanity(self):
        c = config.defaults()
        t, _ = textproc.clean_message("what the fuck", c)
        self.assertIn("beep", t)
        self.assertNotIn("fuck", t)
        c["limits"]["profanity"] = "skip"
        self.assertIsNone(textproc.clean_message("shit", c)[0])

    def test_names(self):
        self.assertEqual(textproc.clean_name("cool_guy_1234"), "cool guy")

    def test_template_min(self):
        r = __import__("random").Random(1)
        self.assertEqual(textproc.pick_template(["a", "min:10|b"], 5, r), "a")
        self.assertEqual(textproc.pick_template(["a", "min:10|b"], 50, r), "b")

    def test_quiet(self):
        c = config.defaults()
        c["quiet"].update(enabled=True, start="23:00", end="07:00")
        mid = time.mktime(time.strptime("2026-10-19 02:00", "%Y-%m-%d %H:%M"))
        self.assertTrue(textproc.in_quiet(c, mid))
        self.assertFalse(textproc.in_quiet(c, mid + 10 * 3600))

    def test_pronounce_and_length(self):
        c = config.defaults()
        c["limits"]["max_chars"] = 20
        t, w = textproc.finish("Hello pinguino and everybody in the whole wide chat", c)
        self.assertLessEqual(len(t), 21)
        self.assertIn("cut", w)
        c["limits"]["too_long"] = "skip"
        self.assertIsNone(textproc.finish("x" * 50 + " y", c)[0])


class Config(unittest.TestCase):
    def test_defaults_safe(self):
        c = config.defaults()
        self.assertFalse(c["master"])
        self.assertEqual(config.normalize(c), config.normalize(config.normalize(c)))

    def test_garbage(self):
        c = config.normalize({"personas": {"x": {"rate": 999, "pitch": "abc", "effects": {"echo": -5}}}, "limits": {"max_chars": "no"}, "events": {"follow": {"persona": "ghost"}}, "master": 1})
        p = c["personas"]["x"]
        self.assertEqual(p["rate"], 10)
        self.assertEqual(p["pitch"], 0)
        self.assertEqual(p["effects"]["echo"], 0)
        self.assertEqual(c["events"]["follow"]["persona"], "default")
        self.assertEqual(c["limits"]["max_chars"], 160)

    def test_save_load_backup_presets(self):
        c = config.defaults()
        c["output"]["volume"] = 33
        config.save(c)
        config.save(c)
        self.assertEqual(config.load()["output"]["volume"], 33)
        self.assertTrue(config.backups())
        n = config.preset_save("my set", dict(c, master=True))
        self.assertFalse(config.preset_get(n)["master"])
        self.assertIn("Cozy night", [p["name"] for p in config.preset_list()])
        self.assertEqual(config.preset_get("Cozy night")["default_persona"], "sleepy")
        config.preset_delete(n)

    def test_every_setting_has_help(self):
        for k in ("master", "engine", "persona.pitch", "event.templates", "limits.profanity", "queue.mode", "quiet.start", "output.volume", "pronounce", "tts.enabled"):
            self.assertIn(k, config.HELP)


class Pipeline(unittest.TestCase):
    def test_master_off_silent(self):
        b, s, pl = mk(master=False)
        self.assertEqual(b.handle({"kind": "follow", "user": "bob"})["outcome"], "master_off")
        time.sleep(0.2)
        self.assertEqual(s.calls, [])
        self.assertEqual(pl.played, [])

    def test_follow_spoken(self):
        b, s, pl = mk()
        self.assertEqual(b.handle({"kind": "follow", "user": "bob"})["outcome"], "queued")
        wait(pl, 1)
        self.assertEqual(len(pl.played), 1)
        self.assertIn("bob", s.calls[0][0].lower())

    def test_secret_never_spoken(self):
        b, s, pl = mk()
        b.handle({"kind": "say", "message": "my password is hunter2 and oauth:abcdefghijklmnop12345", "manual": True})
        wait(pl, 1)
        self.assertTrue(s.calls)
        self.assertNotIn("hunter2", s.calls[0][0])
        self.assertNotIn("abcdefghij", s.calls[0][0])

    def test_min_amount_and_cooldown(self):
        b, s, pl = mk()
        self.assertEqual(b.handle({"kind": "cheer", "user": "a", "amount": 10})["outcome"], "below_min")
        self.assertEqual(b.handle({"kind": "cheer", "user": "a", "amount": 500})["outcome"], "queued")
        self.assertEqual(b.handle({"kind": "cheer", "user": "a", "amount": 500})["outcome"], "cooldown")

    def test_rate_limit(self):
        b, s, pl = mk(limits={"rate_per_min": 2})
        b.cfg["events"]["follow"]["cooldown_s"] = 0
        b.cfg["queue"]["merge_similar"] = False
        for i in range(2):
            b.handle({"kind": "follow", "user": f"u{i}"})
            wait(pl, i + 1)
        time.sleep(0.1)
        self.assertEqual(b.handle({"kind": "follow", "user": "u9"})["outcome"], "rate_limited")

    def test_blocked_and_profanity_skip(self):
        b, s, pl = mk(limits={"blocked_users": ["troll"], "profanity": "skip"})
        self.assertEqual(b.handle({"kind": "say", "message": "hi", "user": "Troll", "manual": True})["outcome"], "blocked_user")
        self.assertEqual(b.handle({"kind": "say", "message": "you shit", "user": "ok", "manual": True})["outcome"], "blocked")

    def test_persona_resolution(self):
        b, s, pl = mk(roles={"mod": "robot"}, users={"vip_dude": "hype"})
        self.assertEqual(b.persona_for({}, "command", "x", "mod", None), "robot")
        self.assertEqual(b.persona_for({}, "command", "VIP_dude", "mod", None), "hype")
        b.cfg["events"]["follow"]["persona"] = "narrator"
        self.assertEqual(b.persona_for({}, "follow", "VIP_dude", "mod", None), "narrator")

    def test_merge_follows(self):
        b, s, pl = mk()
        b.cfg["events"]["follow"]["cooldown_s"] = 0
        pl.delay = 0.5
        b.handle({"kind": "follow", "user": "first"})
        time.sleep(0.2)
        for n in ("a", "b", "c", "d"):
            b.handle({"kind": "follow", "user": n})
        wait(pl, 2, 8)
        self.assertEqual(len(pl.played), 2)
        self.assertTrue(any("more" in c[0] for c in s.calls))

    def test_drop_new(self):
        b, s, pl = mk(queue={"mode": "drop_new"})
        pl.delay = 0.5
        b.handle({"kind": "raid", "user": "a", "amount": 20})
        time.sleep(0.2)
        self.assertEqual(b.handle({"kind": "raid", "user": "b", "amount": 20})["outcome"], "dropped")

    def test_interrupt(self):
        b, s, pl = mk(queue={"mode": "interrupt", "interrupt_min_priority": 8})
        pl.delay = 0.6
        b.handle({"kind": "follow", "user": "a"})
        time.sleep(0.25)
        b.handle({"kind": "raid", "user": "big", "amount": 50})
        time.sleep(0.1)
        self.assertGreaterEqual(pl.stops, 1)

    def test_panic_clears_queue(self):
        b, s, pl = mk()
        pl.delay = 0.4
        b.cfg["events"]["follow"]["cooldown_s"] = 0
        b.cfg["queue"]["merge_similar"] = False
        for i in range(4):
            b.handle({"kind": "follow", "user": f"u{i}"})
        time.sleep(0.1)
        b.panic()
        time.sleep(1.0)
        self.assertLessEqual(len(pl.played), 1)

    def test_quiet_mute_and_whisper(self):
        b, s, pl = mk(quiet={"enabled": True, "start": "00:00", "end": "23:59", "mode": "mute"})
        self.assertEqual(b.handle({"kind": "follow", "user": "a"})["outcome"], "quiet_hours")
        b.cfg["quiet"]["mode"] = "whisper"
        self.assertEqual(b.handle({"kind": "follow", "user": "a"})["outcome"], "queued")

    def test_mute(self):
        b, s, pl = mk()
        b.mute(5)
        self.assertEqual(b.handle({"kind": "follow", "user": "a"})["outcome"], "muted")
        b.mute(0)
        self.assertEqual(b.handle({"kind": "follow", "user": "a"})["outcome"], "queued")

    def test_disabled_event(self):
        b, s, pl = mk()
        self.assertEqual(b.handle({"kind": "chat", "user": "a", "message": "hi"})["outcome"], "disabled")

    def test_preview_works_when_off(self):
        b, s, pl = mk(master=False)
        wav, said = b.preview("hype", "hello there")
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertEqual(pl.played, [])

    def test_replay(self):
        b, s, pl = mk()
        b.handle({"kind": "follow", "user": "a"})
        wait(pl, 1)
        time.sleep(0.1)
        self.assertEqual(b.replay()["outcome"], "queued")


class Audio(unittest.TestCase):
    def test_effects_pitch_stingers(self):
        a = np.sin(np.arange(22050) / 7.0).astype(np.float32) * .5
        for k, f in engine.FX.items():
            self.assertTrue(np.all(np.isfinite(f(a, 22050, .7))), k)
        self.assertAlmostEqual(len(engine.pitch_shift(a, 5)) / len(a), 1, delta=0.15)
        for s in config.STINGERS:
            self.assertTrue(np.all(np.isfinite(engine.stinger(s))))

    def test_render(self):
        wav, secs = engine.render("hi", config.defaults()["personas"]["robot"], sting="ding", sapi_obj=FakeSapi())
        self.assertGreater(secs, 0.3)
        self.assertTrue(wav.startswith(b"RIFF"))


if __name__ == "__main__":
    unittest.main()
