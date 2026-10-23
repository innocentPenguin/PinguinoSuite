import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "suite"))
import feedback  # noqa: E402

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 20).decode()


class Feedback(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()) / "feedback"

    def test_saves_md_json_and_screenshots(self):
        m = feedback.save(self.d, "Overlay is cut off", "Overlay fit", "overlays", "http://127.0.0.1:8760/", "1.2.3", [{"name": "a.png", "data": "data:image/png;base64," + PNG}], now=1_700_000_000)
        j = json.loads((self.d / (m["id"] + ".json")).read_text("utf8"))
        self.assertEqual((j["note"], j["page"], j["version"]), ("Overlay is cut off", "Overlay fit", "1.2.3"))
        self.assertTrue((self.d / m["id"] / "shot1.png").is_file())
        self.assertIn("Overlay is cut off", (self.d / (m["id"] + ".md")).read_text("utf8"))
        self.assertEqual(feedback.recent(self.d)[0]["id"], m["id"])

    def test_same_second_does_not_overwrite(self):
        a = feedback.save(self.d, "one", route="x", now=1_700_000_000)
        b = feedback.save(self.d, "two", route="x", now=1_700_000_000)
        self.assertNotEqual(a["id"], b["id"])

    def test_secrets_blanked_and_bad_input_refused(self):
        m = feedback.save(self.d, "chat said oauth:abcdefghijklmnop1234 and password: hunter22", route="x")
        self.assertNotIn("abcdefghijklmnop", m["note"])
        self.assertNotIn("hunter22", m["note"])
        with self.assertRaises(ValueError):
            feedback.save(self.d, "   ")
        with self.assertRaises(ValueError):
            feedback.save(self.d, "x", images=[{"data": base64.b64encode(b"MZ not an image").decode()}])
        with self.assertRaises(ValueError):
            feedback.save(self.d, "x" * 9000)
        self.assertEqual(feedback._slug("../../Evil Page!"), "evil-page")


if __name__ == "__main__":
    unittest.main()
