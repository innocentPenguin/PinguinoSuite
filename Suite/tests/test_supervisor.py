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
