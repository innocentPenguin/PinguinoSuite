# 02 PinguinoBots engine report, 2026-10-21 (Phase 3)

## Audit round 1 (Host + Core, run 14:15 CDT on a fresh build)
- All 60 Host test scripts except test-host-obs (excluded on purpose: OBS) ended with no FAIL line. Core suite: ALL BOT CHECKS PASSED. `sync-shared --check` clean.
- No new code in this round; nothing to fix. Rounds 2 and 3 with the forks (Helper, Chatty, B0t) are still open because messaging between sessions was paused (rate limit, resets when Ivan types in session 02).
- A test of mine had left `PinguinoB0t/overlays/zz_test.html` (`<html></html>`) in the real overlays folder; removed, and the test now uses a temp overlay dir.

## New since the last report (all committed locally, none pushed)
- 75349e9, 87df037: `GET /api/eventlog?kind=chat|players|backend` (+ SSE `playerlog`, `backendlog`): structured, backfilled logs for the Master View.
- 046d1eb: song refunds (rejected/skipped song returns the viewer's channel-points redeem). Needs the `spotify-redeem` preset enabled.
- 269b61a: `GET /api/commands/all` (unfiltered). 6bef2b7: site bridge long poll + commands-all push (site answers 404 until its batch is deployed; expected).
- 79c87d1: bare "pinguino(s)/penguino(s)/penguins" count as a bot call. 8a596df: wheel overlay flicker/pixelation.
- e3adc12: welcome bonus (100 points, 45 s). Strike limit tunable (d213195).
- Data change: `ixsamux` aliased into `ixsamuu` (Data/boards/aliases.json, backup next to it).

## Known issues / open
- test-host-obs: "ban alert was not shown" (pre-existing, mock OBS).
- Login-button failures: waiting for the exact error text.
- Overlay assistant is off (no Data/config/overlaychat.json).
- Streamer re-sign-in on Host /setup is needed for `moderator:read:chatters`.
- Held 3x audit rounds 2 and 3 and 4-tier docs: pending.

## Hard rules kept
No OBS go-live or stream tests, no site push, no deletions of user data, no duplicate bot messages from new code.
