# 01 Core + Suite app report, 2026-10-22 (Phase 3, updated-only)

All commits are local, unbuilt and not seen live. No push, no OBS, no stream, no user data deleted.

## Changed since the last report
- Installer and PinguinoUpdater (7677c85, d4e2243, 209d200): sha256 + backup + rollback library, git/network/local sources, optional Ed25519 manifest signing, launch hook (`updater launch`, wired into PinguinoApp.bat, silent no-op without an `install.json` source), std-only rustc exes (`Suite/updater/exe/Build-Exes.bat`), Penguino-styled installer window (HTA). 25 node tests in temp dirs.
- Module isolation (dde8a9d, design `Docs/MODULE_ISOLATION.md`): quitting the app or the core leaves modules running (only "Quit and stop all modules" stops them); a restarted core adopts running modules; detached spawn; Stop kills only the port owner; the shell judges each module by its own port while the core is away.
- Module secrets persist across core restarts (957b5ec): they were derived from the per-launch core token, so any module that outlived a core got "unauthorized" on the on_start hook. They now come from `Data/runtime/module_secret`.
- Settings page: Sounds and Replays card (565e4e6). Sources page (d1f0413), `/assets/*` route and log rotation (2a21da3), read-only `/api/update/status`. Sidebar header "Suite" in accent orange (ea22b6f).
- Core tests: 69 pass. `cargo check` of the shell passes.

## Listen log review (00's questions)
1. "port 8765 held by a process that does not answer" (23x), crashes (exit 3), "unauthorized" (15x): the last crash entry is 2026-10-20 08:40 and the last "port held" entry is 2026-10-21 08:54, so nothing recent. These match 00's earlier finding (a stray listener on 8765 plus an ingest crash loop, both fixed). The "unauthorized" part has a real cause that is fixed in 957b5ec (token changed with every core launch). The "port held" message appears when the health check is not OK (slow or erroring) while the port accepts connections; it is a guard against double-starting, working as designed.
2. `Suite/logs/listen.log` (82 MB): cannot be moved while a running Listen still holds it open (Windows "busy"). Nothing was deleted. It is rotated at the next Listen start (the core rotates logs over 5 MB into `.1`), or move it to `Suite/logs/Archive` after 00's batch restart. Most of its content is yt-dlp download progress and asyncio ConnectionResetError traces from the old ingest loop.
3. Ownership: Listen the module stays with 01 (Core/shell lead and Listen module owner); 06 owns Voice and the ingest pipeline fixes. Docs/INDEX.md's Voice section listing should say "Voice (06); Listen host module (01)". I did not edit INDEX for that.

## New capabilities
Updates from a folder/USB/https/git source with rollback; modules survive app restarts; Sounds/Replays controls in Settings.

## Known issues
- Everything above needs the single shell + core rebuild; after it, modules started by the previous core keep their old-derived secret until they restart once.
- Installer window not opened (no GUI launched by design).
- Timers tab still waits on Host endpoints from 02. Economy depreciation/loans UI is not built (optional, 02 FYI).

## Future plans
Release hosting URL, repo visibility and signing key from Ivan; Economy page controls if 00 wants them; end-of-night audit and 4-tier docs stay held until Ivan says done.
