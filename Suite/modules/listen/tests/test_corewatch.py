import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import corewatch  # noqa: E402


class Fake:
    def __init__(self):
        self.t, self.pid, self.alive_set, self.gone = 0.0, 100, {100}, 0

    def watch(self, grace=30):
        return corewatch.CoreWatch(lambda: self.pid, lambda p: p in self.alive_set, lambda: setattr(self, "gone", self.gone + 1), now=lambda: self.t, grace=grace)


class Watch(unittest.TestCase):
    def test_core_dies_for_longer_than_grace_fires_once(self):
        f = Fake(); w = f.watch()
        w.tick()
        f.alive_set.clear()
        for t in (1, 10, 29):
            f.t = t; w.tick()
        self.assertEqual(f.gone, 0)
        f.t = 31; w.tick(); w.tick(); f.t = 99; w.tick()
        self.assertEqual(f.gone, 1)

    def test_restarted_core_with_a_new_pid_is_not_a_death(self):
        f = Fake(); w = f.watch()
        w.tick()
        f.alive_set = set(); f.t = 10; w.tick()          # old core gone for a moment
        f.pid, f.alive_set = 200, {200}; f.t = 20; w.tick()   # new core rewrote the pid file
        f.t = 200; w.tick()
        self.assertEqual(f.gone, 0)
        self.assertIsNone(w.gone_since)

    def test_never_seen_core_means_standalone_and_never_fires(self):
        f = Fake(); f.alive_set = set(); f.pid = None; w = f.watch()
        for t in range(0, 500, 5):
            f.t = t; w.tick()
        self.assertEqual(f.gone, 0)

    def test_missing_pid_file_after_core_was_seen_counts_as_gone(self):
        f = Fake(); w = f.watch()
        w.tick(); f.pid = None; f.t = 1; w.tick(); f.t = 40; w.tick()
        self.assertEqual(f.gone, 1)

    def test_off_by_default_and_real_pid_check(self):
        self.assertFalse(corewatch.enabled({}))
        self.assertIsNone(corewatch.start(lambda: None, {"PINGUINO_DATA_DIR": tempfile.mkdtemp()}))
        self.assertTrue(corewatch.pid_alive(os.getpid()))
        self.assertFalse(corewatch.pid_alive(0))
        self.assertFalse(corewatch.pid_alive(4000000))
        self.assertEqual(corewatch.core_file({"PINGUINO_DATA_DIR": "x"}), Path("x") / "pids" / "core.json")


if __name__ == "__main__":
    unittest.main()
