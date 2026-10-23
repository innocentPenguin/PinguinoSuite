# Publishing a Lite release (exact steps for Ivan)

Written 2026-10-23 by 21-Lite. Everything below was dry-run in a scratch folder (nothing installed, nothing pushed). Companion docs: `RELEASE_DRYRUN.md` (updater dry-run table + signing), `INSTALL.md` (Suite installer), `LITE_APP.md`.

## How it fits together
- There is ONE release format for Suite and Lite: `manifest.json` + `suite-<version>.zip` (+ `manifest.sig` when signed). `Installer\Build-Release.mjs` packs the current built Suite **and** Lite into it. The manifest lists per-part hashes; Lite uses the parts `lite`, `link`, `tools` (profile `lite-minimal`). Checked: the `lite` part holds exactly 2 files (`PinguinoLite\src-tauri\target\release\pinguino-lite.exe`, `PinguinoLite\Start-Lite.bat`), `link` 32, `tools` 23.
- The zip always contains the whole Suite (about 66 MB); a minimal install downloads it once and keeps only `lite`, `link`, `tools` (about 8 MB on disk). Other modules are added later with the Install button (fetched from the same zip).
- **Update source** = the `source` entry in the install's `install.json`. Only the shared Node updater reads it (Lite's Parts card, Verify/Repair/Eject/Install). PinguinoLink does **not** read install.json and has no update server ("local sources only"), so nothing needs configuring in Link.
- `source` is recorded only when the install is made from a network source (`--url`, `--github`) or with `--update-from`. An install made with `--local` (USB, folder, zip) records **no** source and Lite's Install button then says "No update source is set".

## Before you start (on the main PC, with Lite and the Suite CLOSED)
1. Build the Suite: `App\Build-All.bat --no-launch` (the release needs `pinguino-suite.exe`, `pinguino-core.exe`, `PinguinoHost.dll`).
2. Build Lite: in `PinguinoLite\src-tauri` run `cargo build --release --features custom-protocol` (only after the coordinator has closed Lite; the exe is locked while it runs). The exe currently in `target\release` may be older than the source: rebuild so the release carries the newest Lite.
3. Make the GitHub repo `innocentPenguin/PinguinoLite` and keep it **public** (checked 2026-10-23: the API answers 404 for it, so it does not exist yet or is private). Reason: the `https` update source has no token; a private repo needs the `github` source plus the sealed key (`Seal-InstallKey`, see RELEASE_DRYRUN.md section "Signed releases").

## Build the release
Version = plain numbers only (`1.2.3`; names like `1.0.0-dry` are refused).
```
node Installer\Build-Release.mjs --version 1.0.0 --out Installer\dist\release
```
With signing (recommended once the key exists, see RELEASE_DRYRUN.md):
```
node Installer\Build-Release.mjs --version 1.0.0 --out Installer\dist\release --sign-key C:\path\to\signing-seed.txt
```
Before a real release, run `Installer\Selftest.bat` (17 PASS/FAIL steps in a temp folder, about 15 s, nothing real touched; see `RELEASE_DRYRUN.md`). For release notes: `node Installer\Release-Notes.mjs --from <last tag or commit> --out notes.txt`, then add `--notes-file notes.txt` to the Build-Release command.

Output in `Installer\dist\release`: `manifest.json`, `suite-1.0.0.zip`, and `manifest.sig` when signed. The script reads only; it refuses when something secret-looking would ship (vault, .env, tokens) and when Host or core are missing.

## Publish to GitHub (nothing is pushed by the build)
`gh` is not installed on this PC, so use the website:
1. https://github.com/innocentPenguin/PinguinoLite/releases/new
2. Tag `v1.0.0` (create it), title `PinguinoLite 1.0.0`.
3. Attach exactly these files (names must stay): `manifest.json`, `suite-1.0.0.zip`, and `manifest.sig` if you signed. Publish.
4. Check in a browser: `https://github.com/innocentPenguin/PinguinoLite/releases/latest/download/manifest.json` shows the manifest.
(If you install `gh` later: `gh release create v1.0.0 Installer\dist\release\* --repo innocentPenguin/PinguinoLite --title "PinguinoLite 1.0.0"`.)

The Lite "Check for updates" button reads `releases/latest` of that repo, so it starts working after the first release.

## Minimal install on the second PC
The updater needs Node 22+ on that PC. Copy two folders from the main PC (USB or cloud) to the second PC, for example into `C:\PinguinoSetup\`: `Installer\` and `Suite\updater\` (keep them side by side as `Installer` and `Suite\updater`). Then:
```
node C:\PinguinoSetup\Installer\install.mjs --target C:\PinguinoLite --url https://github.com/innocentPenguin/PinguinoLite/releases/latest/download/manifest.json --pubkey <public key, only if signed> --profile lite-minimal --shortcuts
```
Result: `C:\PinguinoLite\install.json` holds `profile: "lite-minimal"`, `parts: [lite, link, tools]`, the `pubkey` if given, and **`source: { "type": "https", "url": "<the manifest url>" }`**. That `source` is what the Install, Parts and Verify buttons need on that PC. Start Lite with `C:\PinguinoLite\PinguinoLite\Start-Lite.bat`.

Minimal `install.json` the second PC must end up with (check it after install):
```
{ "schema": 1, "version": "1.0.0", "channel": "stable",
  "source": { "type": "https", "url": "https://github.com/innocentPenguin/PinguinoLite/releases/latest/download/manifest.json" },
  "pubkey": "<base64 32-byte public key, or absent for unsigned>",
  "profile": "lite-minimal", "parts": ["lite", "link", "tools"], "components": { ... } }
```
Notes:
- `https` is the right source type for a public repo; `type: github` always demands the sealed read-only token, even for public repos.
- The zip URL is resolved next to the manifest URL (`releases/latest/download/suite-<ver>.zip`), so "latest" always pairs the manifest with its own zip.
- `--local <folder|zip>` (offline USB install) works the same but records no source; add it afterwards by hand-editing `install.json`, or reinstall with `--url`.

## Later releases
Repeat Build + Publish with a higher version. On the second PC Lite's Parts card shows "Update available" per part; `lite` is staged and applied the next time Lite starts, `link` is swapped by Lite (it stops and restarts the Link it owns). Updates never run while you are live.

## Dry-run result (2026-10-23, scratch folder, throwaway key)
Build-Release 1.0.0 signed: manifest + sig + 66 MB zip, parts core 17, link 31, listen 13, multi 57, spotify 31, voice 10, tools 23, host 33, shell 1, lite 2. `install.mjs --local ... --pubkey ... --profile lite-minimal`: 57 files, `install.json` as above (no `source` because `--local`). `check`/`verify` OK. Tampered manifest, removed `.sig` and wrong key were each refused with a clear message. `--url http://...` is refused ("updates must come from an https address").
Fixed on the way: the build crashed with EBUSY on `Suite\modules\spotify\bin\spike-cfg\lockfile` (a running Spotify module); `spike-cfg` and `lockfile` are now never packed (commit 927a625).
Not tested (needs the real repo): the actual download from GitHub.
