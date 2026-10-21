# PinguinoLink INDEX
Code: `Suite/modules/link/` (Node >=22, no deps, port 7777). Docs: this folder. Owner: session 04.

## Source map (`Suite/modules/link/src/`)
| File | What | Key parts (line) |
|---|---|---|
| server.mjs | HTTP server, all routes | runMacro 18, readJson 50, tokenOk 65, hostOk 75, serve 82; peer routes 124-135 before the token check; token-gated /api/* from 142 |
| mesh.mjs | Device mesh, Tailscale-only | createMesh 52; addressing 133, pairing 144, peer messages 208, status 264 |
| obs.mjs | obs-websocket v5 client | runRequests, getData, obsState (2 s cache), forgetState, diagnoseObs |
| macros.mjs | Macro editor model, allow-list of actions | KINDS 7, set, remove, move, missing, exportAll/importAll |
| settings.mjs | Settings schema, validation, reset | SCHEMA 10, view, apply (role change needs confirm_role) |
| prestream.mjs | Pre-stream report items | prestream 8 |
| vault.mjs | OBS password from core key vault | secret, obsConn |
| config.mjs / log.mjs / tailscale.mjs / doctor.mjs / cli.mjs | config dir, JSONL console log, Tailscale status, doctor, CLI | |
| page.html | Dashboard UI | served by GET / |
| *check.mjs, fakeobs.mjs | Tests (fake OBS): selfcheck, meshcheck, macrocheck, settingscheck, remotecheck | run with `node src/<name>.mjs` |

## Docs
00-CHARTER, 01..09 planning set, 10-SUITE-INTEGRATION (Tauri embedding, personalisation), 11-DEVICE-MESH (pairing plan), SESSIONS.

## Rules that shape the code
Tailscale only; no custom VPN/crypto; no remote shell; no key injection; risky actions (start/stop stream) need confirmation and a guard; role/hub changes need a visible confirm; Link posts no chat lines (if it ever does: only via Host say endpoint).

## PinguinoLite update pipeline (local only, decided by Ivan)
Source of truth: `Data\lite\packages\<id>-<ver>.zip` (+ `.sha256`) and `Data\lite\staging\PinguinoLite-<ver>-setup.exe` (+ `.sha256`) on the update-host PC.
Other PCs pull them over the Tailscale mesh from paired PCs (`/api/mesh/updates/list|get`, peer-auth only), on "Check for updates" and every 5 min, hash-verified. Settings: Devices > share / fetch updates.
Make a package on the update host: `node Suite/modules/link/src/cli.mjs pack <module-id>` (module.json needs "version"; data/ and db/log files are left out). Code: lite.mjs (contract, sync, sharing), pkg.mjs (zip, pack, install, rollback). Tests: litecheck, pkgcheck, updcheck. Nothing installs or runs without a click; Lite self-update apply is not built.

## Going live is off by default
Setting `safety.allowStartStream` (Settings > Buttons and safety) is OFF. While off, `runMacro` and `runRequests` (obs.mjs) refuse StartStream/ToggleStream with 403 for every caller: dashboard, Stream Deck CLI, paired devices, any future timer or voice. Stop, BRB and scene macros are unaffected. The default `start` macro was removed from new configs. Tests: macrocheck and remotecheck.

## Lite self-update apply (Ivan approved 2026-10-21)
Only after the user clicks Update in Lite: Lite writes `selfupdate-apply` and exits (killing Link). `lite.mjs applyLiteUpdate` first re-verifies the staged installer (hash vs .sha256), finds the running PinguinoLite.exe (or %LOCALAPPDATA%\PinguinoLite), writes `lite_apply_job.json` and starts the detached helper `applyupdate.mjs`, which: waits up to 90 s for Lite to close (never kills it), re-checks the hash, copies the install folder to `Data\lite\backup\lite-<ver>-<stamp>`, runs `<setup>.exe /S`, relaunches Lite. If the installer fails the backup is copied back and the old Lite relaunched. Result in `lite_apply_result.json` (+ `lite_apply.log`); the next Link start reports it in update_status.json. Test: `applycheck.mjs` (fake installer, never runs a real one).
