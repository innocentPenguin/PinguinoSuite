"""No secret-shaped literal in any tracked or untracked text file (tests, fixtures, docs, scripts): GitHub push protection blocks a whole push on one.
Build such values at runtime instead (e.g. "sk" + "_live_" + "x" * 24). The shapes below are assembled from pieces so this file holds no such literal itself.
A line can opt out with `secret-shape-ok` (only for a value that is provably fake AND not matched by push protection; prefer concatenation)."""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".webm", ".mp4", ".mp3", ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".otf", ".zip", ".exe", ".dll", ".rgba", ".pdf", ".db", ".sqlite", ".gz", ".7z", ".bin", ".wasm", ".node", ".pyc", ".pdb", ".lock"}
ALNUM = "[A-Za-z0-9]"
SHAPES = {
    "stripe key": "s" + "k_(?:live|test)_" + ALNUM + "{10,}",
    "stripe restricted key": "r" + "k_(?:live|test)_" + ALNUM + "{10,}",
    "bearer token": "Bear" + "er\s+[A-Za-z0-9._~+/=-]{24,}",
    "discord token": "[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}",
    "github token": "gh" + "[pousr]_" + ALNUM + "{30,}",
    "github fine-grained token": "github" + "_pat_" + "[A-Za-z0-9_]{30,}",
    "aws access key": "AK" + "IA" + "[0-9A-Z]{16}",
    "slack token": "xo" + "x[abprs]-[A-Za-z0-9-]{10,}",
    "google api key": "AI" + "za" + "[0-9A-Za-z_-]{35}",
    "jwt": "ey" + "J[A-Za-z0-9_-]{10,}\.ey" + "J[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}",
    "private key block": "-----BEGIN [A-Z ]*PRIVATE" + " KEY-----",
}
COMPILED = {k: re.compile(v) for k, v in SHAPES.items()}


def text_files():
    out = subprocess.run(["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"], cwd=REPO, capture_output=True).stdout
    for f in out.decode("utf-8", "replace").split("\0"):
        if f and Path(f).suffix.lower() not in BINARY and (REPO / f).is_file():
            yield f


def find(lines):
    for n, line in enumerate(lines, 1):
        if "secret-shape-ok" in line:
            continue
        for name, rx in COMPILED.items():
            if rx.search(line):
                yield n, name


class NoSecrets(unittest.TestCase):
    def test_no_secret_shapes_in_files(self):
        hits = []
        for f in text_files():
            try:
                lines = (REPO / f).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            hits += [f"{f}:{n}: looks like a {name}" for n, name in find(lines)]
        self.assertEqual(hits, [], "secret-shaped literal(s); build the value at runtime instead of writing it:\n" + "\n".join(hits))

    def test_shapes_catch_real_looking_values(self):
        fake = ["s" + "k_live_" + "a1B2c3D4e5F6g7H8", "Bear" + "er " + "a" * 30, "gh" + "p_" + "A" * 36, "AK" + "IA" + "A" * 16,
                "xo" + "xb-" + "1234567890-abc", "AI" + "za" + "B" * 35, "ey" + "J" + "a" * 12 + ".ey" + "J" + "b" * 12 + "." + "c" * 8,
                "M" + "a" * 24 + "." + "b" * 6 + "." + "c" * 27]
        for v in fake:
            self.assertTrue(list(find([v])), v[:12])
        self.assertFalse(list(find(["Bearer token is sent in the header", "sk_live_ is the prefix", "ordinary text here"])))
        self.assertFalse(list(find(["x = " + "s" + "k_live_" + "a1B2c3D4e5F6g7H8  # secret-shape-ok"])))


if __name__ == "__main__":
    unittest.main()
