import sys, tempfile, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "suite"))
import prefs


class PrefsTests(unittest.TestCase):
    def test_defaults_complete(self):
        d = prefs.clean({})
        self.assertEqual(d["theme"]["preset"], "penguin")
        self.assertEqual(d["dash"]["cards"], prefs.DASH_ORDER)
        self.assertFalse(d["sound"]["on"])

    def test_hostile_input_is_dropped(self):
        d = prefs.clean({"theme": {"preset": "x", "accent": "red;}body{display:none", "zoom": 9999, "vars": {"--accent": "#ff9900", "--x": "url(http://evil)", "bad name": "#fff", "--y": "}"}},
                         "layout": {"start": "../../etc", "nav_hidden": ["m:multi", "<script>"]}, "sound": {"volume": "loud", "events": {"error": 1, "zzz": True}}})
        self.assertEqual(d["theme"]["preset"], "penguin")
        self.assertEqual(d["theme"]["accent"], "")
        self.assertEqual(d["theme"]["zoom"], 160)
        self.assertEqual(d["theme"]["vars"], {"--accent": "#ff9900"})
        self.assertEqual(d["layout"]["start"], "dashboard")
        self.assertEqual(d["layout"]["nav_hidden"], ["m:multi"])
        self.assertEqual(d["sound"]["volume"], 50)
        self.assertTrue(d["sound"]["events"]["error"])
        self.assertNotIn("zzz", d["sound"]["events"])

    def test_new_cards_are_appended(self):
        d = prefs.clean({"dash": {"cards": ["activity", "listen"], "hidden": ["modules", "nope"]}})
        self.assertEqual(d["dash"]["cards"], ["activity", "listen", "modules", "prestream", "chatrate"])
        self.assertEqual(d["dash"]["hidden"], ["modules"])

    def test_profiles_and_auto(self):
        d = prefs.clean({"profiles": {"Streaming": {"theme": {"preset": "midnight"}, "profiles": {"x": {}}}, "<b>": {}}, "auto": {"live": "Streaming", "idle": "Nope"}})
        self.assertEqual(list(d["profiles"]), ["Streaming"])
        self.assertEqual(d["profiles"]["Streaming"]["theme"]["preset"], "midnight")
        self.assertNotIn("profiles", d["profiles"]["Streaming"])
        self.assertEqual(d["auto"], {"live": "Streaming", "idle": ""})

    def test_roundtrip_backup_and_css(self):
        with tempfile.TemporaryDirectory() as t:
            p = prefs.Prefs(pathlib.Path(t) / "prefs.json")
            p.save({"theme": {"preset": "rose", "vars": {"--accent": "#ff5c8a"}}})
            p.save({"theme": {"preset": "forest"}})
            self.assertEqual(p.load()["theme"]["preset"], "forest")
            (pathlib.Path(t) / "prefs.json").write_text("{broken")
            self.assertEqual(p.load()["theme"]["preset"], "rose")   # corrupt file -> last good backup
            self.assertEqual(p.css(), ":root{--accent:#ff5c8a}")
            self.assertEqual(p.reset()["theme"]["preset"], "penguin")



class SoundPrefTests(unittest.TestCase):
    def test_per_event_choice_and_defaults(self):
        d = prefs.clean({"sound": {"choice": {"golive": "bell", "error": "u:0123456789", "act_raid": "../x", "chat_sent": "nope"}, "vols": {"golive": 30, "error": "x", "act_sub": 999}}})
        s = d["sound"]
        self.assertEqual(s["choice"]["golive"], "bell")
        self.assertEqual(s["choice"]["error"], "u:0123456789")
        self.assertEqual(s["choice"]["act_raid"], prefs.SOUND_DEFAULT["act_raid"])   # hostile id -> default
        self.assertEqual(s["choice"]["chat_sent"], prefs.SOUND_DEFAULT["chat_sent"])
        self.assertEqual((s["vols"]["golive"], s["vols"]["error"], s["vols"]["act_sub"]), (30, 100, 100))
        self.assertFalse(s["events"]["chat_sent"])   # new event is off until chosen
        self.assertEqual(set(s["choice"]), set(prefs.SOUND_EVENTS))

    def test_chat_filter_and_gap(self):
        s = prefs.clean({"sound": {"chat_filter": "bot", "chat_gap": 0}})["sound"]
        self.assertEqual((s["chat_filter"], s["chat_gap"]), ("bot", 1))
        s = prefs.clean({"sound": {"chat_filter": "x", "chat_gap": "z"}})["sound"]
        self.assertEqual((s["chat_filter"], s["chat_gap"]), ("all", 4))

    def test_more_than_double_the_old_four_sounds(self):
        self.assertGreaterEqual(len(prefs.SOUND_IDS), 12)
        self.assertEqual(len(set(prefs.SOUND_IDS)), len(prefs.SOUND_IDS))

if __name__ == "__main__":
    unittest.main()


class CoreParses(unittest.TestCase):
    def test_core_files_compile(self):   # a syntax slip in suite.py once got committed; this catches it without starting the core
        import ast
        for f in ("suite.py", "helpdb.py", "prefs.py", "livedetect.py", "device.py", "vault.py", "portable.py", "integrations.py", "prestream.py"):
            ast.parse((pathlib.Path(__file__).resolve().parents[1] / "suite" / f).read_text("utf8"), f)


class WordingTests(unittest.TestCase):
    def test_text_and_thresholds(self):
        d = prefs.clean({"text": {"app_name": "  My Hub  ", "idle_title": "<b>x</b>", "live_pill": "", "offline_pill": 5}, "thresholds": {"errors_min": 1}})
        self.assertEqual(d["text"]["app_name"], "My Hub")
        self.assertEqual(d["text"]["idle_title"], "Ready when you are")   # angle brackets rejected -> default
        self.assertEqual(d["text"]["live_pill"], "LIVE")
        self.assertEqual(d["thresholds"]["errors_min"], 5)
        self.assertIn("act_raid", d["sound"]["events"])
