"""A module that answers but is not the core's own child (it recovered after a hung start was skipped, or the core lost track of it)
must still be stopped by a stop request, and the control-file trigger must work for every module id in the manifests."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402
from test_shutdown import SCRIPT, free_port, port_open  # noqa: E402

SUITE = Path(__file__).resolve().parents[1]


def manifest_ids():
    ids = [m["id"] for m in json.loads((SUITE / "modules.json").read_text("utf8"))]
    for f in sorted((SUITE / "modules").glob("*/module.json")):
        ids.append(json.loads(f.read_text("utf8"))["id"])
    return ids


class Orphan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = dict(suite.modules)
        suite.modules.clear()
        self.port = free_port()
        spec = {"id": "orph", "name": "orph", "url": f"http://127.0.0.1:{self.port}", "health": "/health", "cwd": ".", "port": self.port, "cmd": ["{py}", "-c", "pass"]}
        self.m = suite.Module(spec)
        suite.modules["orph"] = self.m
        # started from outside, like a module left over from an earlier core or one that recovered after a skipped start
        self.ext = subprocess.Popen([sys.executable, "-c", SCRIPT, str(self.port), str(self.tmp / "c.pid")], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        end = time.time() + 20
        while time.time() < end and not port_open(self.port):
            time.sleep(0.2)
        self.assertTrue(port_open(self.port), "external fake module did not come up")

    def tearDown(self):
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.ext.pid)], capture_output=True)
        suite.modules.clear()
        suite.modules.update(self.saved)

    def _gone(self):
        end = time.time() + 15
        while time.time() < end and port_open(self.port):
            time.sleep(0.3)
        return not port_open(self.port)

    def test_stop_ends_an_untracked_answering_copy(self):
        self.assertFalse(self.m.running or self.m.adopted)
        self.m.stop()
        self.assertTrue(self._gone(), "stop left the untracked module answering")

    def test_stop_ends_an_adopted_copy_whose_pid_was_lost(self):
        self.m.adopted, self.m.adopt_pid = True, 0
        self.m.stop()
        self.assertTrue(self._gone(), "stop left the adopted module (pid 0) answering")

    def test_refresh_adopts_a_wanted_answering_copy(self):
        self.m.wanted = True
        self.m.refresh()
        self.assertTrue(self.m.adopted)
        self.assertTrue(self.m.adopt_pid)

    def test_a_stopped_module_is_not_re_adopted(self):
        self.m.wanted = False
        self.m.refresh()
        self.assertFalse(self.m.adopted)


class ControlFiles(unittest.TestCase):
    def test_every_manifest_module_gets_every_control_action(self):
        ids = manifest_ids()
        self.assertGreaterEqual(len(ids), 5)
        calls = []
        saved, ctl = dict(suite.modules), suite.CONTROL_DIR
        suite.CONTROL_DIR = Path(tempfile.mkdtemp())
        try:
            suite.modules.clear()
            for mid in ids:
                m = suite.Module({"id": mid, "name": mid, "url": "http://127.0.0.1:1", "cwd": ".", "cmd": ["{py}", "-c", "pass"]})
                m.stop = lambda deferred=False, mid=mid: calls.append((mid, "stop"))
                m.start = lambda mid=mid: calls.append((mid, "start"))
                m.hold = lambda mins=None, mid=mid: calls.append((mid, "hold", str(mins)))
                m.release = lambda mid=mid: calls.append((mid, "release"))
                suite.modules[mid] = m
            for mid in ids:
                for act in ("hold", "stop", "release", "start", "restart"):
                    (suite.CONTROL_DIR / f"{act}-{mid}").write_text("7" if act == "hold" else "", "utf8")
                    suite.process_control()
                    self.assertFalse((suite.CONTROL_DIR / f"{act}-{mid}").exists(), f"{act}-{mid} was not consumed")
            for mid in ids:
                got = [c[1] for c in calls if c[0] == mid]
                self.assertEqual(got, ["hold", "stop", "release", "start", "stop", "start"], mid)
                self.assertIn((mid, "hold", "7"), calls)
        finally:
            suite.modules.clear()
            suite.modules.update(saved)
            suite.CONTROL_DIR = ctl


if __name__ == "__main__":
    unittest.main()
