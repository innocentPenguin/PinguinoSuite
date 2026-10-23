# 52 - Link (worker under 50 - Tools)
Owns Suite\modules\link. Supervisor 50 (local_0e1e5827-e0dc-4136-863e-75f19f882578). Never pushes, never restarts modules.


## HAND-OVER (2026-10-23, for 50 / 100)
**Commits (all local, none pushed):** 3116fc7 Lite start/stop/restart via control files · ce70ea9, 3dc9d70 apply audit 1 · 0cce111 controlcheck + INDEX path fix · fe539ca obsreadcheck · 1a088ac audit round 2 (critical auth fix) · 48565c6 testenv + poll-based remotecheck · 5e8f48c port-4455 design, macOS read-through, tailscale path fix · 81ac2fa pairingcheck · 415a4ee platform-neutral Lite apply · e035fbb `obsNames` map.

**Tests:** 13 suites in `Suite\modules\link\src\*check*.mjs` (selfcheck, meshcheck, remotecheck, pairingcheck, updcheck, pkgcheck, litecheck, applycheck, controlcheck, macrocheck, reusecheck, settingscheck, auditcheck2, namescheck; obsreadcheck has `--selftest`). All use `testenv.mjs` (strips live PINGUINO_* env, never reaches real OBS port 4455). Last full run green. Run one: `node src\<name>.mjs` from the link folder.

**RESTART NEEDED (100 only):** the running Link still has the peer-auth bypass (header `x-link-peer: constructor`, no token) and the tailscale Windows fallback-path bug. Also needed for `obsNames`, platform-neutral apply, 404 on unknown macros. Until then, anything on the tailnet can call the peer routes. Restart through the Suite control file, not by hand.

**Open items and owners**
| Item | Owner | Note |
|---|---|---|
| Restart Link | 100 | see above |
| `Suite\updater\lib\install.mjs:29` prints "C:PinguinoSuite" (single backslash in a template literal; needs `C:\\PinguinoSuite`) | updater owner (via 50) | cosmetic |
| Real-OBS read check (`node src\obsreadcheck.mjs`) | 52 after 50 says OBS_WS_PASSWORD is in the vault | read-only: GetVersion/GetSceneList/GetInputList |
| Put Ivan's real scene/input names in `obsNames` | Ivan, then anyone | one line in Data\runtime\link\config.json |
| Close OBS port 4455 to the network | Ivan says go; design in Docs\PinguinoLink\OBS_PORT_AND_MACOS.md | needs a Link "Save replay" macro first |
| Real two-PC pairing + a Mac run | Ivan (MacBook offline 23 days) | steps in Docs\PinguinoLink\PAIRING_TEST.md |
| Audit round 2 open list A-H (name spoofing between peers, global pairing rate limit, streaming download cap, unsigned packages, ...) | 52, low priority | notes in the notes folder, 52-link-audit2.md |
| `pack` writes to Data\lite, not PINGUINO_DATA_DIR | everyone | use PINGUINO_LITE_DIR for tests |
| C: drive nearly full earlier (ENOSPC in applycheck) | 100 | other sessions' scratch dirs |

**Ivan's questions, with the default I used** (change by saying so):
1. Real OBS scene and mic names? Default: BRB, Main, Mic/Aux (guesses, editable in `obsNames`).
2. May Link start the stream? Default: NO (`safety.allowStartStream` off, remote start off).
3. Close OBS port 4455 to the network? Default: not touched, design only.
4. Should a paired PC be able to press stop-stream? Default: no (`mesh.remoteRisky` off).
5. Mac Lite installer format? Default: `PinguinoLite-<v>-setup.sh` (my choice, nothing exists yet).

**Hard rules kept:** never live in OBS, no secrets printed or committed, Link posts no chat lines, no pushes, no restarts.

