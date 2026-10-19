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
        self.assertEqual(d["dash"]["cards"], ["activity", "listen", "modules", "prestream"])
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


if __name__ == "__main__":
    unittest.main()
