# Installing PinguinoSuite on another computer

Nothing in the Suite assumes a drive letter or folder. Everything is found relative to the Suite folder; user data lives in `Data\runtime` next to it (or wherever `PINGUINO_DATA_DIR` points).

## What you get
- **Portable folder (works today, Windows):** copy or `git clone` the Suite folder anywhere, run `App\Setup-Suite.ps1`, start `App\src-tauri\target\release\pinguino-suite.exe`.
- **Windows installer:** `App\Build-All.bat --installer` builds `PinguinoSuite_<version>_x64-setup.exe` (NSIS). The installer ships the app and the core sidecar. The module folders (`Suite\modules`, Python venv, Node, Host build) are NOT inside it yet, so on a clean PC use the portable folder route; bundling the module runtimes into the installer is the next packaging step (tracked in the roadmap).
- **Mac:** `bash App/setup-suite.sh` builds a `.app`/`.dmg` with Tauri. **Not tested yet** (no Mac was available): expect to fix small things the first time. Known gaps: the bundled core binary is looked up next to the executable, which inside a `.app` is `Contents/MacOS`, while Tauri puts resources in `Contents/Resources`; if the app cannot find the core, point it at the folder with `PINGUINO_SUITE_ROOT`. Mac should normally be an auxiliary device (no bot Host).

## Prerequisites (Setup-Suite.ps1 checks and tells you the install command)
Python 3.11+, Node 22+ (Link), .NET 8 SDK (Host, streaming PC only), Rust + Visual Studio Build Tools C++ (only to build the app shell). Tailscale for linking devices.

## First launch
A setup wizard asks for a device name and what the computer is (streaming PC / gaming PC / Mac), and can import a config bundle from another PC. The role sets the master priority (100 / 70 / 50). Change it later in Settings.

## Moving settings between computers
Settings -> **Backup & move**: *Export settings* creates a zip with settings, bots and voice commands, with passwords and keys blanked. *Export encrypted* adds the secrets inside an encrypted part (passphrase, 8+ characters). On the other computer choose the zip under *Import* (or in the wizard): you get a preview of what would change; *Apply* writes it, saving the replaced files under `Data\backups\import-<time>`. Keys already on that computer are kept when the bundle has them blanked. The device id and Link's per-device config are never exported.

## Several computers (master / auxiliary)
Exactly one online device is master and runs the bots; see "Devices: master / auxiliary" in `Docs/MODULE_CONTRACT.md`. Pair devices in the Link module.

## Paths and environment
| Variable | Meaning | Default |
|---|---|---|
| `PINGUINO_DATA_DIR` | where settings, bot data, console logs live | `<Suite parent>\Data\runtime` |
| `PINGUINO_SUITE_ROOT` | where the app looks for `Suite\suite\suite.py` | found from the exe location upward |
| `PINGUINO_PORT` | core port | 8760 |