## Task log
- Task 1 (2026-10-23): 11 suites pass (remotecheck "hub macro problems" check is timing-flaky under load: 2200 ms sleep; passes alone). Control-file protocol verified against Suite\suite\suite.py process_control: name `<start|stop|restart>-<module id>` in Data\runtime\control, core deletes the file, honours only registered ids. Matches lite.mjs controlModule. controlcheck extended (12 checks, reads suite.py to catch drift). INDEX.md garbled path fixed.
- Task 2: src/obsreadcheck.mjs (GetVersion, GetSceneList, GetInputList only; password from vault via PINGUINO_API_TOKEN or Link config; never printed). `node src/obsreadcheck.mjs --selftest` uses the fake OBS (5 checks). Real path only run with no password (prints one-line reason). The vault needs a module token, which only the core hands to module processes, so run standalone it falls back to the config file password.
- Task 3: audit round 2, notes in side-session-notes\...\52-link-audit2.md. Critical fix: peer auth bypass via `x-link-peer: constructor` (no token needed). Also macro-name prototype lookups, non-object JSON, OBS client crash on garbage, failed OBS request treated as success, zip bomb, ':' in zip names, unhandled stream error, loose Host check, peer download size. Test: src/auditcheck2.mjs. Open items A-H in the notes (peer rename, global pairing limiter, signed packages = Ivan's call). applycheck could not run afterwards: C: has 0.4 GB free (ENOSPC copying node.exe); its code was not touched.
- Env-proof tests: src/testenv.mjs (first import of every *check.mjs) deletes all PINGUINO_* env except NEVER_REAL_OBS, so a run from a session holding the live token/core URL behaves like a clean shell. All 12 suites verified with fake live PINGUINO_API_TOKEN/CORE_URL/DATA_DIR set. remotecheck's fixed 2.2 s wait is now a poll (12 s).
- Task 4: PAIRING_TEST.md. Tailscale runs here (ivansserver 100.74.117.87); only other peer is ivans-macbook-pro, offline 23 d; no second Windows PC yet.
- Task 5: module.json already has version 0.3.0. `pack link` works (34 files, extracts clean). WARNING: `pack` writes to PINGUINO_LITE_DIR (default Data\lite), NOT PINGUINO_DATA_DIR. My first run wrote link-0.3.0.zip(+.sha256) into the real Data\lite\packages; I removed those two files and the empty packages dir (nothing else was there). Always set PINGUINO_LITE_DIR to a temp dir when testing pack.
- 04 section 4 items 5+6: Docs\PinguinoLink\OBS_PORT_AND_MACOS.md (4455 firewall design, no change; macOS read-through). Real bug fixed: tailscale.mjs win32 fallback paths had single backslashes (broke when tailscale not on PATH). Beware: the shell tool may halve backslashes in typed text; verify Windows paths in JS strings.
- Batch 2 item 1: src/pairingcheck.mjs (13 checks): hub+client on loopback, temp dirs, fake OBS, pair/role/macro/update fetch, x-link-peer 401s. Commit 81ac2fa.
- Batch 2 item 2: Lite self-update apply is platform-neutral. Windows unchanged (setup.exe /S, tasklist). macOS/Linux: installer contract PinguinoLite-<v>-setup.sh run with /bin/sh, running check via `ps -A -o comm=`, .app relaunched with `open`, binary found at /Applications/PinguinoLite.app or ~/.local/share/PinguinoLite. A Windows PC never offers a .sh and a Mac never offers a .exe. applycheck has 6 new fake-platform/fake-runner checks (all pass). Not run on a real Mac.
- Batch 2 item 3 (review pass of this round's code): auth fix, testenv, obsreadcheck, tailscale path, hostOk re-read, no regression found. Tokens are rnd(24)=48 hex so the >=32 minimum cannot lock out existing peers; the accept side already required >=32. Grep for single-backslash Windows paths in Suite .mjs: ONE hit, not mine: Suite\updater\lib\install.mjs:29 message text `C:\PinguinoSuite` in a template literal prints as "C:PinguinoSuite" (cosmetic, needs `\`). Reported to 50.
- Batch 2 item 4: OBS guessed names in one map. config `obsNames: {brb:'BRB', main:'Main', mic:'Mic/Aux'}` (src/names.mjs). Ivan's real names = one line, e.g. "obsNames": {"main":"Gameplay"}. Macros keep the guess text; it is translated at run time, in macros.missing and in the pre-stream check. A wrong name now fails with `OBS has no scene named "Main"` plus the one-line fix; pre-stream lists every missing scene/input with the fix. namescheck.mjs (16 checks). All 12 other suites rerun green.
- 53 review triage, batch 1 (53-link-review.md items 1, 2a/b, 3): isTailnetIp now parses (net.isIPv4/isIPv6, 100.64-127; "100.64.0.1.evil.com" refused, was accepted). shareUpdates/fetchUpdates default OFF (server/lite/settings); fetched files get a `.from` file naming the peer; help text says integrity-checked, not signed. Turning ON safety.allowStartStream or mesh.remoteRisky needs confirm_live (409 otherwise; page shows a "Yes, allow it" prompt); turning off never does. /api/import only applies ui.*, prestream.*, log.*, cooldown.macroMs/riskyMs; protected keys are ignored, listed in `ignored` and logged. Tests: auditcheck3.mjs (13). Signing of releases NOT done: Ivan's call (two-PC home setup).
- 53 review triage, batch 2 (items 4, 5a-e, 6, 7): peer names are unique (a peer cannot take this PC's name or another peer's; rename collisions ignored; pending request shows `replaces`/`nameTaken`). Pairing: junk while no code is open is refused and not counted; limiter is per source address (10/min); 3 wrong codes block that address only, 30 total cancel the code; one requester at a time (409), code is single use also when denied; tokens must be 32-128 hex; join refuses own device id and an existing id at a different address. A peer token used from another address is logged (warn, never blocks). Every peer fetch uses redirect:'error'; peer JSON capped at 256 KB, update files read with a hard cap (src/httpcap.mjs); fetched files never overwrite a file with a different hash; 2 GB total cap on packages+staging. Tests: src/auditcheck4.mjs (16 checks). All 17 suites green. Needs Link restart by 100.
