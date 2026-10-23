# Rebuild / restart checklist for 100

Written 2026-10-23 by 21-Lite. Only 100 launches or rebuilds (single-launcher rule). Nothing here was run by me.

**This list goes stale. Regenerate it any time:**
```
node Installer\Rebuild-Plan.mjs            # plain text
node Installer\Rebuild-Plan.mjs --md       # markdown (what is pasted below)
node Installer\Rebuild-Plan.mjs --files    # also the changed files per commit
node Installer\Rebuild-Plan.mjs --all      # list the no-rebuild commits one by one
node Installer\Rebuild-Plan.mjs --since 2026-10-22   # one date (or commit) for every part
```
It is read-only (git log + file times). "Last build" per part = the mtime of its newest built file: shell `pinguino-suite.exe`, core `binaries\pinguino-core.exe`, Host `PinguinoHost.dll`, Lite `pinguino-lite.exe` (also looks in `D:\cargo-target\lite\release`). A module runs from the tree, so its "last restart" is unknowable; the app/core exe time stands in for it (a module restarted later with `Update-Module` still shows up here: restart it again, it is harmless). A part with no built file falls back to 2026-10-22 00:00. The path rules are the `PARTS` table at the top of the script.

## Path rules (what needs what)
| Changed path | Needs |
|---|---|
| `App\src\**`, `App\src-tauri\{src,capabilities,tauri.conf.json,Cargo.*,icons}` | shell rebuild |
| `Suite\suite\*.py`, `Suite\modules.json` | core rebuild (frozen exe) |
| `PinguinoHost\**` (not bin/obj/docs) | Host rebuild |
| `Suite\modules\{listen,multi,link,spotify,voice}\**` | module restart (they run from the tree; no build) |
| `PinguinoLite\{src,src-tauri\...}` | Lite rebuild (separate exe, separate target dir) |
| Node tests, `Suite\tests`, `Docs`, `Installer`, `Tools`, `Tests`, site, bots' data | nothing |

Traps:
- `App\Build-All.bat` can say **"[core] up to date, skipped"** although `Suite\modules.json` or core code changed: `Stale.ps1` compares file times only and the APP_LOG already recorded this once (079ed6e). Use `App\Build-All.bat --only core --force`.
- A module file change does NOT need a core rebuild. Use `App\Update-Module.bat listen` (then multi, link, spotify, voice).
- Quit the app from the tray first, or the exe / Host DLL / core exe are locked (the 2026-10-23 05:01 rebuild needed three attempts for a Host DLL lock).
- Never rebuild while live: `GET http://127.0.0.1:8770/api/live` must say false.

## Snapshot (generated 2026-10-23 by `Rebuild-Plan.mjs --md`)
### Shell rebuild (Tauri app): 2 commits
- since 2026-10-23T14:34:18.224Z (App/src-tauri/target/release/pinguino-suite.exe)
- do: App\Build-All.bat --only shell (Build-Shell skips when nothing is newer)
- `eeaa687` Shell + Listen UI: no native confirm(), in-flight guard on POST buttons, module/device buttons report refusals, long text wraps
- `3a2cc5c` Master View: per-source outage matrix; 502-504 now means Host offline, junk/500 replies no longer look fresh, Multi pinged while Stream tab is open

### Core rebuild (frozen Python): 3 commits
- since 2026-10-23T14:31:19.246Z (App/src-tauri/binaries/pinguino-core.exe)
- do: App\Build-All.bat --only core --force   (Build-All may say "up to date" and skip: Stale.ps1 only compares times, so force it)
- `b67094a` Fix escape in write_core_pid docstring (lint)
- `d159946` Listen: opt-in core watchdog (PINGUINO_LISTEN_WATCHDOG=1, default off) + core writes Data/pids/core.json
- `6931550` Core: cap log growth (gzip archives, running-log warning, 2 GB feedback cap) and clean shutdown (no orphan modules, health loop ends)

### Host rebuild (dotnet): 1 commit
- since 2026-10-23T14:45:25.792Z (PinguinoHost/bin/Release/net8.0/PinguinoHost.dll)
- do: App\Build-All.bat --only host
- `ea9a8f1` C:/Program Files/Git/api/intro/viewer also answers by login

