# Session notes: 53 Voice (worker under 50 - Tools)

Last updated: 2026-10-23 08:50. Hand-over from the old 06 session: `Docs\sessions\06-voice.md`. Docs: `Docs\VOICE.md`, `Docs\VOICE_ROUTING.md` (Windows), `Docs\VOICE_MAC.md` (Mac).
Module: `Suite\modules\voice` (Speak, id voice, port 8772), version 0.9.0. Tests: `cd Suite\modules\voice` then `..\..\.venv\Scripts\python.exe -m unittest discover -s tests` -> 145 pass (temp data dir, fake player and fake synthesiser, no audio).

## What I built (commit hashes)
| Hash | What |
|---|---|
| 7844318 | `output.device` matching: case-insensitive substring, WASAPI > DirectSound > MME, de-duplicated stable device list; WASAPI plays with `auto_convert` (shared mode rejects 22.05 kHz). (Committed inside another session's commit through the shared index.) |
| c20416c | Audit rounds 2-3, 11 fixes: spoken numbers/names/commands cannot carry text, priority clamped 1..9, speech-interval race, history.jsonl rotation at 5 MB, 24-bit WAV rejected, message cap 2000 chars, non-dict JSON bodies. |
| d15ed20 | `!speak` readiness: Host sends role as a number ("3" mod, "4" broadcaster), now understood; `redeem: true` lets anyone through (channel-point paid); speech-interval tests; `version` in module.json; Docs\VOICE.md "!speak: what the Host needs". |
| cc1683c | Spoken mic-lost alert: event `mic_alert` (OFF by default), polls Listen `/api/status` every 10 s, speaks one fixed line per distinct alert, never Listen's text. |
| 7a2ee86 | Mac/Linux support: backends `Sapi` (Windows, unchanged), `MacSay` (`say`, aiff/wav to sounddevice), `Espeak`; chosen by `sys.platform`; the page shows "Voices come from: ..."; plain-language messages when no voice or no output device exists (voices, devices, preview, sound check, self-test). |
| 6b14a81 | Docs\VOICE_MAC.md (say voices, BlackHole 2ch/16ch routing, fallback, troubleshooting). |
| a370c17 | Third review of c20416c/d15ed20/cc1683c: no regressions. |
| 1d1932a | Read-only Routing check (`GET /api/routing-check` + button in the Output card; checks voice=Voicemeeter AUX Input, music=CABLE Input, and whether Play on resolves; plain fixes); spoken-name cleanup (emoji dropped, CamelCase split, xX decoration, trailing digits, all-emoji -> "someone", secrets scrubbed first; per-name override = the existing `nicknames` setting). |
| (this batch) | Fixes from 52's security review (`52-voice-review.md`): security headers + `frame-ancestors` on the page, exact local Origin match, `token_ok` fails closed without a token, sensitive GETs (history, history.csv, export, incidents, review reports, control, config) need the module token or the page's own same-origin request, 413 for bodies over 4 MB or chunked, 15 s socket timeout, secret filter (NFKC + invisible characters dropped, keyword swallows the next 6 words, spaced-out keywords, Discord-style tokens, PIN, 8+ digit runs and phone numbers), a spoken timeout can never be confirmed by voice and `require_confirm=false` never auto-runs a timeout, Windows device names (CON, NUL ...) cannot be file names for sounds/presets/backups, `control.jsonl` and `incidents.jsonl` rotate at 5 MB, `restore_backup` needs a real file. Tests: `tests/test_hardening53.py`. |
Also: read-only review of 51's Connect work (`53-connect-review.md` in 50's notes folder, 25 findings) and the update of Docs\SPOTIFY_CONNECT.md to match connect.py as built.

## Restart needs
- Voice needs ONE restart by 100 (`App\Update-Module.ps1 voice`) for everything above to take effect. Nothing was restarted or pushed by me. The master switch is OFF and stays OFF until Ivan turns it on.
- Behaviour to expect after the restart: the Windows speech path is unchanged; the Speak page gets the Routing check button, "Voices come from: Windows SAPI", and the hints; `mic_alert` stays off until enabled.

## Open items and owners
| Item | Owner |
|---|---|
| Listen should skip the bot's own voice: read `GET :8772/api/speech-intervals?since=<oldest queued segment epoch - 5>` (1 s timeout), drop or tag overlapping segments; Listen segment times are relative to `_t0`, so epoch = `_t0` + start/end. Request sent via 50. | 20-Suite (Listen) |
| Raid-by-voice (pending-confirm only) | 02, needs their endpoint |
| Core `/api/voice/dispatch` must also refuse obs/stream actions | 01 / core |
| Memory watchdog for VOD jobs; `listen.log` rotation (was 82 MB) | Listen / core |
| First live check on a real Mac (Sound check, then one Preview); Mac go-librespot binary | Ivan / 51 |
| Tune the hourly review on a real, supervised stream with the master ON | Ivan |
| Page token (52 finding 1) is DONE (commit after 457ffd9): `GET /` replaces `__TOKEN__` with the module token only for a direct loopback load (no proxy/forwarded headers, local Host); the page sends it as `X-Pinguino-Token`. The Suite shell frames `http://127.0.0.1:8772/` directly (App `modSrc`), so the embed gets the token. POSTs that change settings, speak, enable spoken control or call the cloud (`server.TOKEN_POST`) need it whenever the Suite token env is set; mute/stop/replay/preview/sound check stay same-origin as the safe fallback. Still open: a local program can fake same-origin headers on the sensitive GETs (the page also has to read them without a header for downloads such as history.csv). Needs a Voice restart by 100, then one look at the Speak page in the app. | 53 / 100 |
| `/api/chat-command` must require the module token (52 finding 2): 02 must send `Authorization: Bearer <module token>` on `module_command` first; then 53 removes it from OPEN_POST. Until then a local program can post a forged role/redeem. | 02 first, then 53 |
| Redeem bypass accepts JSON `true` only (string "true" would not); Host sends booleans today | Host (02), only if that changes |
| The 24 old `vod-*.mp4` files (~21 GB) in Listen's sources await Ivan's say-so | Ivan |

## Ivan's questions, with my defaults
1. Approved by Ivan: command `!speak` (alias `!tts` stays). 2. Approved by Ivan: price is a Host channel-point redeem of 100 points, anyone may use it once redeemed; typed in chat it is mod-only. (Set in the Host, not Speak.) 3. Is a second virtual cable for the voice OK: default yes, "Voicemeeter AUX Input" (fallback "CABLE In 16ch"), see VOICE_ROUTING.md. 4. Do one supervised test with the master ON before relying on it (never while live in OBS).

## Rules I follow
Never go live in OBS; the module never posts to chat itself (only the Host `say` endpoint); no secrets read aloud or logged; no pushes; no restarts; never flip the master switch; tests never play real audio or touch the real Data\runtime\voice.
