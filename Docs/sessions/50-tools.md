# Session notes: 50 - Tools (supervisor for Spotify, Link, Voice)

Session id local_0e1e5827-e0dc-4136-863e-75f19f882578, started 2026-10-23 05:30 CDT by 100 - Coordinator (local_32405a3a-974d-494b-8007-01272497ad35). Workers: 51 - Spotify, 52 - Link, 53 - Voice (proposal cards; the app refuses start_session from a session-driven turn, Ivan must click or say "start them"). Shared notes: `C:\Users\ivanm\AppData\Roaming\Claude\side-session-notes\local_32405a3a-974d-494b-8007-01272497ad35\50-tools-backlog.md` (live backlog, DONE-by-50 list that workers must read first).

## 1. What I did and why
- Read SESSIONS_STRUCTURE, music-spotify, 04-pinguinolink, 06-voice, SPOTIFY, IDEAS, COORDINATOR_HANDOFF and the module git log. Several brief "backlog" items were already built: Link 3116fc7 (Lite start/stop/restart; protocol verified against core `suite.py` process_control), Voice 26afe27 (!speak alias, routing design), Spotify mod queue commands / leaderboard / lyrics_on / fallback playlist. Reported this to 100 at 05:50 so the restart list is right.
- Wrote and committed (ae3dbfc) `Docs\SPOTIFY_CONNECT.md` (go-librespot as a module child process, `device_auth` login via spotify.com/pair so Ivan clicks nothing in a redirect, `/player/output` for runtime device switch, per-OS binary for the Mac, settings/endpoints/tests, routing steps for Ivan) and `Docs\VOICE_ROUTING.md` (bot voice on a Voicemeeter input, OBS Monitor and Output, fallback).
- Ivan 05:43: the Connect device must be "thru pinguinosuite" so it works on a Mac -> cross-platform design, no separate install.

## 2. Decisions and facts
- Audio on this PC: VB-Cable (CABLE Input / CABLE In 16ch) and Voicemeeter (Input, AUX, VAIO3, In 1-5) exist; nothing to install for routing.
- go-librespot v0.10.5 Windows exe + MinGW DLLs are in `Suite\modules\spotify\bin` (spike by the old Music session). Do not touch bin until Music reports the spike done.
- `python` on PATH in bash is an MSYS build: it mis-resolves `C:\` paths and `python -` hangs; use `Suite\.venv\Scripts\python.exe` or the Edit/Write tools.
- Stream was offline at 05:50 (decapi).

## 3. For the next session
- Rounds to 100: once per round, one message (done / needs restart / numbered questions with defaults / idle: N).
- Restarts pending (100 decides): link 3116fc7, voice 26afe27 (-NoBuild; Host re-reads the manifest for !speak).
- Waiting on: Music's spike report; Ivan's answers (OBS_WS_PASSWORD in vault, !speak name/price, output devices, hub role + real scene names).

## 4. Backlog by module (priority order)
Spotify: Connect device (connect.py, after spike) > audit round 2 > artist-exact ban by id > announce per tier > lyrics_toggle mod-action for Master View > lifetime/week leaderboard > manual real-flow tests (playlist add, YouTube link, lyrics overlay).
Link: run suites + obsreadcheck (read-only OBS test when the password exists) > audit round 2 > PAIRING_TEST.md + hub role steps > pack check > 4455 restriction design.
Voice: device matching (prefer WASAPI entry, dedupe) > audit rounds 2-3 > speech-intervals verification + Listen consumption check > !speak readiness + module.json version > next Speak items from 06-voice.md.
