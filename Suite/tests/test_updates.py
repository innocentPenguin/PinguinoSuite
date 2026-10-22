import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "suite"))
import updates  # noqa: E402


class FakeModule:
    def __init__(self, wanted=True):
        self.wanted, self.healthy, self.calls = wanted, wanted, []

    def stop(self):
        self.calls.append("stop")
        self.wanted = False

    def start(self):
        self.calls.append("start")
        self.wanted = True


class FakeUpdates(updates.Updates):
    def __init__(self, install, mods, live=False, answers=None):
        super().__init__(install, Path(install) / "updater.mjs", 8760, mods, lambda: live)
        self.answers, self.ran = answers or {}, []

    def run(self, *args, timeout=900):
        self.ran.append(args)
        return self.answers.get(args[0], {"ok": True, "message": "ok"})


def make(live=False, answers=None, mods=None):
    d = Path(tempfile.mkdtemp())
    (d / "install.json").write_text("{}")
    (d / "updater.mjs").write_text("")
    return FakeUpdates(d, mods if mods is not None else {"listen": FakeModule(), "multi": FakeModule(False)}, live, answers)


def wait(u):
    for _ in range(100):
        if u.job.get("state") != "running":
            return u.job
        time.sleep(0.05)
    raise AssertionError("job never finished")


class UpdatesTests(unittest.TestCase):
    def test_not_supported_without_install_json(self):
        u = make()
        (u.install / "install.json").unlink()
        self.assertFalse(u.check()["supported"])
        self.assertEqual(u.apply(["listen"])["status"], 400)

    def test_refused_while_live(self):
        u = make(live=True)
        self.assertEqual(u.apply(["listen"])["status"], 409)
        self.assertEqual(u.rollback()["status"], 409)
        self.assertEqual(u.ran, [])

    def test_module_part_is_stopped_swapped_and_started_again(self):
        u = make()
        self.assertTrue(u.apply(["listen"])["ok"])
        job = wait(u)
        self.assertTrue(job["ok"], job)
        self.assertEqual(u.modules["listen"].calls, ["stop", "start"])
        self.assertEqual(u.ran[0][:3], ("apply", "--only", "listen"))

    def test_module_that_was_off_stays_off(self):
        u = make()
        u.apply(["multi"])
        wait(u)
        self.assertEqual(u.modules["multi"].calls, [])

    def test_app_parts_are_only_staged_and_say_restart(self):
        u = make()
        u.apply(["core", "shell"])
        job = wait(u)
        self.assertTrue(job["ok"] and job["restart_needed"], job)
        self.assertIn("--stage", u.ran[0])
        self.assertEqual(u.modules["listen"].calls, [])

    def test_failed_swap_still_restarts_the_module(self):
        u = make(answers={"apply": {"ok": False, "message": "sha256 mismatch"}})
        u.apply(["listen"])
        job = wait(u)
        self.assertFalse(job["ok"])
        self.assertEqual(u.modules["listen"].calls, ["stop", "start"])

    def test_deferred_by_the_host_is_blocked_not_done(self):
        u = make(answers={"apply": {"ok": True, "deferred": True, "message": "waiting until you are off stream"}})
        u.apply(["listen"])
        self.assertEqual(wait(u)["state"], "blocked")

    def test_one_job_at_a_time_and_unknown_parts_ignored(self):
        gate = threading.Event()
        u = make()
        orig = u.run
        u.run = lambda *a, **k: (gate.wait(2), orig(*a, **k))[1]
        self.assertTrue(u.apply(["listen", "bogus"])["ok"])
        self.assertEqual(u.apply(["multi"])["status"], 409)
        gate.set()
        wait(u)
        self.assertEqual(u.apply(["bogus"])["status"], 400)

    def test_rollback_stops_only_the_modules_it_touches(self):
        u = make(answers={"rollback": {"ok": True, "message": "rolled back to 1.0.1", "components": ["listen"], "to": "1.0.1"}})
        r = u.rollback()
        self.assertTrue(r["ok"], r)
        wait(u)
        self.assertEqual(u.modules["listen"].calls, ["stop", "start"])
        self.assertEqual(u.modules["multi"].calls, [])


if __name__ == "__main__":
    unittest.main()