### Module restart (Listen, Multi, Link, Spotify, Voice): 11 commits
- since 2026-10-23T14:34:18.224Z (App/src-tauri/target/release/pinguino-suite.exe)
- do: App\Update-Module.bat <id>  (listen first; or restart the whole app)
- `d159946` Listen: opt-in core watchdog (PINGUINO_LISTEN_WATCHDOG=1, default off) + core writes Data/pids/core.json
- `6a35d39` Intro viewer route also answers by login
- `fdd7d93` Multi alerts: OBS chat overlay hardening (zalgo, bidi, backfill after reconnect, boot retry), alerts segs() tolerant
- `fe9141d` Voice: hand the module token to the page (direct loopback only) and require it for settings/speak/control POSTs
- `eeaa687` Shell + Listen UI: no native confirm(), in-flight guard on POST buttons, module/device buttons report refusals, long text wraps
- `daa8289` Multi connectors: Host 5xx never repeated, MULTI_NO_SEND in host_feed, server keeps send key after unknown outcome, dev inject text optional
- `f4cd06e` Multi connectors: at-most-once chat send guard in every connector (timeouts, 5xx, refresh retry, double click, MULTI_NO_SEND)
- `25dffd4` Multi alerts: launcher YouTube card points at the sign-in box, Missed count uses missed_total
- `457ffd9` Voice: harden per 52's review (headers, token fail-closed, sensitive GETs, 413, secret filter, timeout confirm page-only, device-name files, log rotation)
- `92b3af5` Multi alerts: full-Host rehearsal rig, intro retry after Host outage, Host HTTP errors count as reachable, media upload hardening
- `0206da9` Multi connectors: Twitch hardening (401 refresh, 429, revocation, replays, timestamps) + PLATFORMS.md

