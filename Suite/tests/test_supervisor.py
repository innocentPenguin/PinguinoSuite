"""Core supervisor: never spawn a second copy while a hung one holds the module's port."""
import os
import socket
import sys
import tempfile
import unittest

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("PINGUINO_LOG_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402


class PortGuard(unittest.TestCase):
    def test_busy_port_means_no_spawn(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            m = suite.Module({"id": "t", "name": "t", "url": f"http://127.0.0.1:{port}", "cmd": ["{py}", "-c", "raise SystemExit"], "cwd": "."})
            self.assertEqual(m.port(), port)
            m._ping = lambda: False
            m.start()
            self.assertIsNone(m.proc)
            self.assertTrue(m.wanted)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()


class Hysteresis(unittest.TestCase):
    """A busy module missing one health ping must not flip to 'starting' (the shell would swap its page for a card and lose the user's place)."""

    def test_one_or_three_missed_pings_keep_it_running_the_fourth_does_not(self):
        m = suite.Module({"id": "h", "name": "h", "url": "http://127.0.0.1:1", "cmd": ["x"], "cwd": "."})
        m.healthy = True
        m.supervise = lambda: None
        m._ping = lambda: False
        for _ in range(3):
            m.refresh()
            self.assertTrue(m.healthy)
        m.refresh()
        self.assertFalse(m.healthy)

    def test_an_answer_resets_the_count(self):
        m = suite.Module({"id": "h2", "name": "h2", "url": "http://127.0.0.1:1", "cmd": ["x"], "cwd": "."})
        m.healthy = True
        m.supervise = lambda: None
        for ok in (False, False, True, False, False, False):
            m._ping = lambda ok=ok: ok
            m.refresh()
        self.assertTrue(m.healthy)
