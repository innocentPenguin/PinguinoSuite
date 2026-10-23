"""Static lint of our own Python (suite/ and the Listen module): everything compiles, no unused imports, no bare `except:`.
Runs pyflakes as well when it is installed (undefined names etc.); the checks below need nothing extra."""
import ast
import py_compile
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted(list((ROOT / "suite").glob("*.py")) + list((ROOT / "modules" / "listen").glob("*.py")))


def unused_imports(tree, src):
    imported = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imported[(a.asname or a.name).split(".")[0]] = n.lineno
        elif isinstance(n, ast.ImportFrom) and n.module != "__future__":
            for a in n.names:
                imported[a.asname or a.name] = n.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    exported = {e.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in n.targets) for e in ast.walk(n.value) if isinstance(e, ast.Constant)}
    lines = src.splitlines()
    return [(name, ln) for name, ln in imported.items() if name not in used and name not in exported and "noqa" not in lines[ln - 1]]


class Lint(unittest.TestCase):
    def test_files_found(self):
        self.assertGreater(len(FILES), 15)

    def test_compile_unused_imports_and_bare_except(self):
        problems = []
        for f in FILES:
            src = f.read_text("utf8")
            try:
                py_compile.compile(str(f), cfile=str(ROOT / "tests" / "__pycache__" / "lint.pyc"), doraise=True)
            except py_compile.PyCompileError as e:
                problems.append(f"{f.name}: {e}")
                continue
            tree = ast.parse(src)
            problems += [f"{f.name}:{ln} '{n}' imported but unused" for n, ln in unused_imports(tree, src)]
            problems += [f"{f.name}:{n.lineno} bare except" for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
        self.assertEqual(problems, [])

    def test_pyflakes_when_available(self):
        try:
            import pyflakes  # noqa: F401
        except ImportError:
            self.skipTest("pyflakes not installed")
        r = subprocess.run([sys.executable, "-m", "pyflakes", *map(str, FILES)], capture_output=True, text=True)
        self.assertEqual(r.stdout + r.stderr, "")


if __name__ == "__main__":
    unittest.main()
