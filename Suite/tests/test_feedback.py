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


    def test_handled_flag(self):
        m = feedback.save(self.d, "something odd", "Timers", "timers", now=1_700_000_000)
        self.assertFalse(feedback.recent(self.d)[0]["handled"])
        r = feedback.set_handled(self.d, m["id"])
        self.assertTrue(r["handled"])
        self.assertTrue(json.loads((self.d / (m["id"] + ".json")).read_text("utf8"))["handled"])
        self.assertTrue(feedback.recent(self.d)[0]["handled"])
        self.assertFalse(feedback.set_handled(self.d, m["id"], False)["handled"])
        self.assertEqual(feedback.recent(self.d)[0]["note"], "something odd")

    def test_handled_rejects_bad_ids(self):
        for bad in ("../x", "", "20231114-221320-../../a", "nope"):
            with self.assertRaises(ValueError):
                feedback.set_handled(self.d, bad)
        with self.assertRaises(KeyError):
            feedback.set_handled(self.d, "20231114-221320-missing")


if __name__ == "__main__":
    unittest.main()


class Robust(unittest.TestCase):
    def test_handled_on_hand_edited_files(self):
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        (root / "20260101-000000-a.json").write_text(json.dumps({"note": "no id key"}), "utf8")
        (root / "20260101-000001-b.json").write_text("[1, 2]", "utf8")
        m = feedback.set_handled(root, "20260101-000000-a")
        self.assertEqual(m["id"], "20260101-000000-a")
        self.assertTrue(feedback.recent(root)[0]["handled"])
        with self.assertRaises(ValueError):
            feedback.set_handled(root, "20260101-000001-b")
        self.assertEqual(len(feedback.recent(root)), 1)   # the list file is skipped, not a crash

    def test_counts_cover_more_than_one_page(self):
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        ids = [feedback.save(root, f"n{i}", "p", "r", now=1_700_000_000 + i)["id"] for i in range(40)]
        feedback.set_handled(root, ids[0])
        self.assertEqual(feedback.counts(root), {"total": 40, "open": 39})
        self.assertEqual(len(feedback.recent(root, 30)), 30)
        self.assertEqual(len(feedback.recent(root, 60)), 40)

    def test_page_and_route_are_scrubbed(self):
        import tempfile
        from pathlib import Path
        m = feedback.save(Path(tempfile.mkdtemp()), "x", "token=abcdef123456", "password: hunter2222")
        self.assertNotIn("abcdef123456", m["page"])
        self.assertNotIn("hunter2222", m["route"])
