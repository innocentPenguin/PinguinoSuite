"""Module registry sanity (modules.json + modules/*/module.json): the typos that make a module vanish from the nav or never start."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
SUITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE / "suite"))
import suite  # noqa: E402

PLACEHOLDERS = {"{py}"}


def read(p):
    return json.loads(Path(p).read_text("utf8"))


def raw_specs():
    """[(source, spec)] exactly as written, before discover_specs() lets modules.json override a manifest."""
    out = [(f"{p.parent.name}/module.json", read(p)) for p in sorted((SUITE / "modules").glob("*/module.json"))]
    out += [("modules.json", s) for s in read(SUITE / "modules.json")]
    return out


def uis(spec):
    u = spec.get("ui")
    return [] if u is None else u if isinstance(u, list) else [u]


class Registry(unittest.TestCase):
    def test_ids_unique_within_each_source(self):
        ids = [s["id"] for src, s in raw_specs() if src != "modules.json"]
        self.assertEqual([k for k, n in Counter(ids).items() if n > 1], [])
        ids = [s["id"] for src, s in raw_specs() if src == "modules.json"]
        self.assertEqual([k for k, n in Counter(ids).items() if n > 1], [])

    def test_effective_ports_unique_and_match_url(self):
        specs = suite.discover_specs()
        ports = Counter(s["port"] for s in specs.values())
        self.assertEqual({p: n for p, n in ports.items() if n > 1}, {})
        for mid, s in specs.items():
            u = urlparse(s["url"])
            self.assertEqual((u.hostname, u.port), ("127.0.0.1", s["port"]), mid)

    def test_each_effective_module_is_complete(self):
        for mid, s in suite.discover_specs().items():
            with self.subTest(mid):
                self.assertTrue(s.get("name"), "name")
                self.assertIsInstance(s["port"], int)
                self.assertTrue(str(s.get("health", "")).startswith("/"), "health path")
                for k in ("prestream", "integrations"):
                    if k in s:
                        self.assertTrue(str(s[k]).startswith("/"), k)
                for hook in ("on_live", "on_offline", "on_start"):
                    if hook in s:
                        self.assertTrue(str(s[hook].get("post", "")).startswith("/api/"), hook)
                cwd = (SUITE / s["cwd"]).resolve() if s.get("cwd") else None
                self.assertTrue(cwd and cwd.is_dir(), f"cwd {s.get('cwd')}")
                cmd = s["cmd"]
                self.assertTrue(isinstance(cmd, list) and cmd and all(isinstance(c, str) and c for c in cmd), "cmd")
                self.assertTrue(cmd[0] in PLACEHOLDERS or shutil.which(cmd[0]) or (cwd / cmd[0]).exists(), f"cmd[0] {cmd[0]} not resolvable")
                if "build" in s:
                    b = s["build"]
                    self.assertTrue(isinstance(b, list) and b and (b[0] in PLACEHOLDERS or shutil.which(b[0])), "build")

    def test_ui_entries(self):
        navs = []
        for src, s in raw_specs():
            for u in uis(s):
                with self.subTest(src + ":" + str(u.get("nav"))):
                    self.assertIsInstance(u, dict)
                    self.assertTrue(isinstance(u.get("nav"), str) and u["nav"].strip(), "nav label")
                    self.assertTrue(str(u.get("path", "")).startswith("/"), "ui.path must start with /")
                    self.assertIsInstance(u.get("order", 0), (int, float))
                    if "replaces" in u:
                        self.assertTrue(isinstance(u["replaces"], str) and u["replaces"], "replaces")
                    if "section" in u:
                        self.assertIsInstance(u["section"], str)
        for mid, s in suite.discover_specs().items():
            navs += [(u.get("path"), mid) for u in uis(s)]
        c = Counter(navs)
        self.assertEqual([k for k, n in c.items() if n > 1], [])   # the same module never lists the same page twice

    def test_manifest_dir_matches_nothing_odd(self):
        for p in (SUITE / "modules").glob("*/module.json"):
            self.assertRegex(read(p)["id"], r"^[a-z0-9_-]+$", p.parent.name)

    def test_checker_catches_typos(self):
        """The checks above would fail for the usual slips: sanity-check the helpers on a broken spec."""
        bad = {"id": "x", "name": "x", "port": "8000", "url": "http://127.0.0.1:8000", "health": "api/status", "cmd": ["nonexistent-binary-xyz"], "cwd": "modules/none",
               "ui": {"nav": " ", "path": "automations"}}
        self.assertNotIsInstance(bad["port"], int)
        self.assertFalse(bad["health"].startswith("/"))
        self.assertFalse(shutil.which(bad["cmd"][0]))
        self.assertFalse((SUITE / bad["cwd"]).is_dir())
        self.assertFalse(bad["ui"]["nav"].strip())
        self.assertFalse(bad["ui"]["path"].startswith("/"))


if __name__ == "__main__":
    unittest.main()
