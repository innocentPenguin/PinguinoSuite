import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stamp  # noqa: E402


class Stamp(unittest.TestCase):
    def test_each_line_stamped_once(self):
        buf = io.StringIO()
        s = stamp.StampStream(buf, clock=lambda: 0)
        s.write("a")
        s.write("b\nc\n")
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\d\d:\d\d:\d\d ab$")
        self.assertRegex(lines[1], r"^\d\d:\d\d:\d\d c$")

    def test_empty_and_passthrough(self):
        buf = io.StringIO()
        s = stamp.StampStream(buf)
        self.assertEqual(s.write(""), 0)
        s.flush()


if __name__ == "__main__":
    unittest.main()
