# 01 — Prototype Inventory (verified 2026-10-19)

Location: `Suite\modules\link` — `cli.mjs, config.mjs, doctor.mjs, obs.mjs, server.mjs, tailscale.mjs, package.json` (pinguinolink 0.1.0, Node >=22). Byte-identical to the backup copy in `D:\PinguinoBackup\2026-10-19-pre-reorg\...\PinguinoLink`.

## What each file does (read from code)
- `cli.mjs`: commands setup, status, serve, macro, send, receive, doctor.
- `config.mjs`: `~/.pinguinolink/config.json`; role, hub name, port 7777, random shared token, inbox, OBS 127.0.0.1:4455, 5 macros (brb, live, start, stop, mute).
- `tailscale.mjs`: install (winget/brew/curl), up, status (direct = `CurAddr` present), ping, Taildrop send/receive, netcheck.
- `obs.mjs`: minimal obs-websocket v5 client (SHA256 auth, sequential requests, 5 s timeout).
- `server.mjs`: hub runs macros against OBS; clients POST `/api/macro/<name>` with `x-link-token`; minimal HTML page; binds loopback + Tailscale IP.
- `doctor.mjs`: checks Tailscale/hub/OBS; on failure sends a redacted bundle to `claude -p`, which may only pick from a fixed fix whitelist; each fix needs y/N.

## Verified
- All 6 files pass `node --check` (Node 24.22).
- Tailscale 1.104.1 installed here; state **Stopped** (no tailnet).
- `tailscale netcheck`: UDP OK, IPv4 only, nearest DERP Chicago 17 ms, mapping not destination-dependent (good for direct paths).
- OBS installed; obs-websocket enabled on 4455 with auth; scene collections Base, Main.
- Config exists: role `client`, hub `streaming-pc`.

## Not verified / absent
Any peer connectivity (MacBook not enrolled), live OBS control (macro scene/input names are guesses), Taildrop transfers, server on tailnet, doctor run, any video transport, any tests. Module is not in `Suite\modules.json`, so the Suite does not launch it. This PC is configured as client; the OBS side needs hub role.

## Findings (record only — no changes yet)
1. Loopback skips the token; a local web page can blind-POST `/api/macro/stop`. Needs token + Host/Origin checks everywhere.
2. Single shared static token: no per-device identity, scopes, expiry, revocation, audit; plaintext (0600 is a no-op on Windows); non-constant-time compare.
3. Stop/start stream macros have no risk tier or confirmation.
4. OBS WebSocket listens on all interfaces; nothing firewalls 4455.
5. Doctor bundle includes netcheck output (public IP) — redaction must be allow-list based.
6. Taildrop only: no verification, queue, or resume guarantees.
7. Speedify tunnel adapter present; may affect routing/MTU — test on/off.
8. OBS password sits in OBS's own config; the hub agent must read it locally and never forward it.
9. `direct` is inferred only from `CurAddr`.
10. No WoL, no real dashboard, no Stream Deck integration, no idempotency/dedupe.
