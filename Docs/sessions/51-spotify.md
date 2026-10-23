# 51 - Spotify (worker under 50 - Tools), notes
Started 2026-10-23 05:50 CDT. Phase A = docs only, no edits under Suite\modules\spotify until 50 says "spike done, go".

## Phase A status (2026-10-23 06:20)
1. DONE SPOTIFY_CONNECT.md reviewed (50 wrote it). Added section 9 "To verify in the spike": exe build 90a4fdaf has /auth/code, /player/output, /player/volume, audio_device; NOT confirmed: literal `device_auth` value (spike ran `interactive`; fallback = parse the login URL from the log) and what `audio_device` means for WASAPI.
2. DONE Routing steps for Ivan = section 8 of the same doc (checked against Docs\IDEAS #24).
3. DONE Audit round 2: 28 findings in the shared notes folder (51-spotify-audit2.md). Top: site_bridge spin loop on unexpected exceptions (1,2), lyrics 404 not cached (4), store.load overwrite-after-corrupt (5,6), blocklist non-string crash (7).
4. DONE SPOTIFY_NEXT.md (a artist-id ban, b announce per tier, c week/month leaderboard, d lyrics_toggle).

## Phase B plan (waiting for "spike done, go")
connect.py + tests per SPOTIFY_CONNECT.md, then audit fixes 1,2,4,5,6,7,12,14,9, then Phase-4 items in 50's order, then manual playlist-add + YouTube-link tests.

## Pitfalls noted
- Python files are CRLF: patch with Edit or small Python scripts. Heredocs with backslash-n mangle strings.
- Never port 8799 in tests; never restart modules (needs restart: spotify -> tell 50).
