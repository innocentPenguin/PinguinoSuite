import sys, tempfile, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "suite"))
import templates


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.dir.name) / "templates.json"
        self.t = templates.Templates(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def test_save_list_and_persist(self):
        it = self.t.save("wheel", "Fast spins", {"spinSpeed": 3000, "mode": "random", "autoReopen": True, "maxBet": None})
        self.assertEqual(it["values"]["spinSpeed"], 3000)
        self.assertGreater(it["createdAt"], 0)
        again = templates.Templates(self.path)
        self.assertEqual([x["name"] for x in again.list("wheel")], ["Fast spins"])
        self.assertEqual(again.list("queue"), [])

    def test_name_conflict_needs_overwrite(self):
        self.t.save("wheel", "A", {"x": 1})
        with self.assertRaises(templates.TemplateError) as c:
            self.t.save("wheel", "a", {"x": 2})
        self.assertEqual(c.exception.status, 409)
        it = self.t.save("wheel", "a", {"x": 2}, overwrite=True)
        self.assertEqual(self.t.list("wheel")[0]["values"]["x"], 2)
        self.assertEqual(len(self.t.list("wheel")), 1)
        self.assertEqual(it["name"], "a")

    def test_rename_and_delete(self):
        a = self.t.save("q", "One", {"x": 1})
        b = self.t.save("q", "Two", {"x": 2})
        with self.assertRaises(templates.TemplateError) as c:
            self.t.rename("q", a["id"], "two")
        self.assertEqual(c.exception.status, 409)
        self.t.rename("q", a["id"], "Uno")
        self.assertEqual([x["name"] for x in self.t.list("q")], ["Two", "Uno"])
        self.t.delete("q", b["id"])
        with self.assertRaises(templates.TemplateError) as c:
            self.t.delete("q", b["id"])
        self.assertEqual(c.exception.status, 404)

    def test_limits_and_bad_input(self):
        for i in range(templates.MAX_PER_AREA):
            self.t.save("g", f"t{i}", {"x": i})
        with self.assertRaises(templates.TemplateError) as c:
            self.t.save("g", "one too many", {"x": 1})
        self.assertEqual(c.exception.status, 413)
        bad = [("../x", "n", {"a": 1}), ("g2", "", {"a": 1}), ("g2", "x" * 41, {"a": 1}), ("g2", "<b>", {"a": 1}),
               ("g2", "n", {}), ("g2", "n", {"a": {"nested": 1}}), ("g2", "n", {"a": [1]}), ("g2", "n", {"bad key!": 1}),
               ("g2", "n", {f"k{i}": i for i in range(templates.MAX_KEYS + 1)}), ("g2", "n", "text")]
        for area, name, vals in bad:
            with self.assertRaises(templates.TemplateError, msg=str((area, name))) as c:
                self.t.save(area, name, vals)
            self.assertEqual(c.exception.status, 400)

    def test_corrupt_file_is_ignored(self):
        self.path.write_text("not json", encoding="utf8")
        self.assertEqual(self.t.list("wheel"), [])
        self.t.save("wheel", "ok", {"x": 1})
        self.assertEqual(len(self.t.list("wheel")), 1)


if __name__ == "__main__":
    unittest.main()
