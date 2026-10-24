"""Per-module hold: while an operator replaces a module's files the health loop must not relaunch it."""
import json
import os
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
from test_shutdown import _Base, port_open  # noqa: E402


class Hold(_Base):
    def _kill_outside(self, m):
        """what a taskkill / manual install does: the process dies without the core being told"""
        import subprocess
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(m.proc.pid)], capture_output=True)
        m.proc.wait(10)

    def test_a_held_module_is_not_relaunched_and_a_free_one_is(self):
        self._up()
        (m, port, _), (o, oport, _) = self.mods
        m.hold(10)
        self._kill_outside(m)
        self._kill_outside(o)
        for _ in range(3):
            m.refresh(); o.refresh()
            time.sleep(0.5)
        self.assertGreater(m.held_left(), 0)
        self.assertFalse(port_open(port), "the held module was relaunched")
        self.assertEqual(m.crashes, [])
        self.assertTrue(o.crashes, "the other module should have been noticed as crashed and be on its way back")

    def test_hold_expires_and_the_module_comes_back(self):
        self._up()
        m, port, _ = self.mods[0]
        m.hold(1)
        self._kill_outside(m)
        m.hold_until = time.time() + 0.2
        time.sleep(0.4)
        self.assertEqual(m.held_left(), 0)
        for _ in range(8):
            m.refresh()
            if m.retry_at and time.time() >= m.retry_at:
                m.refresh()
            time.sleep(0.5)
            if port_open(port):
                break
        self.assertTrue(port_open(port), "after the hold ended the module was not relaunched")

    def test_release_and_start_clear_it(self):
        m = self.mods[0][0]
        self.assertEqual(m.hold(), 10)
        self.assertTrue(m.release())
        self.assertEqual(m.held_left(), 0)
        m.hold(5)
        m.start()
        self.assertEqual(m.held_left(), 0)

    def test_limits(self):
        m = self.mods[0][0]
        self.assertEqual(m.hold(500), 30)
        self.assertEqual(m.hold(0), 1)
        self.assertEqual(m.hold(True), 10)
        self.assertEqual(m.hold("abc"), 10)

    def test_visible_in_state_diag_selfcheck_and_holds_file(self):
        m = self.mods[0][0]
        m.hold(3)
        self.assertIn(m.public()["held"], (3,))
        self.assertEqual(m.public()["state"], "stopped")
        self.assertGreater(m.diag()["held_s"], 100)
        sc = suite.selfcheck()
        self.assertTrue(any("held" in p for p in sc["problems"]))
        j = json.loads((Path(suite.DATA_DIR) / "holds.json").read_text("utf8"))
        self.assertIn(m.id, j["holds"])
        m.release()
        self.assertNotIn(m.id, json.loads((Path(suite.DATA_DIR) / "holds.json").read_text("utf8"))["holds"])

    def test_api_needs_token_and_stop_can_hold(self):
        from fastapi.testclient import TestClient
        c = TestClient(suite.app, base_url="http://127.0.0.1:8760")
        m = self.mods[0][0]
        self.assertEqual(c.post(f"/api/modules/{m.id}/hold").status_code, 401)
        h = {"Authorization": "Bearer " + suite.TOKEN}
        r = c.post(f"/api/modules/{m.id}/hold", headers=h, json={"minutes": 4}).json()
        self.assertEqual(r["minutes"], 4)
        self.assertEqual(c.post(f"/api/modules/{m.id}/release", headers=h).json()["was_held"], True)
        self.assertEqual(c.post("/api/modules/nope/hold", headers=h).status_code, 404)
        self.assertEqual(c.post(f"/api/modules/{m.id}/stop", headers=h, json={"hold": True}).json()["ok"], True)
        self.assertGreater(m.held_left(), 500)
        c.post(f"/api/modules/{m.id}/start", headers=h)
        self.assertEqual(m.held_left(), 0)

    def test_control_files_hold_and_release(self):
        m = self.mods[0][0]
        suite.CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        (suite.CONTROL_DIR / f"hold-{m.id}").write_text("7")
        suite.process_control()
        self.assertTrue(6 * 60 < m.held_left() <= 7 * 60)
        (suite.CONTROL_DIR / f"release-{m.id}").write_text("")
        suite.process_control()
        self.assertEqual(m.held_left(), 0)

    def test_reconcile_does_not_start_a_held_singleton(self):
        m = self.mods[0][0]
        m.deferred = True
        m.hold(5)
        self.assertGreater(m.held_left(), 0)   # reconcile_devices guards on held_left(); start() would clear it, so it must not be reached
        self.assertFalse(m.running)


if __name__ == "__main__":
    unittest.main()
