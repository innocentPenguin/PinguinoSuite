# 10 — Suite Integration (Windows + macOS)

Status: DONE 2026-10-19. Scope: make `Suite\modules\link` loadable by the Suite core under MODULE_CONTRACT v1. This is NOT the M2 hub agent.

## Registration
Drop-in manifest `Suite\modules\link\module.json` (id `link`, port 7777, health `/api/health`, cmd `node src/cli.mjs serve`, cwd `modules/link`). Defaults: enabled, **start_with_suite false**, react_to_live false (nothing starts or reacts until the user opts in from the Suite). Requires `node` >= 22 on PATH for the Suite process.

## Contract compliance
| Requirement | How |
|---|---|
| 127.0.0.1 only | Loopback always; tailnet IP added only when Tailscale is Running (re-checked every 15 s). Never 0.0.0.0. Loopback bind failure exits 1. |
| Token on state-changing/data endpoints | Required on loopback too (fixes inventory finding 1). Accepts module token and the core's `PINGUINO_API_TOKEN`. Constant-time compare. |
| Reject foreign Origin | 403 if Origin present and not same host. |
| DNS rebinding | Host must be IP literal, localhost, or tailnet name; else 421. |
| Health | `GET /api/health` is unauthenticated, secret-free, no Tailscale call (fits the 1.5 s poll). |
| Port override | `PINGUINO_LINK_PORT`. |

Loopback dashboard page gets the token injected (same-origin only). `PINGUINO_DATA_DIR` is not used: config stays in `~/.pinguinolink` by user decision.

## Cross-platform
`tailscale.mjs` resolves the CLI from PATH, then `C:\Program Files\Tailscale\tailscale.exe`, `/Applications/Tailscale.app/Contents/MacOS/Tailscale`, Homebrew paths. Works with Tailscale or OBS absent (status reports the error; service still runs).

## Verified (Windows, this PC, port 7791 test run)
health 200 · status no token 401 · wrong token 401 · module token 200 · core token 200 · loopback POST without token 401 · foreign Origin 403 · rebinding Host 421 · page 200 · syntax check on all modules passes.

## Verified through the real Suite core (Windows, `.venv`)
`suite.modules['link']` discovered from the drop-in manifest; `Module.start()` spawned it; the core's own `_ping()` (1.5 s timeout) reported healthy after 1 s; `stop()` killed it and the port went dead. Log: `Suite\logs\link.log`.

## Not verified
macOS run (no Mac here; paths and code are platform-neutral but untested; the core's non-Windows spawn path `start_new_session` is also unexercised); Tailscale-bound listener (Tailscale is Stopped); real OBS macros.

## macOS: what static evidence exists (2026-10-19) and what is left
- Simulated darwin path: with `os.platform()` forced to `darwin` and `tailscale` not on PATH, `resolveBin()` picks `/Applications/Tailscale.app/Contents/MacOS/Tailscale`.
- Source scan: all Windows-specific code (`winget`, `powershell Restart-Service`, `shell:` flag) sits behind `os.platform() === 'win32'`; paths use `path.join`/`os.homedir()`; no `.exe`, drive letters or backslashes outside the Windows candidate list.
- Server code uses only portable Node APIs (http, crypto, child_process).
- **Still open — needs the MacBook:** run the module through the Suite core there (its POSIX `start_new_session` spawn) and `curl http://127.0.0.1:7777/api/health`. Checklist: Node >= 22 on PATH, Suite checked out, `module.json` picked up, health 200, no-token POST 401, Tailscale app detected by `status`.

## One-command check (Mac or Windows)
`cd Suite/modules/link && node src/selfcheck.mjs` — starts the server on a spare port and runs the health/token/Origin checks; exit code 0 = pass. Passed on Windows 2026-10-19. Run it on the MacBook, then start the module from the Suite and confirm it shows healthy; that closes the macOS item.

## Windows optimisation (2026-10-19; Mac deferred by user)
`tailscale.status()` is cached 3 s and de-duplicated, so the dashboard's 5 s poll no longer spawns `tailscale.exe` on every request (cold 90 ms, cached 0 ms). `node` resolves at `C:\Program Files\nodejs\node.exe` on PATH. selfcheck still passes. Mac work is deferred until the MacBook is available.
