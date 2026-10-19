# Module Contract (v1)

How any Pinguino app (Bots, Multi, Link, Site helpers, future apps) plugs into PinguinoSuite.

## Registration
Either of:
1. `Suite/modules.json` – explicit list (current: `listen`).
2. Drop-in: `Suite/modules/<dir>/module.json` – discovered at core start. `cwd` defaults to `modules/<dir>`. `modules.json` wins on id clash.

## Manifest fields
| Field | Required | Meaning |
|---|---|---|
| `id` | yes | short unique id, used in URLs `/api/modules/{id}/...` |
| `name`, `desc` | yes | shown in the dashboard |
| `cmd` | yes | argv list; `{py}` expands to the core's Python |
| `cwd` | no | working dir relative to `Suite/` |
| `port`, `url`, `health` | for HTTP modules | core polls `url+health` for liveness |
| `on_live` / `on_offline` | no | `{"post": "/path"}` called when the stream goes live / offline |
| `defaults` | no | `enabled`, `start_with_suite`, `react_to_live` |

## `ui` block (optional): appear in the App with only a manifest
```json
"ui": { "nav": "Bots", "icon": "🤖", "section": "Modules", "path": "/", "order": 30, "replaces": "bots" }
```
| Field | Meaning |
|---|---|
| `nav` | sidebar label (default: `name`) |
| `icon` | emoji/char shown in the sidebar (default ▣) |
| `section` | sidebar group heading (default `Modules`) |
| `path` | page inside the module's `url` that the App embeds (default `/`) |
| `order` | sort key, lower first (default 100) |
| `replaces` | hides the matching *preview mock* (`voice`, `chat`, `bots`, `actions`) once the real module exists |

The core returns it as `modules[].ui` in `/api/state` (with `url`, `state`). The shell builds a nav entry and an embedded page per module with `ui`; if the module is not running it shows a Start button. No edit to `App/src/index.html` is ever needed. Requirements for the embedded page: serve it over HTTP on `127.0.0.1:<port>`, allow being framed by the App (do not send `X-Frame-Options: DENY`/`frame-ancestors 'none'`), and call your own API same-origin.

(Planned, not yet enforced: `version`, `deps`, `capabilities`, `config schema`, `restart policy`.)

## Security rules for modules
- Bind to `127.0.0.1` only.
- The core passes `PINGUINO_API_TOKEN` (planned: per-module token) and `PINGUINO_DATA_DIR` in the environment. Modules must require the token on state-changing endpoints and reject foreign `Origin`s.

## Core API (all `/api/*` need `Authorization: Bearer <token>` or `X-Pinguino-Token`)
`GET /api/capabilities`, `GET /api/state`, `POST /api/modules/{id}/{start|stop|restart|options}`, `POST /api/channel`, `POST /api/simulate`, `POST /api/windows-autostart`, `POST /api/quit`, `WS /ws?token=…` (events `{type, ts, …}`).
Requests with a wrong `Host` or a non-allowed `Origin` get 403 (anti DNS-rebinding / drive-by pages).
Allowed origins: the core itself and the Tauri webview (`tauri://localhost`, `http(s)://tauri.localhost`).

## Platform capabilities
Anything OS-specific is optional. `GET /api/capabilities` reports what exists. The Tauri shell provides tray, single-instance and autostart on Windows/macOS/Linux; the legacy HKCU Run key is only the standalone-Python path.

## Status (2026-10-19)
`PINGUINO_API_TOKEN` is now passed to modules and sent on core->module hook calls. Listen enforces it (Host/Origin guard + token for non-browser writes). Link (Unit 04) is registered but must adopt the same rule. Per-module tokens are in place (HMAC of the core token per module id).

## What needs a rebuild (rule)
| You changed | Do |
|---|---|
| Module code (Multi, Listen, Link, Host, any `Suite/modules/*`) | Restart **only that module** from the app (or `POST /api/modules/{id}/restart`). No app rebuild. |
| `Suite/suite/*.py` or `Suite/modules.json` | Rebuild the core sidecar: `App\Rebuild-App.bat` (freezes only if those files are newer than `pinguino-core.exe`). |
| `App/src`, `App/src-tauri/src`, `tauri.conf.json` | `App\Rebuild-App.bat` (rebuilds only the shell, `--no-bundle`). |
| Nothing under those | The script reports "up to date" and you just relaunch. |
`Rebuild-App.bat --installer` also builds the NSIS setup; `--force` rebuilds everything. Only session 00 runs it.

## Updating one module without restarting the app
`App\Update-Module.bat <id> [-NoBuild]` stops that module, runs its manifest `build` command if it has one (Host: `dotnet build`, which needs the DLL unlocked, hence the stop first), starts it again and waits until its health URL answers. The app and the other modules are never touched.
It talks to the core through a file-drop folder, so no API token is needed: the core polls `Data\runtime\control\` every second and consumes files named `start-<id>`, `stop-<id>` or `restart-<id>` (only registered module ids). Anyone who can write to `Data\runtime` can do this, which is the same trust level as the data itself. Needs a core that includes this feature (after the next core rebuild).
Manifest field: `"build": ["cmd", "arg", ...]`, run in the module's `cwd`.
