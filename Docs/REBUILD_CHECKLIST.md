# Rebuild / restart checklist for 100

Written 2026-10-23 by 21-Lite; snapshot regenerated 2026-10-30. Only 100 launches or rebuilds (single-launcher rule). Nothing here was run by me.

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

## Snapshot (generated 2026-10-30 by `Rebuild-Plan.mjs --md`; regenerate before relying on it)
### Shell rebuild (Tauri app): 0 commits
- since 2026-10-31T01:38:07.660Z (App/src-tauri/target/release/pinguino-suite.exe)

### Core rebuild (frozen Python): 1 commit
- since 2026-10-27T14:49:33.459Z (App/src-tauri/binaries/pinguino-core.exe)
- do: App\Build-All.bat --only core --force   (Build-All may say "up to date" and skip: Stale.ps1 only compares times, so force it)
- `2bf7327` Listen: HLS/ffmpeg download falls back once to a progressive format; timestamps in listen.log. Core: Data/runtime/status.json with starts/downs/miss counts. Tests added.

### Host rebuild (dotnet): 5 commits
- since 2026-10-31T03:34:36.317Z (PinguinoHost/bin/Release/net8.0/PinguinoHost.dll)
- do: App\Build-All.bat --only host
- `5ef21d3` Watchdog: nested Begin/End keep the outer op (a stack via Parent), so an inner End no longer clears the outer step marker; test added, lock-wait check made race-free
- `1e2702a` /api/account/streamer missingText: the count and the first 3 scopes (the full list stays in the missing array)
- `7f3d6eb` Seeds written while the Host runs: a pushups.json / redeem_counts.json newer than the Host's own last read or write is read again (never overwritten); POST /api/seeds/reload reads both now
- `1fbc1f5` Chat sends: a YouTube/TikTok viewer with no remembered name is @friend, never the yt: key or their bare channel id
- `3b1a9d0` Lore answers: @name on every public reply (bare words too), YouTube/TikTok viewers by display name, never the yt:/tt: key

### Module restart (Listen, Multi, Link, Spotify, Voice): 4 commits
- since 2026-10-31T01:38:07.660Z (App/src-tauri/target/release/pinguino-suite.exe)
- do: App\Update-Module.bat <id>  (listen first; or restart the whole app)
- `2bf7327` Listen: HLS/ffmpeg download falls back once to a progressive format; timestamps in listen.log. Core: Data/runtime/status.json with starts/downs/miss counts. Tests added.
- `cf3388b` spotify: address the viewer in !song idle and skip-nothing replies
- `49636e2` Multi alerts: Host activity feed outage tracking (one warning, recovery line, counters)
- `53e79d9` spotify: name a run of HTTP 403s (log, selfcheck, chat) and let the Host's live hooks through

### Lite rebuild (PinguinoLite, Tauri): 0 commits
- since 2026-10-24T03:15:10.391Z (PinguinoLite/src-tauri/target/release/pinguino-lite.exe)

### No rebuild (Node, site, docs, tests, installer tools): 807
Docs 203, Suite 179, PinguinoHost 140, App 86, PinguinoB0t 80, Tools 39, PinguinoChat 24, HelperPinguino 22, PinguinoLite 14, Tests 8, .gitignore 5, Installer 4, PinguinoApp 2, Pipeline 1   (--all lists them)
### Order
1. Tell Ivan, and check that the stream is OFFLINE (GET /api/live on 8770 must say false). Never rebuild while live.
2. Quit the app from the tray (Quit), so the exe, the core and the Host DLL are not locked.
3. Host: App\Build-All.bat --only host
4. Core: App\Build-All.bat --only core --force
5. Launch with PinguinoApp.bat (or Build-All.bat with no flags builds the stale pieces and launches).

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
7. OBS overlays: `node Tests\overlay-smoke\overlay-smoke.mjs` (GET only, never touches OBS) must say PASS: it checks every Host overlay page, `/obs/alerts`, `/obs/goal` and the module pages for 200, no undefined/NaN/[object Object]/raw yt:/tt: keys, missing assets and bad state JSON.
8. Problem reports page: "Run the morning check" (read-only self-check) is all green or explains itself; module states match step 4.
9. Console: no new error lines in the Console page since the launch time except known ones (compare with the previous APP_LOG entry).
10. Lite (only if rebuilt): start `pinguino-lite.exe` from its folder: the Dashboard shows the version, Parts card says "Up to date" or lists parts, Replays page opens. Quit it. No scan of a replay folder on this PC (Rocket League is on the gaming PC).
Result goes into APP_LOG; any fail stops the rest and goes to Ivan with the failing step number.
