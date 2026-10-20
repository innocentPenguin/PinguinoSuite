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

## Devices: master / auxiliary
Several machines can run the Suite (streaming PC, gaming PC, Mac). Each install has a stable **device id** (`Data\runtime\device.json`), a name and a **priority**. Exactly **one alive device is the master** and holds the *singletons*: bots/Host, Spotify, the pre-stream scheduler. Auxiliary devices run only local things (Listen mic, Link, Multi viewer) and control the master's bots remotely.

**Who is master (every device computes the same answer from heartbeats, no server):**
1. a manual pin ("Take control here") on a device that is alive, else
2. a device that is streaming (a module reports `POST /api/device/streaming {"on": true}` while OBS is live), highest priority first, else
3. the alive device with the highest priority (ties: lowest device id).
A device is *alive* if its heartbeat arrived in the last 20 s. A device that just (re)appeared only counts for rule 3 after 30 s alive, so a booting PC does not yank the bots away mid-session. A device that already knows peers waits 10 s after start before assuming it is master. A pin to a dead device is ignored. Default priorities: master-role machine 100, others 50; editable in the app.
Known limit: if the network between devices is cut while both stay online, each side can think it is master for the duration of the cut (no quorum, on purpose, so a lone Mac can take over when the PC is off). Singletons check the lease (below) every 10 s, which bounds the overlap after the network returns.

**Manifest:** `"singleton": true` marks a module that may only run on the master (Host has it; Spotify will). The core refuses to start it elsewhere, stops it when the device loses the master role and starts it again on promotion (if its `enabled` and `start_with_suite` options are on).

**Lease (for singleton modules, token = your module token):** `GET http://127.0.0.1:8760/api/device/lease` -> `{"is_master": true, "master_id": "...", "master_name": "...", "device_id": "..."}`. **A singleton must poll this every 10 s and shut down cleanly when `is_master` is false, and must not start working before it has seen `is_master: true`.** (Host/02: add this check; the core already blocks starting it on an auxiliary device, this is the second fence.)

**Streaming flag (any module, module token):** `POST /api/device/streaming {"on": true|false}`. Host or Link sets it while OBS is streaming on this device.

**Transport (04 / Link).** Link owns the network. The core talks to Link only on loopback and the core never opens a network port. Contract:
- Core -> Link, every 5 s: `POST <link url>/api/peer/broadcast` with the module token (`Authorization: Bearer`, also `x-link-token`) and body `{"type": "device-hb", "payload": {id, name, priority, streaming, streaming_ts, pin: {to, ts}, sent}}`. Link sends `body` unchanged to every paired peer over the tailnet and answers `200 {"sent": n}`. 404 or an error just means "single device".
- Link -> core, when a peer's message arrives: `POST http://127.0.0.1:8760/api/device/peer` with Link's module token and the same body. Link must authenticate the peer (pairing secret / tailnet identity) and may add `"from": "<peer name>"`; the core only reads `payload`.
- Pairing (Link UI/API, not the core): the master shows a short-lived pairing code; an auxiliary enters `<master tailnet name or IP> + code`, they exchange a shared secret, and each side stores the other as a peer. Pairing is symmetric afterwards. Any device can be unpaired from either side.
- Later (phase 2): Link proxies a peer's module UI (for example the master's Host page) so an auxiliary can control the bots remotely; until then an auxiliary shows "bots run on <master name>".

**Core API (app token):** `GET /api/device` (me, master, devices, pin), `POST /api/device/take` (pin to this device), `POST /api/device/release` (clear the pin), `POST /api/device/config {name, priority, role_pref}`. Module-token endpoints: `/api/device/peer`, `/api/device/streaming`, `/api/device/lease`. Everything is logged to the Console under module `core`, source `device`.

