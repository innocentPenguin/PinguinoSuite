import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "suite"))
import portable as P  # noqa: E402


def mk():
    suite, data = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    (suite / "suite_settings.json").write_text(json.dumps({"channel": "chan", "modules": {}}))
    (data / "settings.json").write_text(json.dumps({"DefaultFormat": "3v3", "TrnApiKey": "SECRET-TRN", "nested": {"WebSyncKey": "SECRET-WS"}}))
    (data / "host_secrets.json").write_text(json.dumps({"twitch": "TOKEN123"}))
    (data / "device.json").write_text(json.dumps({"id": "abc"}))
    return {"suite": suite, "data": data}


class PortableTests(unittest.TestCase):
    def test_export_without_secrets_has_none(self):
        r = mk()
        z, man = P.export_bundle(r, [])
        blob = b"".join(zipfile.ZipFile(io.BytesIO(z)).read(n) for n in zipfile.ZipFile(io.BytesIO(z)).namelist())
        for s in (b"SECRET-TRN", b"SECRET-WS", b"TOKEN123"):
            self.assertNotIn(s, blob)
        self.assertNotIn("device.json", " ".join(f["arc"] for f in man["files"]))
        self.assertIn(b"3v3", blob)

    def test_secrets_need_passphrase_and_roundtrip(self):
        r = mk()
        with self.assertRaises(P.ExportError):
            P.export_bundle(r, [], include_secrets=True, passphrase="short")
        z, _ = P.export_bundle(r, [], include_secrets=True, passphrase="correct horse")
        self.assertNotIn(b"TOKEN123", b"".join(zipfile.ZipFile(io.BytesIO(z)).read(n) for n in zipfile.ZipFile(io.BytesIO(z)).namelist()))
        t = mk()
        (t["data"] / "settings.json").unlink(); (t["data"] / "host_secrets.json").unlink()
        self.assertTrue(P.import_bundle(t, [], z)["needs_passphrase"])
        with self.assertRaises(P.ExportError):
            P.import_bundle(t, [], z, passphrase="wrong passphrase", apply=True)
        rep = P.import_bundle(t, [], z, passphrase="correct horse", apply=True)
        self.assertTrue(rep["applied"])
        self.assertEqual(json.loads((t["data"] / "host_secrets.json").read_text())["twitch"], "TOKEN123")
        self.assertEqual(json.loads((t["data"] / "settings.json").read_text())["TrnApiKey"], "SECRET-TRN")

    def test_dry_run_changes_nothing_and_import_keeps_local_secrets(self):
        r = mk()
        z, _ = P.export_bundle(r, [])
        t = mk()
        (t["data"] / "settings.json").write_text(json.dumps({"DefaultFormat": "1v1", "TrnApiKey": "LOCAL-KEY", "nested": {"WebSyncKey": "LOCAL-WS"}}))
        rep = P.import_bundle(t, [], z)
        self.assertFalse(rep["applied"])
        self.assertEqual(json.loads((t["data"] / "settings.json").read_text())["DefaultFormat"], "1v1")
        P.import_bundle(t, [], z, apply=True)
        s = json.loads((t["data"] / "settings.json").read_text())
        self.assertEqual((s["DefaultFormat"], s["TrnApiKey"], s["nested"]["WebSyncKey"]), ("3v3", "LOCAL-KEY", "LOCAL-WS"))
        self.assertTrue(list((t["data"] / "backups").glob("import-*/data/settings.json")))
        self.assertEqual(json.loads((t["data"] / "device.json").read_text())["id"], "abc")

    def test_tampered_and_foreign_paths(self):
        r = mk()
        z, man = P.export_bundle(r, [])
        bad = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(z)) as zi, zipfile.ZipFile(bad, "w") as zo:
            for n in zi.namelist():
                zo.writestr(n, b'{"x": 1}' if n == "suite/suite_settings.json" else zi.read(n))
        with self.assertRaises(P.ExportError):
            P.import_bundle(mk(), [], bad.getvalue())
        evil = io.BytesIO()
        with zipfile.ZipFile(evil, "w") as zo:
            zo.writestr("data/../../evil.json", b"{}")
            zo.writestr("data/device.json", b"{}")
            zo.writestr("manifest.json", json.dumps({"version": 1, "files": [{"arc": "data/../../evil.json", "sha256": __import__("hashlib").sha256(b"{}").hexdigest()},
                                                                              {"arc": "data/device.json", "sha256": __import__("hashlib").sha256(b"{}").hexdigest()}]}))
        rep = P.import_bundle(mk(), [], evil.getvalue(), apply=True)
        self.assertTrue(all(f["status"] == "skipped" for f in rep["files"]))
        with self.assertRaises(P.ExportError):
            P.import_bundle(mk(), [], b"not a zip")


if __name__ == "__main__":
    unittest.main()
