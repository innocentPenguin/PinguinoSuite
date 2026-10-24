"""No script of ours may ring the terminal bell or beep (a visible PowerShell/conhost turns BEL into an audible beep).
Scans our scripts for Beep/SystemSounds/MessageBeep/BEL characters. Speech and stingers (winsound.PlaySound of a WAV) are not bells and are allowed.
Test files (test-*, test_*, check.mjs) may mention BEL on purpose (they check that control characters are stripped); other lines opt out with `nobell-ok`."""
import re
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


class NoBell(unittest.TestCase):
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
