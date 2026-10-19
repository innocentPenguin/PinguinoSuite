import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "suite"))
import vault as V  # noqa: E402


class XorBackend:  # test double: obviously not secure, lets the tests run on any OS
    id = 9

    def protect(self, d):
        return bytes(b ^ 0x5A for b in d)

    unprotect = protect


def mk(backend=None):
    return V.Vault(Path(tempfile.mkdtemp()) / "vault.bin", backend or XorBackend())


class VaultTests(unittest.TestCase):
    def test_roundtrip_and_never_plaintext_on_disk(self):
        v = mk(); v.set("SPOTIFY_API_KEY", "sk-very-secret-123456")
        self.assertNotIn(b"sk-very-secret", v.path.read_bytes())
        v2 = V.Vault(v.path, XorBackend())
        self.assertEqual(v2.get("SPOTIFY_API_KEY", by="spotify"), "sk-very-secret-123456")
        self.assertEqual(v2.info("SPOTIFY_API_KEY")["used_by"], "spotify")
        self.assertEqual(v2.names(), ["SPOTIFY_API_KEY"])

    def test_rotate_delete_and_validation(self):
        v = mk(); v.set("A_KEY", "one-value-1"); v.set("A_KEY", "two-value-2")
        self.assertEqual(v.peek("A_KEY"), "two-value-2"); self.assertEqual(v.info("A_KEY")["rotations"], 1)
        for bad in ("", "has space", "x" * 100):
            with self.assertRaises(V.VaultError):
                v.set(bad, "value-1234")
        with self.assertRaises(V.VaultError):
            v.set("OK", "   ")
        self.assertTrue(v.delete("A_KEY")); self.assertFalse(v.delete("A_KEY")); self.assertIsNone(v.get("A_KEY"))

    def test_redact_hides_stored_values(self):
        v = mk(); v.set("T", "supersecrettoken99")
        self.assertEqual(v.redact("auth failed with supersecrettoken99 today"), "auth failed with •••• today")
        self.assertEqual(v.redact("short"), "short")

    def test_backup_restore_needs_passphrase(self):
        v = mk(); v.set("K1", "value-one-111"); v.set("K2", "value-two-222")
        blob = v.export_backup("correct horse battery")
        self.assertNotIn(b"value-one", blob)
        w = mk()
        with self.assertRaises(V.VaultError):
            w.restore_backup(blob, "wrong passphrase!!")
        self.assertEqual(w.restore_backup(blob, "correct horse battery"), 2)
        self.assertEqual(w.peek("K2"), "value-two-222")
        with self.assertRaises(V.VaultError):
            v.export_backup("short")

    def test_migration_import_then_scrub_only_matching(self):
        d = Path(tempfile.mkdtemp())
        (d / "settings.json").write_text(json.dumps({"DefaultFormat": "3v3", "TrnApiKey": "trn-key-123456", "nested": {"WebSyncKey": "ws-key-abcdef"}}))
        (d / "host_secrets.json").write_text(json.dumps({"twitch": "tw-token-1", "bot_token": "bot-token-7890"}))
        v = mk()
        found = V.scan_plaintext([d / "settings.json", d / "host_secrets.json"])
        self.assertIn("TRN_API_KEY", [f["name"] for f in found]); self.assertNotIn("trn-key", json.dumps(found))
        self.assertEqual(V.import_plaintext(v, [d / "settings.json", d / "host_secrets.json"]), 3)  # 'twitch' is not secret-looking
        self.assertEqual(v.peek("TRN_API_KEY"), "trn-key-123456")
        v.set("TRN_API_KEY", "changed-after-import")        # vault now differs from the file -> must NOT be scrubbed
        n = V.scrub_plaintext(v, d / "settings.json")
        s = json.loads((d / "settings.json").read_text())
        self.assertEqual(s["TrnApiKey"], "trn-key-123456"); self.assertEqual(s["nested"]["WebSyncKey"], "")
        self.assertEqual(n, 1); self.assertEqual(s["DefaultFormat"], "3v3")

    @unittest.skipUnless(sys.platform == "win32", "DPAPI is Windows only")
    def test_real_dpapi_roundtrip(self):
        b = V.DpapiBackend()
        blob = b.protect(b"hello secret")
        self.assertNotIn(b"hello secret", blob); self.assertEqual(b.unprotect(blob), b"hello secret")
        v = V.Vault(Path(tempfile.mkdtemp()) / "vault.bin", b); v.set("X_KEY", "real-dpapi-value")
        self.assertNotIn(b"real-dpapi-value", v.path.read_bytes())
        self.assertEqual(V.Vault(v.path, V.DpapiBackend()).peek("X_KEY"), "real-dpapi-value")


if __name__ == "__main__":
    unittest.main()
