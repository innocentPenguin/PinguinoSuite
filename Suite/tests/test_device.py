"""Run: Suite/.venv/Scripts/python.exe -m unittest discover -s Suite/tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "suite"))
import device as D  # noqa: E402


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def mk(name, priority, clock, known=()):
    d = D.Devices(Path(tempfile.mkdtemp()) / "device.json", clock=clock, name=name)
    d.configure(priority=priority)
    d.me["known"] = list(known)
    return d


def beat(src, dst):
    dst.receive(src.heartbeat())


def settle(c, *devs, secs=31):
    """Advance time in 5 s steps with everybody heartbeating everybody (what the real transport does)."""
    for _ in range(secs // 5 + 1):
        c.t += 5
        for a in devs:
            for b in devs:
                if a is not b:
                    beat(a, b)


class DeviceTests(unittest.TestCase):
    def test_solo_is_master_immediately(self):
        c = Clock()
        d = mk("pc", 100, c)
        self.assertTrue(d.is_master())
        self.assertTrue(d.state()["solo"])

    def test_priority_pc_over_mac_after_stable(self):
        c = Clock()
        pc, mac = mk("pc", 100, c), mk("mac", 50, c)
        beat(mac, pc); beat(pc, mac)
        settle(c, pc, mac)
        self.assertTrue(pc.is_master()); self.assertFalse(mac.is_master())
        self.assertEqual(pc.master_id(), mac.master_id())

    def test_new_device_does_not_steal_before_stable(self):
        c = Clock()
        mac = mk("mac", 50, c)                       # alone, master
        pc = mk("pc", 100, c)
        beat(pc, mac)                                # pc just appeared
        self.assertTrue(mac.is_master())             # not stable yet
        settle(c, pc, mac)
        self.assertFalse(mac.is_master())            # stable now, higher priority wins

    def test_streaming_device_wins_over_priority(self):
        c = Clock()
        pc, mac = mk("pc", 100, c), mk("mac", 50, c)
        beat(mac, pc); beat(pc, mac); settle(c, pc, mac)
        mac.set_streaming(True); beat(mac, pc)
        self.assertEqual(pc.master_id(), mac.me["id"]); self.assertTrue(mac.is_master())

    def test_dead_master_is_replaced(self):
        c = Clock()
        pc, mac = mk("pc", 100, c), mk("mac", 50, c)
        settle(c, pc, mac)
        self.assertFalse(mac.is_master())
        c.t += 25                                    # pc silent > DEAD_AFTER
        self.assertTrue(mac.is_master())

    def test_pin_take_control_and_release(self):
        c = Clock()
        pc, mac = mk("pc", 100, c), mk("mac", 50, c)
        settle(c, pc, mac)
        c.t += 1; mac.take_control(); beat(mac, pc)
        self.assertTrue(mac.is_master()); self.assertFalse(pc.is_master())
        c.t += 1; mac.release_pin(); beat(mac, pc)
        self.assertTrue(pc.is_master()); self.assertFalse(mac.is_master())

    def test_pin_to_dead_device_is_ignored(self):
        c = Clock()
        pc, mac = mk("pc", 100, c), mk("mac", 50, c)
        settle(c, pc, mac)
        c.t += 1; pc.take_control(); beat(pc, mac)
        c.t += 25
        self.assertTrue(mac.is_master())

    def test_warmup_blocks_master_for_known_peers(self):
        c = Clock()
        mac = mk("mac", 50, c, known=["abc"])
        self.assertFalse(mac.is_master())            # waits before assuming nobody else is there
        c.t += 11
        self.assertTrue(mac.is_master())

    def test_persistence_keeps_identity(self):
        c = Clock(); p = Path(tempfile.mkdtemp()) / "device.json"
        a = D.Devices(p, clock=c, name="x"); b = D.Devices(p, clock=c)
        self.assertEqual(a.me["id"], b.me["id"])


if __name__ == "__main__":
    unittest.main()
