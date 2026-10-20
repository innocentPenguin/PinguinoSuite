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
