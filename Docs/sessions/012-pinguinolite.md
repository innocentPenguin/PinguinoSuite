# Session 012 - PinguinoLite (notes, plain language)

Updated 2026-10-23 (final, coding stopped on 01's order). Latest Lite commit 141a126; rebuild needed for everything since c2dada3. Repo: D:\PinguinoSuite (all work is local commits, nothing pushed). App code: PinguinoLite\ (Tauri 2). Coordinator = 00, installer/updater = 01, Link = 04.

## 1. What I built and why
PinguinoLite = a light app (Dashboard, Modules, Replays pages) that bundles PinguinoLink, for a second/lighter PC.
- Replay stats (55d7e93, 10b24fc, 9bb1bda, eae14f3; Docs\REPLAY_STATS_PLAN.md): scans Rocket League replay folders every 3 s (stat-only), parses the header locally (boxcars), writes result JSON under <lite dir>\replays. Rule from 00/Ivan: always scan; the activity gate (RocketLeague.exe running AND Host /api/customs/state = casual/competitive/koth) only decides whether the winner is auto-attributed. Ranked stays off.
- Icon + brand (9671ad7, b6e4f8a; 00 added b2e5b33): Ivan sent screenshots, icon looked sepia and the bolt too small. Small-size grayscale art, multi-size ico, "Pinguino" white + "Lite" orange.
- Update check (c2dada3): GitHub repo innocentPenguin/PinguinoLite via curl.exe, no token, quiet once a day + button.
- Scan-interval slider 1-10 s (8993507): Ivan asked for a user-settable interval.
- Quit failsafes (2dbbe6c) and Suite parity (ff8c379): Alt+F4/close asks first in an in-page dialog (confirm() is blocked in the webview), tray Quit, tray Force quit, 6 s watchdog, F11 full screen. Copied from the Suite's 2a7fec6 / 6684691.
- Per-part updates (fd20321, 01's fe6f71f added the `lite` part): Parts card calling the shared Node updater.
- Module files card (ff8c379, b41c28e): Verify / Repair / Eject / Install per on-demand module (listen, multi, spotify) + install profiles (`lite-minimal` = parts lite, link, tools). Ivan/00: "other PC minimal install: only Link, everything else listed as Install, downloaded only on click".

- Follow-ups (141a126, 2026-10-23, approved by 01): eject polls Link's status.json until the module stops (20 s, no fixed wait); Install refuses with a clear message when install.json has no update source; quit dialog got "Quit, keep Link running" (my reading of "Quit and stop Link", since Lite already stops the Link it started); Dashboard Replays card.
- Real scratch test of the profile cycle (Build-Release -> install --profile lite-minimal -> add spotify -> damage -> repair -> eject -> install again) passed. 01 then removed the empty module folder left after eject (da0d8b2).

## 2. Decisions and failures
- Network/native access only through Rust commands (CSP connect-src 'self').
- Updates reuse the Suite's Node updater instead of a Rust reimplementation (hash/path rules, backups, lock). Lite only adds: live guard (explicit "not live" required, unreadable = hold), stop/start of the Link it owns, never touches OBS.
- Eject = files MOVED to Data\updates\ejected, never deleted. Install = `apply --only id`, Repair = `apply --only id --repair`, Eject = `eject --part id`.
- Failures I hit: Rust comment with backslash-letter sequences broke the build; CRLF made Python edits silently miss; `pub` on a #[tauri::command] in main.rs duplicates macros (use a wrapper fn); the release exe is locked while Lite runs (build to a scratch target dir to check, real build after 00 closes Lite).

## 3. For the next session
- Only 00 launches/rebuilds. Release build: `cargo build --release --features custom-protocol` in PinguinoLite\src-tauri. Tests: `cargo test` (15 pass). UI script check: extract inline <script> and `node --check`.
- Real test done on a scratch copy (Build-Release -> install.mjs --profile lite-minimal --local -> updater verify/apply/eject cycle): all OK. Buttons in the actual window are NOT clicked yet.
- Verify live: icon/taskbar, Alt+F4 dialog, tray Force quit, F11, Replays page + slider, Parts and Module files cards (need an installed copy with install.json), update check button.
- Open (updated 2026-10-23 by 21-Lite): Lite GitHub repo has no release/manifest (404 or private); empty module folder left after eject. Done since: parser run on a real 2v2 replay (fixture test), eject waits until Link reports stopped AND the module port is closed (35 s, shows Link's error), Modules catalog follows install.json parts (mergeRows, node tests).

## 4. Future ideas (priority)
1. Run the parser on a real replay and compare with the scoreboard.
2. Publish a Lite release with a manifest; decide the Link update source.
3. Click-test the Module files card on a real minimal install.
4. Catalog follows the profile (one "Not installed" source).
5. "Quit and stop Link" option in the quit dialog.
6. Replay stats card on the Dashboard.
7. Real "module stopped" check before eject.

## 5. Chat history
Session id f4dd94ce-1d48-45f2-96c8-ed0a9c4fab57, transcript C:\Users\ivanm\.claude\projects\D--\f4dd94ce-1d48-45f2-96c8-ed0a9c4fab57.jsonl. Grep for: "lite-minimal", "confirm-quit", "replay_set_interval", "parts_eject", "GATES_ENABLED".

## 6. Things Ivan may be forgetting
- Nothing is pushed; Lite repo on GitHub has no release, so the update check always says "No release published yet".
- The other PC needs a release built by the current Build-Release plus an install source (GitHub/URL) in install.json, otherwise the Install buttons cannot fetch anything. A private repo needs the sealed key step.
- Replays only work if Rocket League saves replays on that PC; Demos folder was not found on this one.
- Scratch test data (~100 MB) sits in this session's scratchpad folder and can be deleted.
- Quit/Force quit/F11 and the icon are unverified until someone launches the rebuilt app.

## 7. Verify after the next Lite rebuild (for the coordinator)
Everything below is source-only until Lite is rebuilt (`cargo build --release --features custom-protocol`, Lite closed). Unit tests pass; none of it was clicked in the real window.
1. Replays page: lists replays from Documents AND OneDrive\Documents (OneDrive must be running; online-only files are skipped and counted as `unreadable`). Platforms show Steam/Epic/Xbox/PlayStation/Switch, not raw names like dingo.
2. Modules page on a lite-minimal install: listen/multi/spotify show "Not installed" with an Install button (calls Lite parts_install, not Link); link shows installed. No version/update/conn state on not-installed rows.
3. Install a module: waits, then the row turns installed. Eject a running module: Lite asks Link to stop, waits until status.json says stopped and the port is closed (up to 35 s), then moves files. If it refuses, the message includes Link's error.
4. Start/Stop/Restart from Lite on a module: goes through request files, Link drops Data/runtime/control/<action>-<id>, the Suite core acts. With the Suite closed, expect "the Suite core did not pick up the request".
5. The exe in the release is the new one: `Installer\Build-Release.mjs` lite part has 2 files (exe + Start-Lite.bat); check the exe timestamp is after the rebuild.
6. Release/signing: follow Docs/LITE_RELEASE.md and Docs/RELEASE_DRYRUN.md (key with Installer/Make-SigningKey.mjs, `--sign-key`, publish three files, install on the second PC with `--url ... --pubkey ... --profile lite-minimal`).
7. On the gaming PC (the only one with Rocket League): the replay scan finds the Demos folder under OneDrive\Documents if Documents is redirected. Do not run the live scan on the main PC.

## 8. Compile Lite on this PC (21-Lite, 2026-10-23)
Findings: the earlier "paging file too small" / "metadata stub" / LNK1108 failures had two causes. (1) C: was 100% full (425 MB free; scratch targets under `%TEMP%` live on C:), so linker writes failed. I deleted my own scratch folders (4 GB free now). (2) Windows commit limit: 45 GB RAM + 30 GB pagefile (auto-managed) = 75 GB, and at the time about 74.7 GB was committed (big python processes: 3.5 GB, 2.4 GB, 1.4 GB, node 1.7 GB, ...), leaving about 0.6 GB free commit. Free physical RAM is not the limit.
Command to try (not run in full by me; 100 was going to do the real build):
```
$env:CARGO_TARGET_DIR='D:\cargo-target\lite'; $env:CARGO_BUILD_JOBS='1'; $env:CARGO_PROFILE_DEV_DEBUG='0'; cargo test --manifest-path D:\PinguinoSuite\PinguinoLite\src-tauri\Cargo.toml
```
D: has 266 GB free, so the target dir goes there. If it still dies with os error 1455 / exit 0xc000012d: the commit limit is the cause; ask Ivan/100 to add a pagefile on D: (System > Advanced > Performance > Virtual memory, 32 GB on D:); I did not change system settings. Without the full build, the pure parts of parts.rs and replays.rs are tested in a tiny scratch crate (copy the functions plus `serde_json`, no tauri), which compiles in about 10 s.