### Lite rebuild (PinguinoLite, Tauri): 15 commits
- since 2026-10-22T11:53:35.742Z (PinguinoLite/src-tauri/target/release/pinguino-lite.exe)
- do: D: target recipe, see Docs\sessions\012-pinguinolite.md section 8: $env:CARGO_TARGET_DIR='D:\cargo-target\lite'; $env:CARGO_BUILD_JOBS='1'; cargo build --release --
- `23c64d5` Lite page polish: focus rings on buttons, keyboard nav, dialog Esc/Tab trap/focus return, wrap-anywhere, buttons disabled while a command runs (survives redra
- `d711c83` Log hygiene: Link rotates link.jsonl itself (2 MB x 3), replay seen-state bounded, support bundles keep newest 5, Windows account name masked in bundles
- `ac8a011` Lite: compile-by-eye fixes (updater live probe uses HTTP/1.0 so no chunked body; explicit str arg for curl)
- `692dd64` Lite: first-run hints on Dashboard/Modules/Replays, Open bundle folder button and privacy note
- `addb524` Lite replays: size cap, parse time cap and panic guard so bad .replay files are skipped and counted unreadable
- `85ee4de` Lite: support bundle (scrubbed logs, install info, parts check, system numbers) with page button
- `6a5d9f9` Lite: pure apply_args/updater_argv helpers + tests; node test for the exact Lite command lines
- `7bb6a31` Lite: missing installed version is not an update; gaming-PC checklist item
- `af4eba0` Lite: eject waits for Link stopped + port closed (35 s), shows Link's error; tests
- `d262720` Lite replays: find OneDrive-redirected Documents, friendly platform names, unreadable counter, real-replay + anonymised real-header tests
- `04776dd` Lite: Modules page follows install.json parts for Not installed (mergeRows + tests)
- `141a126` Lite: eject waits for Link to report the module stopped, no-source guard on Install, Quit keep-Link option, Dashboard replay card
- `b41c28e` Lite: use 01's real updater verbs (apply --only to install, eject --part, apply --repair)
- `ff8c379` Lite: Suite quit parity (watchdog, force kill tree, F11 full screen) and module Verify/Eject/Install with lite-minimal profile
- `fd20321` Lite: per-part updates via the shared Node updater (Parts card, Link stop/swap/start, staged Lite files, rollback, live guard)

### No rebuild (Node, site, docs, tests, installer tools): 396
Docs 138, Suite 103, App 50, PinguinoHost 46, PinguinoB0t 29, Tools 6, .gitignore 5, PinguinoChat 5, Installer 3, HelperPinguino 3, PinguinoLite 3, Tests 2, PinguinoApp 2
### Order
1. Tell Ivan, and check that the stream is OFFLINE (GET /api/live on 8770 must say false). Never rebuild while live.
2. Quit the app from the tray (Quit), so the exe, the core and the Host DLL are not locked.
3. Host: App\Build-All.bat --only host
4. Core: App\Build-All.bat --only core --force
5. Shell: App\Build-All.bat --only shell
6. Launch with PinguinoApp.bat (or Build-All.bat with no flags builds the stale pieces and launches).
7. Lite (can run beside the above, only the coordinator): the D: target recipe from the Lite line.

## Exact order (the full case; skip lines that have no commits above)
1. Ask Ivan / check offline: `GET http://127.0.0.1:8770/api/live` is false and OBS is not streaming.
2. Tray menu > Quit (the app, core, modules and Host stop). Check in Task Manager that `pinguino-suite.exe`, `pinguino-core.exe` and `dotnet PinguinoHost` are gone; wait for the file locks.
3. `App\Build-All.bat --only host` (Host first: the shell needs nothing from it, but a failed Host should stop the night early).
4. `App\Build-All.bat --only core --force` (forced, see the trap above).
5. `App\Build-All.bat --only shell` (about 4-5 min)
6. Or steps 3-5 in one go: `App\Build-All.bat --force --no-launch` (rebuilds everything, about 10 min). Either way, nothing launches unless every piece succeeded.
7. Launch: `PinguinoApp\PinguinoApp.bat`. This restarts every module with the new tree, so a separate Listen restart is not needed after a full launch. Only module commits and no shell/core/host commits: skip steps 2-7 and run `App\Update-Module.bat listen` (and the others listed), one at a time, no app quit.
8. Lite (separate, any time, not needed by the Suite): in PowerShell
   `$env:CARGO_TARGET_DIR='D:\cargo-target\lite'; $env:CARGO_BUILD_JOBS='1'; $env:CARGO_PROFILE_DEV_DEBUG='0'; cargo build --release --manifest-path D:\PinguinoSuite\PinguinoLite\src-tauri\Cargo.toml`
   (D: has the space; C: was 100% full once; an os error 1455 means the Windows commit limit: add a pagefile on D:, see `Docs\sessions\012-pinguinolite.md` section 8). The exe lands in `D:\cargo-target\lite\release\pinguino-lite.exe`; copy it to `PinguinoLite\src-tauri\target\release\` only if you want the shortcut to use it. `cargo test` of the whole crate has never run on this PC (see the 012 header).
9. Add a line to `Docs\APP_LOG.md` (time, which pieces, which commit, what answered).

## Smoke test after the restart (10 steps, SAFE: GET only, no live, no chat posts, no OAuth)
Do it with `curl.exe` or the browser. Ports as in APP_LOG: core 8760, Host 8770, Listen 8765, Multi 8766, Link 7777, Spotify 8771, Voice 8772.
1. Core answers: open `http://127.0.0.1:8760/` (any 200 page or the JSON status). Fail: the core exe did not start; read `Suite\logs\suite.log`.
2. Host answers and is offline: `GET :8770/api/live` is 200 and says false. Fail: Host DLL missing or locked; run `App\Build-All.bat --only host`.
3. Host new routes: `GET :8770/api/intro` and `GET :8770/api/scene-layouts` both 200.
4. Modules up: `GET :8765/`, `:8766/`, `:7777/`, `:8771/`, `:8772/` all answer (any 200/401 page is fine; connection refused is a fail). Check `Suite\logs\listen.log`, `multi.log`, `voice.log`, `spotify.log` for the last 2 minutes: no "Traceback" or "unauthorized".
5. Shell window opens, title and version right; click through Dashboard, Chat, Listen, Master View, Problem reports, Accounts. No red banner, no blank page, Master View shows Host online with the outage matrix filled.
6. Listen page: the module shows running and the mic (device list) loads. Do not press Test-speak or any send button.
7. OBS overlays render in a browser (not in OBS): `http://127.0.0.1:8766/obs/alerts` and `/obs/goal` return a page.
8. Problem reports page: "Run the morning check" (read-only self-check) is all green or explains itself; module states match step 4.
9. Console: no new error lines in the Console page since the launch time except known ones (compare with the previous APP_LOG entry).
10. Lite (only if rebuilt): start `pinguino-lite.exe` from its folder: the Dashboard shows the version, Parts card says "Up to date" or lists parts, Replays page opens. Quit it. No scan of a replay folder on this PC (Rocket League is on the gaming PC).
Result goes into APP_LOG; any fail stops the rest and goes to Ivan with the failing step number.
