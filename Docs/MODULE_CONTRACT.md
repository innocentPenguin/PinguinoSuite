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

## Console logging (any module, no token)
The app has a **Console** page showing one live stream from the core and every module. A module logs by appending JSON lines to a file; the core tails it (same idea as the control folder).

**File:** `<PINGUINO_DATA_DIR>\console\<module id>.jsonl` (the core sets `PINGUINO_DATA_DIR` in every module's environment; default `Data\runtime`). One file per module; the file name stem IS the module id (the core ignores the `module` field and uses the stem). Create the folder if missing.

**Line (UTF-8, one JSON object per line, newline-terminated, under 8 KB):**
```json
{"ts": 1792417685.31, "module": "host", "level": "warn", "source": "twitch", "msg": "chat reconnecting (attempt 3)"}
```
| Field | Meaning |
|---|---|
| `ts` | epoch seconds (float) **or** ISO-8601 UTC string. Missing/invalid = time the core read it |
| `module` | your module id (informational) |
| `level` | `debug` \| `info` \| `warn` \| `error` (anything else = `info`) |
| `source` | sub-area inside the module (`twitch`, `obs`, `eventsub`, `bot:chat`...) free text |
| `msg` | the message, max 2000 chars (longer is cut). **Never log tokens, keys or passwords.** |

**Rules:** append-only; open, write one whole line, close (do not hold the file open, do not rewrite or truncate it). The core rotates the file at 2 MB (`.jsonl` -> `.jsonl.1` -> `.2` -> `.3`); if your write fails because of that, retry once. Do not log in hot loops: errors, state changes and important events, not every message. The core also captures your stdout/stderr (`Suite\logs\<id>.log`) and shows lines that look like errors/tracebacks as `source: "stdout"`, so crashes show up even if you never log.

**Snippets** (copy as is):
```python
# Python
import json, os, time
def clog(level, msg, source="", module="MYID"):
    d = os.path.join(os.environ.get("PINGUINO_DATA_DIR", ""), "console")
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, module + ".jsonl"), "a", encoding="utf8") as f:
            f.write(json.dumps({"ts": time.time(), "module": module, "level": level, "source": source, "msg": str(msg)[:2000]}) + "\n")
    except OSError:
        pass
```
```js
// Node (ESM)
import fs from 'node:fs'; import path from 'node:path';
export function clog(level, msg, source = '', module = 'MYID') {
  try {
    const d = path.join(process.env.PINGUINO_DATA_DIR || '', 'console'); fs.mkdirSync(d, { recursive: true });
    fs.appendFileSync(path.join(d, module + '.jsonl'), JSON.stringify({ ts: Date.now() / 1000, module, level, source, msg: String(msg).slice(0, 2000) }) + '\n');
  } catch {}
}
```
```csharp
// C# (.NET 8)
static void CLog(string level, string msg, string source = "", string module = "MYID") {
  try {
    var d = Path.Combine(Environment.GetEnvironmentVariable("PINGUINO_DATA_DIR") ?? "", "console"); Directory.CreateDirectory(d);
    var line = System.Text.Json.JsonSerializer.Serialize(new { ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0, module, level, source, msg = msg.Length > 2000 ? msg[..2000] : msg }) + "\n";
    File.AppendAllText(Path.Combine(d, module + ".jsonl"), line);
  } catch { }
}
```

## Pre-stream readiness checks
The stream starts **5:00 pm America/Chicago daily** (DST-aware). The core runs all checks at **4:30 pm and 4:45 pm Central** and on the Console page's **Run now** button, and posts pass/warn/fail per item to the Console and as a toast.

**Core checks (automatic):** each registered module is up (`always_start` modules fail if down, others warn); Streamer.bot WebSocket reachable on 127.0.0.1:8080 (warn); OBS websocket reachable on 127.0.0.1:4455 (warn); free disk space on the Suite drive (warn < 5 GB, fail < 1 GB); error-level Console entries in the last 30 minutes (warn if any).

**Module checks (you provide, either way):**
1. **HTTP** (preferred): add `"prestream": "/api/prestream"` to your manifest. The core does `GET <url><prestream>` with your module token (`Authorization: Bearer <PINGUINO_API_TOKEN>`, timeout 5 s) at check time and expects `{"items": [ ... ]}`.
2. **File:** write `<PINGUINO_DATA_DIR>\console\prestream-<module id>.json` (whole file, atomic replace) every <= 5 min and on state changes: `{"ts": <epoch or ISO>, "items": [ ... ]}`. The core uses it when no `prestream` URL is declared, and treats it as stale (warn "no recent readiness report") if `ts` is older than 10 minutes.

**Item:** `{"id": "chat", "label": "Twitch chat connected", "status": "pass|warn|fail", "detail": "optional short text"}`. Use `fail` only for things that would break the stream (not connected, not signed in, not a mod); `warn` for degraded or optional. Suggested items: Host: chat connected, EventSub connected, each bot account signed in and moderator, OBS connected, Streamer.bot reachable (if still used); Multi: chat sources connected; Listen: mic/model ready; Link: Tailscale/OBS link status. The core prefixes your items with your module id in the report.

**Core API (token as usual):** `GET /api/console?since=<seq>&limit=<n>&min_level=&module=&q=` returns `{"seq": <latest>, "entries": [{seq, ts, module, level, source, msg}], "errors": <error count>}`; `GET /api/prestream` returns the latest report `{"ts", "scheduled", "slot", "summary": {"pass","warn","fail"}, "items": [{module, id, label, status, detail}]}`; `POST /api/prestream/run` runs it now.
