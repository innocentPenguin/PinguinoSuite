import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class Disconnect(unittest.TestCase):
    def _srv(self):
        s = server.Server.__new__(server.Server)
        return s

    def test_reset_is_one_line(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                raise ConnectionResetError(10054, "reset")
            except ConnectionResetError:
                self._srv().handle_error(None, ("127.0.0.1", 1))
        self.assertIn("client dropped", out.getvalue())
        self.assertNotIn("Traceback", err.getvalue() + out.getvalue())

    def test_real_error_still_traced(self):
        err = io.StringIO()
        with redirect_stderr(err):
            try:
                raise ValueError("boom")
            except ValueError:
                self._srv().handle_error(None, ("127.0.0.1", 1))
        self.assertIn("ValueError", err.getvalue())


if __name__ == "__main__":
    unittest.main()
