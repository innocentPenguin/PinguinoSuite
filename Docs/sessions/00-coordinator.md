# Session notes: 00 Coordinator (Pinguino)

Last updated: 2026-10-23 05:10. Session id: local_32405a3a-974d-494b-8007-01272497ad35 (took over from local_9b055c40-005d-4fad-892a-7133e1382dd1 at 05:05). Full state and rules: `Docs\COORDINATOR_HANDOFF.md`. App history: `Docs\APP_LOG.md`. Ideas and Ivan's decisions: `Docs\IDEAS.md`.

## 1. What I did and why
- Only 00 builds, launches or restarts anything. Engines commit locally and queue a restart request with me; I check `https://decapi.me/twitch/uptime/innocentpenguin_` first and restart only what changed.
- 2026-10-23 05:01: full rebuild (Build-All, third attempt after a Host DLL lock) + launch + Listen restart; 05:08 Spotify module restart for Music's 035290b. All ports up (8760, 8770, 8765, 8766, 7777, 8771, 8772).
- Routed Ivan's decisions to the owning engines (see HANDOFF "Ivan's decisions"), kept APP_LOG and IDEAS current.

## 2. Decisions and failed attempts
- Rebuilds fail when a `dotnet PinguinoHost.dll` process still holds the DLL: kill by command line (not just by port) before Build-All.
- Modules sometimes survive a core kill as orphans and ignore the control stop file; Update-Module then cannot bind the port. Kill the orphan PID, rerun Update-Module.
- 02 runs a simulator Host from `%TEMP%\hostqi` (`--sim --no-sync --data %TEMP%\scd`); it is not the live Host, leave it alone.

## 3. For the next session
- Read HANDOFF, MEMORY.md, APP_LOG, IDEAS, then `Docs\sessions\*.md`. Message every engine with the new id before anything else.
- Verify-after-restart list: `!gamble !slots !duel/!accept !give !games !shop` one line each (use the Host simulator, not real chat), first/returning chatter sounds in Multi, Spotify channel playlist + YouTube link (Music's manual test steps in `music-spotify.md`), `scene.html?profile=h&preview=1`, `/api/economy/depreciation` dry run, site `/points`, `/mod/view` 403 when signed out.

## 4. Future plans, by priority
1. Combined "what Ivan must answer" list after each engine round (this file's section 6 + HANDOFF).
2. Held end-of-night 3x audit + 4-tier docs, only when Ivan says done.
3. Tell 01 to re-run `Installer\Build-Installer.bat` after the next Suite push.

## 5. Where my history lives
- Old transcript: `C:\Users\ivanm\.claude\projects\D--\7fc07e5a-9de1-4177-a16f-0a88b994dfed.jsonl` (grep it).
- Memory: `C:\Users\ivanm\.claude\projects\D--\memory\MEMORY.md`.
- Shared notes folder: `C:\Users\ivanm\AppData\Roaming\Claude\side-session-notes\local_9b055c40-005d-4fad-892a-7133e1382dd1`.

## 6. Things Ivan may be forgetting
See `README.md` in this folder: the combined list across all engines.
