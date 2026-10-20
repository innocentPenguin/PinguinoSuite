"""Listen: the status poll must not hang behind a long database job."""
import os
import sys
import tempfile
import threading
import unittest

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules", "listen"))
import db  # noqa: E402


class NoWait(unittest.TestCase):
    def test_returns_rows_when_free(self):
        self.assertEqual(db.rows_nowait("SELECT COUNT(*) n FROM segments")[0]["n"], db.one("SELECT COUNT(*) n FROM segments")["n"])

    def test_raises_busy_instead_of_hanging(self):
        held, release = threading.Event(), threading.Event()

        def hog():
            with db._lock:
                held.set()
                release.wait(5)
        t = threading.Thread(target=hog)
        t.start()
        held.wait(2)
        try:
            with self.assertRaises(db.Busy):
                db.rows_nowait("SELECT 1", wait=0.2)
        finally:
            release.set()
            t.join()


if __name__ == "__main__":
    unittest.main()
