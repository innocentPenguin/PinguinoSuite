#!/usr/bin/env bash
# Set up PinguinoSuite on macOS (or Linux) from any folder. Usage: bash App/setup-suite.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "[setup] Suite folder: $ROOT"
need() { command -v "$1" >/dev/null 2>&1 || { echo "[setup] MISSING $1. $2"; MISSING=1; }; }
MISSING=0
need python3 "brew install python@3.12"
need node "brew install node   (Node 22 or newer, for Link)"
need dotnet "brew install --cask dotnet-sdk   (only if this Mac should run the bot Host; usually it will not)"
need cargo "curl https://sh.rustup.rs -sSf | sh   (for the app shell)"
[ "$MISSING" = 0 ] || { echo "[setup] Install the missing tools, open a new terminal and run this again."; exit 1; }
[ -x "$ROOT/Suite/.venv/bin/python" ] || python3 -m venv "$ROOT/Suite/.venv"
"$ROOT/Suite/.venv/bin/python" -m pip install -q --upgrade pip
"$ROOT/Suite/.venv/bin/python" -m pip install -q -r "$ROOT/Suite/requirements.txt"
[ -f "$ROOT/Suite/modules/link/package.json" ] && (cd "$ROOT/Suite/modules/link" && npm install --no-audit --no-fund)
mkdir -p "$ROOT/Data/runtime"
# Core sidecar (PyInstaller) and app shell. The sidecar must be named pinguino-core-<target triple> for Tauri bundling; see Docs/INSTALL.md.
( cd "$ROOT/Suite" && .venv/bin/python -m pip install -q pyinstaller && .venv/bin/python -m PyInstaller --noconfirm --onefile --name pinguino-core --distpath "$ROOT/App/src-tauri/binaries" suite/suite.py )
( cd "$ROOT/App" && npm install --no-audit --no-fund && npx tauri build )
echo "[setup] done. Open the .app / .dmg under App/src-tauri/target/release/bundle/ (first launch shows the setup wizard)."
