import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "suite"))
import helpdb as H  # noqa: E402

SPECS = {"multi": {"id": "multi", "name": "PinguinoMulti", "desc": "Unified chat",
                   "help": {"twitch": {"title": "Twitch for Multi", "steps": ["Open Connect", "Authorize"], "link": {"label": "Open", "url": "https://innocentpenguin.com/x"}},
                            "_module": {"title": "How Multi works", "steps": ["Chat from all platforms"]}}},
         "host": {"id": "host", "name": "PinguinoHost", "desc": "Bots"}}


class HelpTests(unittest.TestCase):
    def test_clean_help_filters_links_and_size(self):
        h = H.clean_help({"title": "t", "steps": ["a"] * 40, "link": {"label": "x", "url": "javascript:alert(1)"}, "fix": {"label": "go", "route": "integrations", "focus": "K", "url": "file:///etc"}})
        self.assertEqual(len(h["steps"]), H.MAX_STEPS); self.assertNotIn("link", h); self.assertNotIn("url", h["fix"]); self.assertEqual(h["fix"]["focus"], "K")
        self.assertIsNone(H.clean_help({"nothing": 1})); self.assertIsNone(H.clean_help("text"))
        self.assertIn("link", H.clean_help({"title": "t", "link": {"url": "https://x.example/a"}}))
        self.assertNotIn("module_action", H.clean_help({"title": "t", "fix": {"label": "x", "module_action": {"module": "a b", "action": "rm"}}}).get("fix", {}))

    def test_module_help_beats_catalog_and_item_forms(self):
        h, _ = H.resolve("multi:twitch", "multi", "twitch", specs=SPECS)
        self.assertEqual(h["title"], "Twitch for Multi")
        h, _ = H.resolve("module:host", specs=SPECS)
        self.assertEqual(h["title"], "PinguinoHost")   # no manifest help: generic overview for the module
        h, _ = H.resolve("module:multi:running", specs=SPECS)
        self.assertEqual(h["title"], "How Multi works")

    def test_catalog_aliases(self):
        for key, cat in (("core:OBS", "obs"), ("core:streamerbot", "streamerbot"), ("host:up", "module_down"), ("spotify:module", "module_down"), ("key:X", "vault_key"),
                         ("host:keys", "keys"), ("module:host:failed", "module_failed"), ("module:host:starting", "module_starting"), ("link:peer-mac", "tailscale_peer"), ("core:disk", "disk")):
            self.assertIs(H.resolve(key, specs=SPECS)[0], H.CATALOG[cat], key)

    def test_console_matchers_and_unknown(self):
        self.assertIs(H.resolve("", "link", "", "http", "unauthorized POST /api/x (401)")[0], H.CATALOG["vault_key"])
        self.assertIs(H.resolve("", "host", "", "obs", "cannot connect")[0], H.CATALOG["obs"])
        self.assertIsNone(H.resolve("zzz:nothing", specs=SPECS)[0])
        self.assertIsNone(H.resolve("", "x", "", "y", "something odd happened")[0])

    def test_catalog_complete_and_no_secrets(self):
        for k, v in H.CATALOG.items():
            self.assertTrue(v["title"] and v["steps"] or k in ("listen_listening",), k)
            for s in v["steps"]:
                self.assertLess(len(s), 500)
        self.assertGreater(len(H.topics(SPECS)), len(H.CATALOG) - 2)


if __name__ == "__main__":
    unittest.main()
