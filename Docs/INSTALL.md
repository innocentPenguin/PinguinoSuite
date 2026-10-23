# Installing PinguinoSuite on another computer

Nothing in the Suite assumes a drive letter or folder. Everything is found relative to the Suite folder; user data lives in `Data\runtime` next to it (or wherever `PINGUINO_DATA_DIR` points).

## One-file installer for another PC (PinguinoSuiteSetup.exe)
Built on the main PC with `Installer\Build-Installer.bat` (run `App\Build-All.bat --no-launch` first so it packs fresh builds). Output: `Installer\dist\PinguinoSuiteSetup.exe` (about 90 MB, one file, no dev tools needed on the target).

**What the target PC needs:** Windows 10 1803+ or 11, internet (for the missing prerequisites and the Python packages), and permission to install software (Windows asks). Setup installs what is missing with winget: .NET 8 runtime (bot Host), Python 3.12 (core modules), Node.js LTS (PinguinoLink), WebView2 (app window, already on Windows 11), then builds `Suite\.venv` and installs the Python packages (NVIDIA CUDA libraries only if an NVIDIA card is found). The Suite itself is the bundled release: app, core, Host build, modules. Lite is separate (its own installer, owned by the Lite unit).

**One-time setup on the main PC (private repo updates):**
1. GitHub > Settings > Developer settings > Fine-grained tokens > Generate new token. Repository access: *Only select repositories* > `innocentPenguin/PinguinoSuite`. Permissions: *Contents: Read-only* (nothing else). Expiry: 1 year. Copy the token.
2. Run `Installer\Seal-InstallKey.bat`. Paste the token (hidden) and choose an install passphrase (8+ characters, remember it). It writes `Installer\install.key.enc`, which is gitignored. The token is encrypted with your passphrase; the file alone is useless.
3. Rebuild the installer (`Installer\Build-Installer.bat`) so the sealed key is inside it.
4. To publish an update: build, run `node Installer\Build-Release.mjs --version 1.2.3`, then create a GitHub release in the private repo with the files from `Installer\distelease` (`manifest.json` and `suite-1.2.3.zip`) attached. The other PC's Updater checks the latest release at each Suite launch (never while live) and verifies the sha256 before installing.

**On the other PC:**
1. Copy `PinguinoSuiteSetup.exe` over (USB, cloud drive) and double-click it.
2. Choose the folder (default `%LOCALAPPDATA%\PinguinoSuite`), type the install passphrase, keep both boxes ticked, press Install. Wait for it to finish (the first Python package download is large).
3. Open PinguinoSuite from the Desktop or Start menu.
4. Move your settings and keys: on the main PC open Settings > Backup & move > **Export encrypted** (choose a passphrase). It saves one zip with your settings, bot files and the key vault (the vault is encrypted with that passphrase because it cannot be copied between Windows users). Copy the zip to the other PC, then Settings > Backup & move > Import, pick it, review the preview, enter the passphrase, Apply. The keys land in that PC's own vault.
5. Pair the PCs in Link; exactly one device is master and runs the bots.

Not covered yet: macOS, code signing of the exe (Windows SmartScreen may warn on first run: More info > Run anyway), Lite.

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

## Fresh-PC failure modes (reviewed 2026-10-23 by 21-Lite)
Read: `Installer/install.mjs`, `Install-PinguinoSuite.cmd`, `Build-Installer.bat`, `pinguino_installer.rs`, `prereqs.mjs`, `Suite/updater/lib/install.mjs`.
| Situation | What happens now |
|---|---|
| Node.js missing (script install, for example Lite on a second PC) | `Install-PinguinoSuite.cmd` now checks first and says how to install Node 22+ (exit 3); a too-old Node gets its own message. `PinguinoSuiteSetup.exe` carries its own node.exe, so it never needs Node. |
| Path with spaces or a OneDrive folder | Fine: the .cmd quotes `%~dp0`, the Rust setup passes paths as arguments, all paths go through `path.resolve`. Prefer a folder you own (`%LOCALAPPDATA%\PinguinoSuite`) over `Program Files` (needs admin) or a very long path. |
| No admin rights | The install itself needs none (writes only to the target folder, shortcuts in your own profile). Only the optional `--prereqs` winget installs may show a Windows permission prompt. |
| Antivirus or another program blocks a file, disk full, path too long | The install stops, removes the files it wrote and now also the empty folders it made (before, a leftover empty `Datauntime` made the retry say "that folder is not empty"). The message names the cause and what to try. A folder that only holds empty folders now counts as empty. |
| Offline, or the update server is down | Each source is tried in order (`--url` then `--local`); with none working: "every source failed; nothing was installed" and the reasons. Put the release on a USB stick and use `--local`. |
| Slow connection | Fixed: downloads of the release zip were cut off after 10 s (the limit covered the whole body, so anything slower than about 50 Mbit/s failed for a 66 MB zip). Manifest and signature keep 10 s; files get 20 minutes. |
| `--shortcuts` on a lite-minimal install | Fixed: it pointed at `pinguino-suite.exe`, which a minimal install does not have. It now makes a PinguinoLite shortcut to `PinguinoLite\Start-Lite.bat`, and refuses to make a shortcut to a file that is not there. Desktop and Start menu folders come from Windows, so a OneDrive-redirected Desktop works. |
| `Installer.hta` / `mshta` blocked (company policy) | Not fixable here: use the command line (`install.mjs`). The Rust setup shows "Setup is damaged" only when the hta is missing. |
| Windows older than 10 1803 | `tar.exe` is missing: setup says so. |
Not tested on a clean Windows install (no spare PC); the code paths above are covered by `Suite/updater/test` (42 tests) and by running the .cmd with and without Node on PATH.
