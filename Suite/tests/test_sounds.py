import sys, tempfile, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "suite"))
import sounds

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 30
OGG = b"OggS" + b"\x00" * 40
MP3 = b"ID3" + b"\x00" * 40


class SoundsTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.s = sounds.Sounds(pathlib.Path(self.t.name) / "sounds")

    def tearDown(self):
        self.t.cleanup()

    def test_add_list_get_remove_keeps_file(self):
        for n, b in (("ding.wav", WAV), ("x.ogg", OGG), ("y.mp3", MP3)):
            ok, e = self.s.add(n, b)
            self.assertTrue(ok, e)
        self.assertEqual(len(self.s.list()), 3)
        ok, e = self.s.add("ding.wav", WAV)   # same bytes again -> the same entry, not a copy
        self.assertTrue(e.get("duplicate"))
        self.assertEqual(len(self.s.list()), 3)
        sid = [x["id"] for x in self.s.list() if x["kind"] == "wav"][0]
        data, mime = self.s.get(sid)
        self.assertEqual((data, mime), (WAV, "audio/wav"))
        self.assertTrue(self.s.remove(sid))
        self.assertIsNone(self.s.get(sid))
        self.assertEqual(len(self.s.list()), 2)
        self.assertEqual(len(list((pathlib.Path(self.t.name) / "sounds" / "removed").iterdir())), 1)   # moved, not deleted

    def test_rejects_wrong_type_size_and_count(self):
        self.assertFalse(self.s.add("a.mp3", b"MZ\x90\x00 not audio")[0])
        self.assertFalse(self.s.add("a.wav", b"")[0])
        self.assertFalse(self.s.add("big.wav", WAV + b"\x00" * sounds.MAX_BYTES)[0])
        for i in range(sounds.MAX_FILES):
            self.assertTrue(self.s.add(f"s{i}.ogg", OGG + bytes([i]))[0])
        self.assertFalse(self.s.add("extra.ogg", OGG + b"\xff\xff")[0])

    def test_ids_are_confined(self):
        self.assertIsNone(self.s.get("../../vault.bin"))
        self.assertFalse(self.s.remove("u:../../x"))
        ok, e = self.s.add("../../evil<script>.wav", WAV)
        self.assertTrue(ok)
        self.assertNotIn("<", e["name"])
        self.assertNotIn("..", e["name"])


if __name__ == "__main__":
    unittest.main()
