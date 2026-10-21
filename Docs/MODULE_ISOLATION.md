# Module isolation: modules must not die together

Owner: 01 (Core). Requested by Ivan via 00: "the modules are supposed to be segregated to run without each other. Dependencies are fine but they shouldn't go down all together."
Scope of this change: core supervisor (`Suite/suite/suite.py`) and the Tauri shell exit path (`App/src-tauri/src/main.rs`). Host-side lease handling is 02's.

## What dies with what today (evidence)

| Event | What happens | Where |
|---|---|---|
| App shell closed / restarted (Tauri `RunEvent::Exit`) | `stop_core` POSTs `/api/quit`, waits 0.5 s, then `child.kill()` on the core | `main.rs` `stop_core`, line ~121 and the Exit handler |
| `POST /api/quit` or tray "Quit (stops all modules)" | `_shutdown()` calls `m.stop()` on EVERY module, then `os._exit(0)` | `suite.py` `_shutdown` |
| `Module.stop()` | `kill_tree` = `taskkill /F /T /PID` on the module and its children | `suite.py` `kill_tree` |
| Core restarted while modules are running | `start()` sees `_ping()` ok and returns early. The module is never marked `wanted` and never gets a handle, so (a) a later crash is never restarted by the new core, and (b) the Stop button cannot stop it (`self.proc` is None, nothing is killed) | `Module.start`, `Module.stop` |
| Core crashes (not a clean quit) | Modules are plain child processes with `CREATE_NEW_PROCESS_GROUP` only, no job object, so they usually survive. They are then orphans nobody supervises (same early return above) | `Module.start` Popen flags |
| One module crashes | `supervise()` restarts only that module (backoff 2/5/15/30/60 s, gives up after 5 crashes in 5 min). Other modules are not touched. This part is already isolated | `Module.supervise` |
| Update-Module / Build-All | `Update-Module.ps1` talks to the control folder and stops/starts ONE module. It does not stop the app. Build-All does not call stop on the core | `App/Update-Module.ps1` |
| Rebuilding the app shell | Quitting the shell goes through `/api/quit`, so every module stops (the row above) | |
| Sidebar | If the core is unreachable the whole module list is shown offline, even for modules that are still running | `App/src/index.html` (`load`/`S`) |

Root cause: the shell and the core treat "close the app" as "stop the whole suite", and a restarted core cannot take back modules that are already running.

## Design

1. **Quit leaves modules running by default.**
   - `POST /api/quit` takes `?modules=stop` (or JSON `{"stop_modules": true}`) to stop them. Without it the core only exits itself.
   - Tauri exit calls `/api/quit` without it. The tray menu gets two items: "Quit (modules keep running)" and "Quit and stop all modules". The core's own tray (headless-less fallback) gets the same two.
   - The shell's per-module Stop buttons stay as they are (explicit, per module).
2. **Adopt running modules on core start.**
   - `Module.start()` on a module that already answers its health URL now marks it `wanted`, `adopted`, records its pid (pid file `Data/runtime/pids/<id>.json`, falling back to the listening pid of its port) and returns. No second copy is started.
   - `stop()` on an adopted module kills that pid tree, but only after confirming the pid still owns the module's port (never kill a stranger).
   - A wanted module that stops answering is restarted by `refresh()` with the same crash accounting as before (5 crashes in 5 minutes = `failed`, start it manually).
3. **Detached spawn.** Modules start with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB` (falls back without breakaway if the parent job forbids it) so closing the shell or the core's console never takes them with it. POSIX already uses `start_new_session`.
4. **One module never takes another down.** The supervisor already restarts only the crashed module. New: restarts of adopted modules use the same per-module backoff and `failed` state; nothing in the supervisor loops over "all modules" except explicit user actions (Stop all, which is its own button).
5. **Sidebar independence.** The shell keeps the last known module list when the core does not answer, and for each module probes its own port directly (no-cors fetch of its health URL). A module is shown `running` if its own port answers, even while the core is restarting. A core outage shows one small "core restarting" chip instead of every module going offline.
6. **Dependencies.** A module that needs another (e.g. Chatty needs Host, Voice needs Listen) must show degraded and retry, never exit. Rule for module authors, added to `Docs/MODULE_CONTRACT.md`: do not `exit` because a peer is down; keep the process up, report `degraded` in the health payload and retry with backoff. A grep of `Suite/modules` and `PinguinoHost` for `sys.exit`, `process.exit` and `Environment.Exit` found no module that exits because a peer is down. The only exits are bind failures in Link (port already taken: correct), test scripts, and Host's lease handover (`HostLease.cs`, 02's change).

## Out of scope (owned elsewhere)
- Host lease change when this device loses master: 02.
- Per-module dependency fixes inside Listen, Multi, Link, Spotify, Voice and Host code: their owners (list below).

## Test plan (no restarts of Ivan's live app)
- Core unit tests with fake `Module`s on a temp port: `start()` adopts a live module; `stop()` refuses a pid that does not own the port; `_shutdown(stop_modules=False)` leaves modules; `quit` default; crash of an adopted module triggers one restart with backoff and does not touch the others.
- Shell render harness: core down + module port answering shows that module as running.
- The Tauri change and the supervisor change are only exercised for real in 00's single rebuild.

## Status
Implemented (commit hashes in the READY message): supervisor adopt/stop/restart, quit default, tray menus (core + Tauri), shell module probing while the core is away, `tests/test_isolation.py` (7 tests with the existing supervisor test). Needs the single rebuild to take effect: `suite.py` (frozen core) and `main.rs` (shell) and `index.html`.
