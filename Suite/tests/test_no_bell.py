"""No script of ours may ring the terminal bell or beep (a visible PowerShell/conhost turns BEL into an audible beep).
Scans our scripts for Beep/SystemSounds/MessageBeep/BEL characters. Speech and stingers (winsound.PlaySound of a WAV) are not bells and are allowed.
Test files (test-*, test_*, check.mjs) may mention BEL on purpose (they check that control characters are stripped); other lines opt out with `nobell-ok`."""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXT = {".ps1", ".psm1", ".bat", ".cmd", ".vbs", ".py", ".mjs", ".js"}
SKIP_DIRS = {"node_modules", "target", "dist", ".git", "__pycache__", "build", "tests", "test", "Tests"}
BAD = re.compile(r"""\[\s*console\s*\]\s*::\s*beep|\bwinsound\s*\.\s*(Beep|MessageBeep)|\bMessageBeep\b|\bSystemSounds\b|Media\.SoundPlayer|\btput\s+bel\b|\x07|\u0007|\a(?=["'])|chr\(\s*7\s*\)|\[char\]\s*7\b|"`a"|\x07""", re.I)


def scripts():
    for p in REPO.rglob("*"):
        if p.suffix.lower() in EXT and p.is_file() and not re.match(r"(test[-_.]|check\.)", p.name, re.I) and not (SKIP_DIRS & set(p.relative_to(REPO).parts[:-1])):
            yield p

BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".webm", ".mp4", ".mp3", ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".otf", ".zip", ".exe", ".dll", ".rgba", ".pdf", ".db", ".sqlite", ".gz", ".7z", ".bin", ".wasm", ".node", ".pyc"}
# Files with a known raw BEL waiting for their owner to patch (none now); add the path here only as a short-lived exception.
PENDING = set()


def text_files():
    out = subprocess.run(["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"], cwd=REPO, capture_output=True).stdout
    for f in out.decode("utf-8", "replace").split("\0"):
        if f and Path(f).suffix.lower() not in BINARY and (REPO / f).is_file():
            yield f


class NoBell(unittest.TestCase):
    def test_no_raw_bel_in_any_tracked_text_file(self):
        """Scripts, tests, fixtures, JSON, docs: a raw 0x07 rings the speaker whenever someone cats or greps the file."""
        hits = []
        for f in text_files():
            if f in PENDING:
                continue
            data = (REPO / f).read_bytes()
            for n, line in enumerate(data.split(b"\n"), 1):
                if b"\x07" in line:
                    hits.append(f"{f}:{n}: {line.replace(bytes([7]), b'<BEL>')[:90]!r}")
        self.assertEqual(hits, [], "raw BEL (0x07) in files; a lost backslash-a (\a in a path) is the usual cause:\n" + "\n".join(hits))

    def test_runners_sanitize_control_chars(self):
        """Our test runners must not pass raw control characters to the console."""
        for f in ["Tests/bots/run-bots-tests.ps1", "Tests/chat/run-chat-tests.ps1", "Tests/core/run-tests.ps1", "Tests/helper/run-helper-tests.ps1", "Tests/history/run-hook-check.ps1"]:
            run = [l for l in (REPO / f).read_text(encoding="utf-8", errors="replace").splitlines() if l.startswith("dotnet run")]
            self.assertTrue(run and all("x07" in l.lower() or "x00-" in l.lower() for l in run), f"{f}: dotnet output is not filtered for control characters")
        for f in ["Installer/Selftest.mjs", "Installer/Rebuild-Plan.mjs", "Tests/history/test-summaries.mjs"]:
            self.assertIn("safe_print", (REPO / f).read_text(encoding="utf-8"), f"{f}: does not install safe_print")

    def test_safe_print_helpers(self):
        import sys
        sys.path.insert(0, str(REPO / "Suite" / "tools"))
        from safe_print import clean
        self.assertEqual(clean("a" + chr(7) + "b\tc\n"), "a" + chr(92) + "x07b\tc\n")
        out = subprocess.run(["node", "--input-type=module", "-e", "import {clean} from './Suite/tools/safe_print.mjs'; process.stdout.write(clean('a\x07b\tc'))"], cwd=REPO, capture_output=True).stdout
        self.assertEqual(out, b"a" + bytes([92]) + b"x07b\tc")

    def test_no_bell_or_beep_in_scripts(self):
        hits = []
        for p in scripts():
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for n, line in enumerate(lines, 1):
                if BAD.search(line) and "nobell-ok" not in line:
                    hits.append(f"{p.relative_to(REPO)}:{n}: {line.strip()[:100]}")
        self.assertEqual(hits, [], "bell/beep in scripts (no audio from scripts, ever):\n" + "\n".join(hits))

    def test_lint_catches_a_bell(self):
        for s in ["[console]::beep(800,200)", "[Console]::Beep()", "winsound.Beep(1,1)", "print(chr(7))", 'echo "`a"', "x = '\x07'", "SystemSounds.Beep.Play()"]:
            self.assertTrue(BAD.search(s), s)
        self.assertFalse(BAD.search("winsound.PlaySound(f, SND_FILENAME)"))


if __name__ == "__main__":
    unittest.main()
