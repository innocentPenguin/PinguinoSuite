# Canned-command editor contract (Host `/api/canned`, for the Suite page)

Owner: 12 (Chatty). Backend: `PinguinoHost/HostCanned.cs` (`CannedEditor`), route in `HostAutoApi.cs`. Chatty reloads `canned_commands.json` by itself within about 4 s of a save, no restart. Loopback only (anything else gets 403). Tests: `python Tools/test-host-canned.py <dll>` (48 checks).

## Auth
- Reads (GET): loopback only.
- Writes (POST): same-origin Host page, or the module/API token (`Authorization: Bearer <token>` or `X-Pinguino-Token`) when one is configured. The Suite shell (Tauri origin) without a token gets `401 {"ok":false,"error":"token required"}`.

## Read
- `GET /api/canned` -> `{ok, cooldownSec, variables, file, commands:[{name, aliases, text, choices, enabled, ...}]}` (view form, for lists).
- `GET /api/canned?export=1` -> everything an editor needs in one call:
  `{ok, version:1, exportedAt, cooldownSec, variables:["$(user)","$(touser)","$(luck)","$(games)"], rules:{name, maxTextLength:400, oneLine, noControlCharacters, reservedNames:[...]}, commands:[<as stored>]}`.
  A stored command is `{name, aliases?:[..], text? | choices?:[..], enabled?:false}` (`enabled` is only present when false).

## Write: `POST /api/canned` with `{action, ...}`, always answers `{ok:true,...}` or `{ok:false,error:"..."}`
| action | fields | notes |
|---|---|---|
| `add` | `name`, `text` or `choices[]`, `aliases?`, `enabled?` | refuses an existing name (use `set`) |
| `set` | `name`, any of `text`, `choices`, `aliases`, `enabled` | `text` replaces `choices` and the other way round; `aliases: []` clears them |
| `delete` | `name` | removes the command and its aliases; refuses an unknown name |
| `test` | `name` or `text`/`choices`, `user?`, `touser?` | renders `$(user)` / `$(touser)` / `$(luck)` / `$(games)`, returns `{ok, line}`, sends nothing to chat |
| `cooldown` | `seconds` 5-600 | per-command cooldown |

## Validation (every refusal is `{ok:false,error}`, nothing is saved)
- name / alias: 1-24 of `a-z 0-9 _` (a leading `!` and capitals are stripped / lowered).
- text and every choice: not empty, at most 400 characters, one line, no control characters (what Twitch refuses; the sender also cleans lines with `CleanLine`), must not start with `/` `.` `!`, only the four variables above (`$(anything else)` is refused).
- no duplicates: a name or alias already used by another canned command is refused; so is any name in `rules.reservedNames` and anything a Host module answers to (control, emotes, alerts, gambling: e.g. `gamble`, `slots`, `duel`, `bet`, `emote`, `alert`).
- Every save and every delete keeps the previous file as `canned_commands.json.bak`; unknown keys in the file are preserved.
