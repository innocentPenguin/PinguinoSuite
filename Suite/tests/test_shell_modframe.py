"""The shell must never swap a loaded module page for a card while the module is only "starting" (missed pings): that remounts the iframe at the module home page."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "App" / "src" / "index.html").read_text("utf8")


class ModuleFrameKept(unittest.TestCase):
    def test_starting_keeps_the_frame_without_a_time_limit(self):
        self.assertIn("mm.state==='starting'||", SRC)
        self.assertIn("modChip(", SRC)
        self.assertNotIn("Date.now()-MODOK<30000", SRC)
        self.assertNotIn("Date.now()-COMMOK<30000", SRC)

    def test_comm_keeps_frames_while_starting(self):
        self.assertRegex(SRC, re.escape("commMod(i)?.state==='starting'))return}}"))

    def test_only_mifreload_and_new_pages_assign_the_module_src(self):
        self.assertEqual(len(re.findall(r"f\.src=f\.dataset\.src", SRC)), 2)   # mifReload + the Sources page


if __name__ == "__main__":
    unittest.main()
