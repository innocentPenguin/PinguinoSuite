"""Guard: no secret-shaped literals in the Spotify module (code, tests, docs, module.json).

Patterns are assembled from fragments at runtime so this file never matches itself
(and never trips GitHub push protection). Fixtures that need a token-looking value
must build it at runtime too (e.g. "ghp" + "_" + "x" * 36).
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"bin", "__pycache__", ".git", "node_modules"}
EXTS = {".py", ".md", ".json", ".html", ".js", ".css", ".txt", ".cs", ".ps1", ".bat", ".yml", ".yaml", ".toml"}
U = "[A-Za-z0-9_-]"
PATTERNS = {
    "github token": "gh" + "[pousr]" + "_[A-Za-z0-9]{20,}",
    "github pat": "github" + "_pat_" + "[A-Za-z0-9_]{20,}",
    "api key sk-": r"\bsk" + "-" + "[A-Za-z0-9]{20,}",
    "slack token": "xox" + "[bapr]-" + "[A-Za-z0-9-]{10,}",
    "aws key id": "AK" + "IA" + "[0-9A-Z]{16}",
    "google key": "AI" + "za" + "[0-9A-Za-z_-]{30,}",
    "twitch oauth": "oauth" + ":" + "[a-z0-9]{20,}",
    "jwt": U + "{20,}\." + U + "{20,}\." + U + "{20,}",
    "private key": "-----BEGIN " + "[A-Z ]*PRIVATE KEY",
    "long hex": r"\b[0-9a-f]{32,}\b",
}
# obvious documentation placeholders (module.json client id example)
PLACEHOLDER = re.compile(r"^(0123456789abcdef)+[0-9a-f]*$")


def _files():
    for d, dirs, names in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            if os.path.splitext(n)[1].lower() in EXTS:
                yield os.path.join(d, n)


class NoSecretLiteralsTests(unittest.TestCase):
    def test_no_secret_shaped_strings(self):
        compiled = {k: re.compile(v) for k, v in PATTERNS.items()}
        bad = []
        scanned = 0
        for path in _files():
            scanned += 1
            with open(path, encoding="utf-8", errors="replace") as f:
                for no, line in enumerate(f, 1):
                    for kind, rx in compiled.items():
                        for m in rx.finditer(line):
                            if kind == "long hex" and PLACEHOLDER.match(m.group(0)):
                                continue
                            bad.append("%s:%d (%s)" % (os.path.relpath(path, ROOT), no, kind))
        self.assertGreater(scanned, 10, "scanner found too few files")
        self.assertEqual(bad, [], "secret-shaped literal(s): build fixtures at runtime instead")

    def test_scanner_catches_shapes(self):
        samples = {
            "github token": "gh" + "p_" + "a" * 36,
            "long hex": "a1" * 16,
            "jwt": "a" * 22 + "." + "b" * 22 + "." + "c" * 22,
        }
        for kind, s in samples.items():
            self.assertTrue(re.search(PATTERNS[kind], s), kind)


if __name__ == "__main__":
    unittest.main()