## Theme (shared colours)
One palette for the whole Suite: near-black surfaces and **penguin orange `#ff9900`**. The tokens live in `App/src/theme.css` (shell and core serve the same file). **Module pages: add this after your own `<style>` (your inline values stay as the fallback when the core is not reachable) and use only the variables, never raw hex:**
```html
<link rel="stylesheet" href="http://127.0.0.1:8760/theme.css">
```
(Use `PINGUINO_CORE_URL` from your environment if you build the URL on the server side. No token is needed. The core never sends `X-Frame-Options` on it, and it is a plain CSS file, so it works inside the app's iframe.)

| Token | Value | Use |
|---|---|---|
| `--bg` / `--bg2` / `--panel` / `--panel2` | `#050505` / `#0a0a0b` / `#101012` / `#17171a` | page / sidebar, inputs / cards / raised controls |
| `--line` / `--line2` | `#232326` / `#34343a` | hairlines / control borders |
| `--fg` / `--dim` / `--faint` | `#f2f0ec` / `#a39f98` / `#85827b` | text / secondary text / hints |
| `--accent` `--accent-hover` `--accent-active` | `#ff9900` `#ffad33` `#e68a00` | primary buttons, active nav, links, focus |
| `--accent-soft` `--accent-line` | `#ff990022` `#ff990066` | tinted background / border (selected item, chip) |
| `--on-accent` | `#140b00` | text on an `--accent` fill |
| `--focus` | `#ffc266` | 2 px focus ring (`:focus-visible` is already styled) |
| `--ok` `--warn` `--bad` `--live` `--info` | `#3ddc97` `#e8d44d` `#ff5c5c` `#ff4d4f` `#9fb4c7` | pass / warn (yellow, not orange) / fail / on air / neutral |
| `--r`, `--shadow` | `14px`, … | card radius, elevation |

Legacy names `--ice`, `--ice2`, `--beak`, `--vio`, `--acc` still resolve (to accent / accent-active / accent / muted tag / accent) so older pages recolour automatically; new code should use the `--accent*` names. **Do not reuse `--ok` for ordinary text.** Contrast (WCAG): text and accent on surfaces are 5-18:1 (`--faint` is 5:1); status colours are 6-13:1 on `--panel`. Never rely on colour alone for status: pair it with a word or icon. Reading the tokens in script: `getComputedStyle(document.documentElement).getPropertyValue('--accent')`.

## Integrations hub
The app's **Integrations** tab lists every outside connection in one place: Twitch and chat platforms, Spotify, Discord, Tailscale/Link devices, OBS, Streamer.bot, the site, and which API keys are set (never their values), each with a status and Connect / Test / Open buttons. The core builds the list (`GET /api/integrations`) by asking each running module, in this order:
1. **Manifest `"integrations": "/api/integrations"`** (preferred): your module answers `GET` (module token) with `{"items": [ ... ]}`.
2. A status JSON (your `health` URL) containing `"connectors": [{platform, label, status, detail}]`, plus an optional `twitch_connect_url` (Multi's shape).
3. Otherwise your pre-stream items are shown as your connections.

**Item:** `{"id": "twitch", "name": "Twitch (bot account)", "group": "Chat platforms", "status": "connected|needs_auth|error|off|unknown", "detail": "short text", "connect_url": "https://...", "connect_label": "Connect Twitch", "test": "/api/test-twitch"}`. `connect_url` must be `https://` or loopback (it opens in the system browser). `test` is a path under `/api/` that the app calls with **POST** (module token) when the user presses Test; answer `2xx` for pass. Keep `detail` free of secrets. Modules that are not running show as Off with an Open button.

## Other core helpers (app token)
- `POST /api/modules/{id}/post {"path": "/api/...", "body": {...}}` and `GET /api/modules/{id}/get?path=/api/...`: the app reaches a module's `/api/` paths through the core (module token attached), so the UI needs no cross-origin call.
- `GET /api/modules/{id}/probe`: the module's health JSON. `GET /api/integrations`, `GET /api/console`, `GET /api/prestream`, `POST /api/prestream/run`.
- Control files in `Data\runtime\control\`: `start|stop|restart-<module id>` and `prestream-run` (runs the pre-stream checks; the latest report is also written to `Data\runtime\console\prestream-last.json`).
- **Several nav entries per module:** `"ui"` may be an array of blocks (Host has Bots / Host and Actions & Events); each becomes its own sidebar entry and page.

## Key vault (API keys and tokens)
All PC-side keys live in **one encrypted store** (`Data\vault.bin`; Windows DPAPI for the current user, macOS/Linux a keychain-held key). Nothing in it is ever plaintext on disk, shown in the UI after it is saved, or written to the Console (every line that reaches the Console has stored secrets replaced by `••••`). Railway/site variables stay in Railway; the vault only holds what runs on the PC (for example `SPOTIFY_API_KEY`).

**For a module (what 02/03/04/spotify do):**
1. Declare the keys in your manifest: `"secrets": ["SPOTIFY_API_KEY", "TWITCH_BOT_TOKEN"]` or objects `{"name": "SPOTIFY_API_KEY", "label": "Spotify API key", "required": true, "test": "/api/test-key"}`. `required: true` makes a missing key a **fail** in the pre-stream check (otherwise a warn); `test` is a path under `/api/` the app POSTs (with your module token) when the user presses Test next to the key (2xx = pass). Names: letters, digits, `_ . -`, up to 80 chars; use `UPPER_SNAKE_CASE`.
2. Read a key at start (and again after an auth failure): `GET {PINGUINO_CORE_URL}/api/vault/<NAME>` with `Authorization: Bearer <PINGUINO_API_TOKEN>` (your module token). `200 {"name": "...", "value": "..."}`. `403` = you did not declare it (and the denial is logged); `404` = not set yet (report `needs_auth` / a pre-stream item, do not crash); `409` = this device is not the master and holds no vault (see below); `503` = no key store on this OS.
3. Hold the value in memory only. Never write it to your own files, logs or `/api/status`, and never put it in a URL. Do not cache beyond the process lifetime; fetching again is cheap.
4. Missing key: show `needs_auth` in your `integrations` / `prestream` items with detail "key missing: add NAME in Integrations > Key vault". The core also adds a pre-stream item "API keys in the vault" for every module with missing declared keys.

**Migration (per module, no big bang):** (a) the user clicks *Import into vault* (Integrations tab) which copies secret-looking values from `settings.json`, `chat_settings.json`, `host_secrets.json`, `bots_secrets.json` into the vault under canonical names (`TRN_API_KEY`, `WEBSYNC_KEY`, `CHAT_BOT_API_KEY`, otherwise `<FILE>.<KEY.PATH>`), leaving the files unchanged; (b) the module is changed to read from the vault (with a one-release fallback to its old file); (c) once verified live, the user clicks *Remove plaintext from <file>*: the core blanks only values the vault holds identically. Link and Multi token files follow the same pattern when those modules adopt the endpoint.

**Devices:** the master's vault is the source of truth. A device that has peers and is not the master answers `409`; auxiliary devices will fetch keys through Link from the master on demand (never copied, never stored: phase 2, same Link channel as the device heartbeat). A single device always serves its own vault. **Backup / move:** Integrations > Key vault > *Export encrypted backup* (passphrase, 8+ characters, scrypt + Fernet) and *restore* on the new PC.

**Core API (app token; values are never returned):** `GET /api/vault` (name, set/missing, updated, last_used, used_by, declared_by, plaintext summary), `POST /api/vault/<name>/set {"value"}` (set or rotate), `POST /api/vault/<name>/delete`, `POST /api/vault/<name>/test`, `POST /api/vault/import-plaintext`, `POST /api/vault/scrub {"file", "confirm": true}`, `POST /api/vault/backup {"passphrase"}`, `POST /api/vault/restore` (body = backup, `X-Passphrase` header). Module-token: only `GET /api/vault/<name>` for keys that module declared.

**Module write (rotation):** a module may also `POST /api/vault/<NAME>/set {"value": "..."}` with its module token, only for names it declared (for example Host storing the fresh Twitch token after a re-sign-in). `403` for undeclared names; delete and test stay app-only.

## Voice commands: silent and logged
Voice commands (Listen / Voice Studio) never produce chat output. An action is a marker or a silent call to a module API through the core (`/api/voice/dispatch`); whatever the module answers (including a `say` reply) is discarded, never posted. Built-in: "skip the song / skip this song / I want this song skipped" calls Spotify `POST /api/chat-command {"command": "skip", "user": "<streamer>", "role": "broadcaster", "isMod": true}`. Every heard command (fired, `master_off`, `ignored_unsure`, `cooldown`, `failed`, `test_dry_run`) is written with heard text, match score and Listen's uncertainty to `Suite\modules\listen\data\voice_log.jsonl` (Voice Studio table, `GET :8765/api/voice-log`) and to the Console as source `voice`. Phrase alternatives are separated by `|`.

## Device status merge (green wins)
Each device publishes a compact snapshot of its own integration and pre-stream statuses in the device heartbeat (`status: {"i": {item id: status}, "p": {"module:id": status}}`, refreshed every minute). The master stays the source of truth, but if an alive peer reports an item **green** (`connected` / `pass`) that this view has as warn/fail, the merged Integrations and pre-stream views show it green, add `from: <device name>` and "(OK on <device>)", and the UI says "OK via <device>". Never merged: vault/key items, "module is running" items, disk space, error counts and the missing-keys item (per-device facts or secrets). The vault and the bots stay master-only. OBS: this PC's OBS WebSocket is port 4455 (127.0.0.1 locally); the password is entered by the user in Integrations > Key vault as `OBS_WS_PASSWORD`, never stored in a manifest or file.

## Help for every status (clickable ? panels)
Every warn/fail/error and every row (green too) in the Suite opens a help drawer: what it means, numbered steps, an optional link, and a fix button. **Modules write their own text**; the core only supplies generic ones (OBS, Streamer.bot, site, disk, errors, key vault, module up/down, Tailscale, device, Listen, voice, console, pre-stream) and a fallback. A non-green item with no help gets a "no help written yet" panel and one Console warning (`source: help`) naming the item, so the owner fills it in.

Help object (plain text only; links must be https or loopback; max 14 steps):
```json
{"title": "Twitch sign-in", "summary": "One sentence on what this is.",
 "steps": ["Open Twitch Developer Console...", "Scopes needed: ...", "Paste the token here"],
 "example": "oauth:xxxxxxxx (format only, never a real value)", "scopes": ["chat:read"],
 "link": {"label": "Twitch console", "url": "https://dev.twitch.tv/console"},
 "fix": {"label": "Enter the key", "route": "integrations", "focus": "TWITCH_TOKEN"}}
```
`fix` may hold `route` (a shell page: `integrations`, `console`, `m:<id>`...), `focus` (a vault key name: opens its Set/Rotate box), `url` (external), `module_action` `{module, action: "start"|"restart"}`.

Where to put it:
- On an **integration item** or **pre-stream item**: add `"help": {...}` to the item.
- Keyed by item id in the manifest: `"help": {"<item id>": {...}, "_module": {...}}` (`_module` = the "how this module works / set up / redo" overview, shown from the module name and the page `?`).
- On a **secret**: `{"name": "X", "label": "...", "help": {...}}`. This is also shown inline under the Set/Rotate box ("How to get this key"). Say where to find it, scopes, example format; never the value.
- Console lines: warn/error lines are clickable; the core matches the message to a topic, or uses the module's help by source.
Core endpoints: `GET /api/help?key=&module=&item=&source=&msg=` and `GET /api/help/all` (index for the Help page).

## Module switch (on/off + padlock)
Every module has an on/off switch (Settings > Modules and the dashboard Modules card) with a padlock beside it. `POST /api/modules/<id>/enable {"on": bool}` (app token): on = `enabled` + `start_with_suite` + start now; off = stop now + no autostart; saved in the core settings. The padlock is UI only: switches start locked, unlock lasts 30 s or one change. Modules with `defaults.always_start` (Host, Multi) are pinned on by the manifest, and only the unlock + switch-off stores `override_off`, which lifts the pin until switched back on. Modules need no code for this; add `help` text if the module needs a note on what going off means.

## Pop-out windows (split a page across monitors)
The shell (Tauri) can open extra windows, put them on a chosen monitor or half of one, and remember where they were. Layouts are saved per label in `<data dir>/windows.json`; pop-outs that were open reopen at launch (closing one with its X stops that). Not available in a plain browser.

Shell API (`window.PGWin`, in `App/src/bootstrap.js`; Rust in `App/src-tauri/src/windows.rs`):
- `PGWin.monitors()` -> `[{index, name, x, y, width, height, scale, primary}]` (physical pixels; `y` negative = a monitor above the main one).
- `PGWin.open({label, url, title?, width?, height?, monitor?, place?, always_on_top?, decorations?, reset?})`: `label` letters/digits/`-` (prefixed `pop-`); `url` = a local `http://127.0.0.1:<port>/...` page or a shell path (`index.html?popout=console`, chrome-less shell page); `monitor` = index or name; `place` = `full|top|bottom|left|right` (fills that part of the monitor; no `place` = remembered geometry, else a centered window); `reset` ignores what was remembered. Opening an open label brings it forward.
- `PGWin.close(label, forget?)`, `PGWin.onTop(label, on)`, `PGWin.list()` -> `[{label,url,title,open,on_top,monitor}]`.
- Only local pages can be opened. Module pages are plain local pages (as in the shell iframe), so they open directly and need no token; shell pop-outs get the core token from the app the same way the main window does.

From a module page (an iframe, no Tauri access) ask the shell with `postMessage`:
```js
parent.postMessage({pinguino:'window', op:'open', label:'chat-top', url:location.origin+'/?type=chat&half=top', monitor:'1', place:'top'}, '*');
parent.postMessage({pinguino:'window', op:'monitors'}, '*');   // reply: {pinguino:'monitors', monitors:[...]}
parent.postMessage({pinguino:'window', op:'close', label:'chat-top'}, '*');
```
Errors come back as `{pinguino:'window-error', error}`. Example split: monitor A (above) `place:'top'`... or two windows on two monitors, each `place:'full'`; one monitor split in half = `top` + `bottom`.
UI: Settings > Pop-out windows, and "Pop out" in the top bar.

## Personalization (per device)
Users can change theme (8 presets + custom accent), corner style, density, UI zoom, motion, sidebar (full / icons / hidden, Ctrl+B), start page, menu order and hidden items, dashboard blocks (order / hide), sounds, notifications, clock format, and save named "looks" that can switch automatically on go-live / offline. UI: Personalize page (System). Stored per device in `<data dir>/prefs.json` via `GET/POST /api/prefs` (`POST /api/prefs/reset`), validated by `Suite/suite/prefs.py` (unknown keys dropped, colours must be hex), mirrored in `localStorage` (`pgprefs`) so the shell paints the right look instantly.
For module pages:
- Use only the `theme.css` variables for colour and your page follows every theme automatically. The core appends the user's palette to `/theme.css`, so a page that links `http://127.0.0.1:8760/theme.css` gets it on load.
- Live changes arrive as `window.addEventListener('message', e => { if (e.data && e.data.pinguino === 'theme') { for (const [k,v] of Object.entries(e.data.vars)) document.documentElement.style.setProperty(k, v); } })` (`e.data.classes` = `{dense, calm}`). Optional but nicer than reloading.
- Hardcoded colours break the light theme ("Paper"); prefer `var(--panel)`, `var(--fg)`, `var(--hover)`, `var(--panel-end)`.
- New variables in theme.css: `--hover`, `--hover2`, `--panel-end`.

## Pre-stream schedule and more adjustable bits (cycle 1)
- `GET/POST /api/prestream/schedule`: `{enabled, slots:["16:30","16:45"], days:[0..6 (Mon=0)], tz:"central"|"local"}` stored in the core settings; edited in Settings > Pre-stream check schedule. Defaults unchanged (16:30 + 16:45 US Central, every day).
- Manifest hook `on_start`: `{"post": "/api/..."}` called once after the core launches the module (Listen uses it to start the mic).
- Personalize adds: wording (app name, offline banner, Live / Offline labels), Errors-tile window and hide-when-clean, and sounds for Activity events (follow, sub/resub/gift, raid, cheer, redeem), which keep working on any page.
- Console: Copy / Save the lines shown. Dashboard pre-stream card: Run now.

## PenguinComm (Listen + Speak in one page)
The shell shows PinguinoListen (`listen`, mic, Ivan to the bots) and PinguinoVoice (`voice`, the bot's TTS voice) as ONE nav entry/page "PenguinComm" (route `comm`) with two sections (Both / Listen / Speak, remembered), each with its own status, on/off switch + padlock, Restart, help and the module's own UI (its manifest `ui.path`, so each module keeps its own settings). Ids, ports, manifests, `always_start` and `on_start` are unchanged; if only one of the two is registered the page shows just that section. Pre-stream items of those two modules appear as clickable chips on top. Listen tells Voice when a voice command fired (`POST /api/voice/dispatch` -> voice `/api/event {"kind":"voice_cmd","what":<id>}`, best effort).

Pop-out additions (from Multi's SHELL_WINDOW_SPEC): `open` also accepts `size:{w,h}`, `bounds:{x,y,w,h}` (last known position, used when nothing is remembered and it lies on a monitor), `remember:false`, numeric `monitor`, and `place`. For messages from module pages, remembered geometry beats `monitor`/`place` (those are first-time defaults). If a remembered monitor is gone the window sits on the nearest monitor and its saved spot is kept, so it returns when the monitor does. Extra ops: `{op:'set', label, always_on_top}`, `{op:'list'}` -> `{pinguino:'windows', windows:[{label,url,title,open,on_top,monitor}]}`. Window-moved events are not sent (Multi saves its own geometry).

## Quick actions, action runs, command palette (Streamer.bot parity, shell side)
- Quick actions page: reads Host `GET /api/automations` (`{doc:{actions:[{id,name,group,enabled,triggers:[{type,...}]}]}, master}`), runs `POST /api/automations/test {id, dry}` through the core proxy; stars are per device (localStorage).
- Activity > Action runs: Host `GET /api/automations/log?n=` (`{runs:[{ts,action,id,trigger,ok,ms,error}]}`).
- Command palette (Ctrl+K): pages, pre-stream run, sounds, sidebar, pop-out, saved looks, themes, restart module, and every enabled Host action.

Quick actions tabs (Host commit 5c8c6f2, shapes in Docs/ACTIVITY_FEED.md): Actions (per-action on/off `POST /api/automations/enable`, enable/disable a group, Export `GET /api/automations/export`, "Streamer.bot retired" switch `GET/POST /api/cutover`), Variables (`/api/vars`, `/api/vars/delete`), Queue (`/api/queues`, pause/resume), Triggers (`/api/automations/triggers`), Hotkeys (`/api/automations/hotkeys`, Fire = `POST /api/automations/fire`), Connect apps (`/api/endpoints`; the token is never shown, it lives in the key vault as BOT_API_KEY).

Automatic config backup: `GET/POST /api/backup/auto {enabled, every_hours, keep}`, `POST /api/backup/auto/run`; zips (no secrets) in `<Data>/backups/auto`, master device only. Dashboard module rows have a Logs drawer (recent Console lines of that module); an unexpected module stop raises a toast + desktop notification (Personalize > notifications).

## Accounts page (streamer Twitch sign-in)
Shell page `accounts` (System). Host API it reads (module token via the core proxy; tokens are never returned): `GET /api/account/streamer` -> `{signedIn, login, displayName, expiresInSec, scopes:[granted], required:[{scope, feature, needed}]}`; `POST /api/account/streamer/signin` -> `{ok, url?}` (requests the full required list; the shell opens `url` if given); `POST /api/account/streamer/signout`. Bot accounts: `GET /api/bots` (`signedIn, signedInAs, health, healthDetail, enabled`). Missing-scope prestream help should use `fix:{label:"Re-sign Twitch", route:"accounts"}`.

### Listen microphone (device by name, alerts)
Listen saves the mic as `device_name` + `device_hostapi` (the old int `device` is legacy) and resolves it to the current sounddevice index at every start. If the saved mic is gone it falls back to the Windows default input and raises `mic_alert` (kind `fallback`); with no input it refuses to start (`missing`); while listening, 30 s of dead-quiet input raises `silent` and tries one reopen. `GET /api/status` of Listen returns `mic_alert` (null when fine); the shell shows a red banner on the dashboard Listen card and PenguinComm, plus a toast/sound/desktop notification, and the pre-stream check fails "Selected microphone present".
