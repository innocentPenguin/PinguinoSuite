# PinguinoSuite Installer + PinguinoUpdater: plan

Owner: 01 (Core). Status: built and tested in temp dirs: `Suite/updater/` (library, CLI, signing, launch hook, 25 node tests), `Installer/` (CLI), read-only `GET /api/update/status` in the core. The launch hook exists (`updater.mjs launch`) but is NOT called from any launcher yet: 00 reviews, then adds one line to PinguinoApp.bat.
Related: `Docs/LITE_APP.md` (Lite's own update, owned by 012/04), `Suite/modules/link/src/applyupdate.mjs` (the apply pattern reused here), `App/Setup-Suite.ps1`, `Docs/MODULE_CONTRACT.md`.

## Goals and hard limits
- **PinguinoUpdater**: checks at every Suite launch and applies an available update before the app window opens. sha256-verified, backup + rollback, one update at a time.
- **Installer** (a different app): git first, then network download, then a local source (folder, USB or zip). Installs app + core + Host + modules, creates shortcuts, registers the Updater.
- Never applies while the stream is live (defers with a notice). Never touches OBS. Never reads, writes or bundles secrets. First run asks for nothing sensitive (keys are entered later in the existing vault UI).
- Tested only in temp dirs. Never run over Ivan's live install without 00's go-ahead. 00 owns the single rebuild.

## Release model
A release is:
- `suite-<version>.zip`: app exe, core exe, Host build, modules, shell UI, docs. **Never** `Data\`, the vault, tokens, logs or `.venv`.
- `manifest.json`, schema 1:
  ```json
  { "schema": 1, "channel": "stable", "version": "0.2.0", "released": "2026-10-22T00:00:00Z",
    "min_updater": 1, "notes": "short text",
    "files": [ { "name": "suite-0.2.0.zip", "url": "https://.../suite-0.2.0.zip", "size": 123, "sha256": "<64 hex>" } ] }
  ```
  `url` may be relative (resolved against the manifest location, so a folder or USB works the same as a web server).
- Channels: `stable` (default) and `beta`. Version compare is numeric per dot part (`0.10.0 > 0.9.2`).
- Integrity: every file is sha256-checked before use and again right before the swap. v1 trusts HTTPS plus the pinned hash in the manifest. **Optional Ed25519 signing is built** (`lib/sign.mjs`): a base64 `manifest.sig` next to `manifest.json` (or inside a zip bundle) signs the exact manifest bytes. It is verified only when a public key is configured (`install.json` `pubkey`, `--pubkey`); with a key set an unsigned, tampered or wrong-key release is refused before anything is downloaded. No key configured = hash-only trust over HTTPS. Ivan generates the key pair (the private seed never goes in the repo).

## Update sources (tried in this order, all yield the same manifest object)
1. **git**: when the install folder is a clone and `git` exists: `git fetch --tags`, then fast-forward to the newest tag for the channel. Local edits stop the update with a notice (never discarded).
2. **network**: HTTPS manifest URL from setting `update.url`. Empty by default, which means no network update (same rule as Lite: local only until Ivan names a source). Timeouts 10 s, size cap, redirects to HTTPS only.
3. **local**: a folder or a `.zip` that contains `manifest.json` (USB, shared drive).
The Installer uses the same order; the Updater skips straight to the configured source from `install.json`.

## PinguinoUpdater (`Suite/updater/updater.mjs`, same CLI later wrapped as a small exe)
Commands: `check`, `apply`, `rollback`, `status` (`apply` always runs the live guard, so it is the safe launch command). Launch flow (once approved): the Suite launcher runs `node Suite/updater/updater.mjs apply` before opening the window.
1. Take the lock `Data\updates\updater.lock` (stale after 30 min). A second run exits quietly.
2. Read `install.json` (version, channel, source), fetch the manifest, compare versions. Nothing newer: write `update_result.json {ok:true, upToDate:true}` and stop.
3. **Live guard**: ask the Host `GET /api/live` (fallback: core `/api/state` live flag). If live, or if the answer is unclear, write `update_deferred.json` and stop. The shell shows "Update waiting until you are off stream". Retried at the next launch.
4. Download to `Data\updates\staging\<ver>\`, verify size + sha256.
5. Re-verify, then back up every program file the release will overwrite (and note the ones it creates) to `Data\updates\backup\<from>-<timestamp>\`. If the backup fails, change nothing.
6. Extract into a `.new` folder inside the install dir with strict path checks (no `..`, no absolute paths, no drive letters, no symlinks, no files that match secret names), then swap file by file; locked files abort the swap and trigger rollback.
7. Post-check: required files exist and `install.json` is updated. The core health probe happens after relaunch (the launcher reports it into `update_result.json`).
8. Any failure: restore the backup byte for byte, write `update_result.json {ok:false, message, backup}`, keep the old version running.
Never kills a process it did not start, never contacts OBS, never writes or logs secrets.
Keep the last 3 backups. `rollback` restores the newest backup on request.

## Installer (`Installer/install.mjs`, launcher `Install-PinguinoSuite.cmd`; a GUI wrapper later if Ivan wants one)
1. Pick a source (git -> network -> local, or `--source`), pick a folder (default `%LOCALAPPDATA%\PinguinoSuite`).
2. Fetch and verify the release the same way as the Updater (shared library).
3. Lay down app + core + Host + modules. `Data\` is created empty. The old `Setup-Suite.ps1` remains the developer path (build from source).
4. Shortcuts: Start menu and desktop (behind `--shortcuts`; tests never touch the real desktop).
5. Register the Updater: write `install.json` and point the Suite launcher at `updater check --apply-if-safe`. No Windows service, no scheduled task.
6. Uninstall removes program files only, never `Data\`.

## Launch hook (built, not yet called)
`node Suite/updater/updater.mjs launch` (= `check --apply-if-safe`). It does nothing when: `install.json` has `"auto_update": false`, there is no `source`, the core already answers on 8760 (never swaps files under a running Suite), or the Host says live / unclear. Otherwise it applies with backup + rollback. Default is on once a source is set; no source = no-op, so the live git install is untouched. Tested: apply, setting off, app running, corrupt hash, live defer, failed post-check rollback.

## What runs at launch
`Suite launcher` -> `updater check --apply-if-safe` (cap 20 s for check, longer only when applying) -> app window opens. If the updater fails or times out the app still opens on the old version. The shell reads `GET /api/update/status` (read-only, from `update_result.json` / `update_deferred.json`) to show a one-line notice.

## Overlap with Lite and Link (to agree with 012)
- Lite updates itself through Link requests and `update_manifest.json`; the Suite Updater does not touch `Data\lite`. The two share only the pattern (verify, back up, restore) and may share this library later.
- Link's module install contract stays as is. Suite modules ship inside the Suite release; per-module updates keep using `App\Update-Module.ps1`.

## Tests (`node --test Suite/updater/test`, all in temp dirs)
Fake release dir with zip + manifest: success; bad hash changes nothing; newer-only; live deferral writes the file and stops; failure during swap restores the exact bytes; path traversal and absolute paths in the zip refused; lock prevents a second run; `Data\` is never touched; manifest url relative and absolute.

## Open items for Ivan
- Where releases are hosted (`update.url`) and whether the GitHub repo is public for the git path.
- Release signing key (Ed25519) so v2 can drop plain-hash trust.
- Exe wrapping: Node SEA needs `esbuild` + `postject` from npm (a download, so needs Ivan's/00's ok); the alternative is a tiny Rust launcher exe that needs node installed. Installer window: a Penguino-styled HTA (built into Windows, no downloads) driven by a progress file is the proposed no-dependency route.
- Whether beta should be offered to Ivan's own PC only.
