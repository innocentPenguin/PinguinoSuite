"""Move to another PC: an export with secrets carries the key vault (passphrase-encrypted); import restores it."""
import io
import os
import sys
import tempfile
import unittest
import zipfile

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "suite"))
import suite  # noqa: E402
import vault as vaultlib  # noqa: E402


class PlainBackend:  # stands in for DPAPI in tests
    id = 1
    def protect(self, d):
        return d[::-1]

    def unprotect(self, d):
        return d[::-1]


def make_vault():
    return vaultlib.Vault(os.path.join(tempfile.mkdtemp(), "vault.bin"), PlainBackend())


class Transfer(unittest.TestCase):
    def setUp(self):
        self.saved = suite.vault

    def tearDown(self):
        suite.vault = self.saved

    def test_vault_travels_in_the_bundle_and_is_not_plaintext(self):
        a = make_vault()
        a.set("TWITCH_CLIENT_SECRET", "sekret-value-12345")
        suite.vault = a
        base = io.BytesIO()
        with zipfile.ZipFile(base, "w") as z:
            z.writestr("manifest.json", "{}")
        out = suite._add_vault_to_bundle(base.getvalue(), "correct horse battery")
        z = zipfile.ZipFile(io.BytesIO(out))
        blob = z.read("vault.pgb")
        self.assertNotIn(b"sekret-value-12345", blob)
        self.assertNotIn(b"sekret-value-12345", out)
        b = make_vault()
        self.assertEqual(b.restore_backup(blob, "correct horse battery"), 1)
        self.assertEqual(b.peek("TWITCH_CLIENT_SECRET"), "sekret-value-12345")
        with self.assertRaises(vaultlib.VaultError):
            make_vault().restore_backup(blob, "wrong passphrase!!")

    def test_empty_or_missing_vault_leaves_the_bundle_alone(self):
        base = io.BytesIO()
        with zipfile.ZipFile(base, "w") as z:
            z.writestr("manifest.json", "{}")
        suite.vault = None
        self.assertEqual(suite._add_vault_to_bundle(base.getvalue(), "x" * 10), base.getvalue())
        suite.vault = make_vault()
        self.assertEqual(suite._add_vault_to_bundle(base.getvalue(), "x" * 10), base.getvalue())


if __name__ == "__main__":
    unittest.main()
