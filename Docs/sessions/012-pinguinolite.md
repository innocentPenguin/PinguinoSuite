# Session 012 - PinguinoLite (notes, plain language)

Updated 2026-10-23. Repo: D:\PinguinoSuite (all work is local commits, nothing pushed). App code: PinguinoLite\ (Tauri 2). Coordinator = 00, installer/updater = 01, Link = 04.

## 1. What I built and why
PinguinoLite = a light app (Dashboard, Modules, Replays pages) that bundles PinguinoLink, for a second/lighter PC.
- Replay stats (55d7e93, 10b24fc, 9bb1bda, eae14f3; Docs\REPLAY_STATS_PLAN.md): scans Rocket League replay folders every 3 s (stat-only), parses the header locally (boxcars), writes result JSON under <lite dir>\replays. Rule from 00/Ivan: always scan; the activity gate (RocketLeague.exe running AND Host /api/customs/state = casual/competitive/koth) only decides whether the winner is auto-attributed. Ranked stays off.
- Icon + brand (9671ad7, b6e4f8a; 00 added b2e5b33): Ivan sent screenshots, icon looked sepia and the bolt too small. Small-size grayscale art, multi-size ico, "Pinguino" white + "Lite" orange.
- Update check (c2dada3): GitHub repo innocentPenguin/PinguinoLite via curl.exe, no token, quiet once a day + button.
- Scan-interval slider 1-10 s (8993507): Ivan asked for a user-settable interval.
- Quit failsafes (2dbbe6c) and Suite parity (ff8c379): Alt+F4/close asks first in an in-page dialog (confirm() is blocked in the webview), tray Quit, tray Force quit, 6 s watchdog, F11 full screen. Copied from the Suite's 2a7fec6 / 6684691.
- Per-part updates (fd20321, 01's fe6f71f added the `lite` part): Parts card calling the shared Node updater.
- Module files card (ff8c379, b41c28e): Verify / Repair / Eject / Install per on-demand module (listen, multi, spotify) + install profiles (`lite-minimal` = parts lite, link, tools). Ivan/00: "other PC minimal install: only Link, everything else listed as Install, downloaded only on click".

## 2. Decisions and failures
- Network/native access only through Rust commands (CSP connect-src 'self').
- Updates reuse the Suite's Node updater instead of a Rust reimplementation (hash/path rules, backups, lock). Lite only adds: live guard (explicit "not live" required, unreadable = hold), stop/start of the Link it owns, never touches OBS.
- Eject = files MOVED to Data\updates\ejected, never deleted. Install = `apply --only id`, Repair = `apply --only id --repair`, Eject = `eject --part id`.
- Failures I hit: Rust comment with backslash-letter sequences broke the build; CRLF made Python edits silently miss; `pub` on a #[tauri::command] in main.rs duplicates macros (use a wrapper fn); the release exe is locked while Lite runs (build to a scratch target dir to check, real build after 00 closes Lite).

## 3. For the next session
- Only 00 launches/rebuilds. Release build: `cargo build --release --features custom-protocol` in PinguinoLite\src-tauri. Tests: `cargo test` (15 pass). UI script check: extract inline <script> and `node --check`.
- Real test done on a scratch copy (Build-Release -> install.mjs --profile lite-minimal --local -> updater verify/apply/eject cycle): all OK. Buttons in the actual window are NOT clicked yet.
- Verify live: icon/taskbar, Alt+F4 dialog, tray Force quit, F11, Replays page + slider, Parts and Module files cards (need an installed copy with install.json), update check button.
- Open: parser never run on a real replay; Lite GitHub repo has no release/manifest; empty module folder left after eject; eject waits a fixed 3 s after asking Link to stop (should check it stopped); Modules catalog (from 04) can disagree with the install profile.

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
