import sys, unittest, pathlib
from datetime import datetime, timezone
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "suite"))
import prestream


class ScheduleTests(unittest.TestCase):
    def test_clean(self):
        s = prestream.clean_schedule({"slots": ["9:5", "16:30", "25:00", "x", "16:30"], "days": [0, 7, "3", "a"], "tz": "mars"})
        self.assertEqual(s["slots"], ["09:05", "16:30"])
        self.assertEqual(s["days"], [0, 3])
        self.assertEqual(s["tz"], "central")
        self.assertTrue(prestream.clean_schedule({})["enabled"])

    def test_default_slots_fire_once(self):
        # 2026-10-19 is a Monday; CDT (UTC-5) -> 16:31 local = 21:31 UTC
        t = datetime(2026, 10, 19, 21, 31, tzinfo=timezone.utc)
        done = set()
        d = prestream.due_slot(t, done)
        self.assertEqual(d[0], "16:30")
        done.add(d[1])
        self.assertIsNone(prestream.due_slot(t, done))

    def test_custom_slot_days_and_disabled(self):
        t = datetime(2026, 10, 19, 22, 1, tzinfo=timezone.utc)   # Monday 17:01 CDT
        self.assertEqual(prestream.due_slot(t, set(), prestream.clean_schedule({"slots": ["17:00"]}))[0], "17:00")
        self.assertIsNone(prestream.due_slot(t, set(), prestream.clean_schedule({"slots": ["17:00"], "days": [1, 2]})))
        self.assertIsNone(prestream.due_slot(t, set(), prestream.clean_schedule({"slots": ["17:00"], "enabled": False})))


if __name__ == "__main__":
    unittest.main()
