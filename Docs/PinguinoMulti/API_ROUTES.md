# PinguinoMulti HTTP routes (generated from the code)

Every route registered in `server.py` and `platform_api.py` (138). Multi listens on `127.0.0.1:8766` (`MULTI_PORT`). Local-only guards: the Host header must be a local name; a write (POST/PUT/DELETE) from Multi's own page (Origin equals Host) passes, any other writer (no Origin, or the Tauri app) must present the module token (`x-pinguino-token` or `Authorization: Bearer`) when the Suite supplies `PINGUINO_API_TOKEN`. The Host has its own token on the alert-bridge/activity paths, and `/hook/kick` is authenticated by Kick's RSA signature instead. The description is the first line of the route's docstring; a blank one means the route has none yet. Regenerate by re-running the extraction (AST over the two files) after adding routes; keep this file in step with the code.

## / (pages)

| Method | Path | File | What |
|---|---|---|---|
| GET | `/` | server.py |  |

## /api/ai

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/ai` | server.py |  |

## /api/alerts

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/alerts` | server.py |  |
| POST | `/api/alerts/config` | server.py |  |
| POST | `/api/alerts/control` | server.py |  |
| GET | `/api/alerts/export` | server.py | The active (or named) alert profile + all per-viewer overrides as a file you can keep or move to another PC. Media files are referenced by address, no |
| POST | `/api/alerts/fire` | server.py | A REAL alert straight into the queue without a chat row (Host: intro clips, goal reached, anything not in the activity feed). |
| POST | `/api/alerts/import` | server.py | {doc, name?, overrides?:bool, activate?:bool}: adds the profile under a new name (never overwrites an existing profile), sanitised like any saved conf |
| POST | `/api/alerts/import-host` | server.py | Copy the Host's alert sounds into the active profile ({apply:false} = preview only, {overwrite:true} replaces existing sounds). |
| GET | `/api/alerts/media` | server.py |  |
| POST | `/api/alerts/media` | server.py | Raw file body (Content-Type: application/octet-stream) + ?name=file.ext -> stored in the alert media library. |
| POST | `/api/alerts/media/delete` | server.py |  |
| POST | `/api/alerts/preview` | server.py |  |
| POST | `/api/alerts/scene` | server.py | {scene}: tell Multi which OBS scene is on air (Link / Host call this); switches to the profile mapped to it in the alerts editor. Never touches OBS. |
| POST | `/api/alerts/stress` | server.py |  |
| POST | `/api/alerts/test` | server.py | Queue a TEST alert (flagged; never reaches the inbox, stats, points, credits or chat). Used by the Suite UI and the Host !alert command. |
| POST | `/api/alerts/testall` | server.py |  |

## /api/assist

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/assist/suggest` | server.py |  |
| POST | `/api/assist/translate` | server.py |  |

## /api/cards

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/cards` | server.py |  |
| POST | `/api/cards/manual` | server.py |  |
| POST | `/api/cards/{cid:path}/{action}` | server.py |  |

## /api/chatstyle

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/chatstyle` | server.py |  |
| POST | `/api/chatstyle` | server.py |  |
| POST | `/api/chatstyle/apply` | server.py |  |
| POST | `/api/chatstyle/delete-preset` | server.py |  |
| GET | `/api/chatstyle/export` | server.py |  |
| POST | `/api/chatstyle/import` | server.py |  |
| GET | `/api/chatstyle/presets` | server.py |  |
| POST | `/api/chatstyle/reset` | server.py |  |
| POST | `/api/chatstyle/save-preset` | server.py |  |
| POST | `/api/chatstyle/undo` | server.py |  |

## /api/chatter

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/chatter/{platform}/{user_id}` | server.py |  |

## /api/checks

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/checks` | server.py |  |

## /api/claims

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/claims` | server.py | Streamer-first contract: open medium/high cards the streamer may answer personally. Bots/Router poll this |

## /api/dash

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/dash` | server.py |  |
| POST | `/api/dash` | server.py |  |
| POST | `/api/dash/active` | server.py |  |
| DELETE | `/api/dash/{name}` | server.py |  |

## /api/dashboard

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/dashboard` | server.py |  |

## /api/dev

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/dev/inject` | server.py |  |

## /api/ding

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/ding` | server.py |  |
| POST | `/api/ding/pick` | server.py | Opens a file dialog on this PC (Multi runs locally) and returns the chosen sound path. |
| POST | `/api/ding/reset` | server.py |  |
| POST | `/api/ding/settings` | server.py |  |
| POST | `/api/ding/test` | server.py |  |

## /api/events

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/events` | server.py |  |

## /api/feed

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/feed` | server.py |  |

## /api/geom

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/geom/{label}` | server.py |  |

## /api/goal

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/goal` | server.py |  |
| POST | `/api/goal` | server.py |  |

## /api/help

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/help/all` | server.py |  |

## /api/host-status

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/host-status` | server.py | is the bot Host reachable (as last seen by the activity feed / live-state polls) |

## /api/hotkey

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/hotkey/{action}` | server.py | Act on the top open card (highest score, newest). Target for global hotkeys, Stream Deck, AutoHotkey. |

## /api/hypebar

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/hypebar` | server.py |  |
| POST | `/api/hypebar` | server.py | {label?, c1?, c2?, bg?, fg?, show_after_s?, show_level?, show_numbers?} -> saved look |

## /api/integrations

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/integrations` | server.py | Items for the Suite's Integrations hub (never contains secrets). |

## /api/intro

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/intro/options` | server.py | What a viewer may pick on the website intro form (05 reads this): short text, sounds from the allowed list only. |

## /api/learning

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/learning` | server.py |  |
| POST | `/api/learning/enabled` | server.py |  |
| POST | `/api/learning/reset` | server.py |  |

## /api/live-state

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/live-state` | server.py | Current poll / prediction / hype train from the Host (null when none or the Host is down). |

## /api/messages

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/messages` | server.py |  |
| GET | `/api/messages/{mid:path}/explain` | server.py |  |

## /api/mod

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/mod/{action}` | server.py |  |

## /api/monitors

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/monitors` | server.py |  |

## /api/newchatters

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/newchatters` | server.py | Recent new / returning chatters (for other modules, e.g. a bot that wants to welcome them). |

## /api/obs

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/obs/chat/import` | server.py |  |
| GET | `/api/obs/{kind}` | server.py |  |
| POST | `/api/obs/{kind}` | server.py |  |
| GET | `/api/obs/{kind}/export` | server.py |  |

## /api/open-connect

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/open-connect` | server.py | Open the site's Connect URL in the user's default browser (works from embedded/native shells too). |

## /api/panes

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/panes` | server.py |  |
| DELETE | `/api/panes/{pid}` | server.py |  |
| GET | `/api/panes/{pid}` | server.py |  |
| POST | `/api/panes/{pid}` | server.py |  |

## /api/pins

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/pins` | server.py |  |
| POST | `/api/pins` | server.py |  |

## /api/pop

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/pop` | server.py |  |
| POST | `/api/pop/settings` | server.py |  |
| POST | `/api/pop/test` | server.py |  |

## /api/prestream

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/prestream` | server.py | Readiness for the Pinguino Console: {ts, items:[{id,label,status pass/warn/fail,detail}]}. |

## /api/profiles

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/profiles` | server.py |  |
| POST | `/api/profiles/{name}/apply` | server.py |  |
| POST | `/api/profiles/{name}/save` | server.py |  |

## /api/recap

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/recap` | server.py | Unanswered recap for after the stream: open + missed + snoozed cards, highest score first. |

## /api/rules

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/rules` | server.py |  |
| POST | `/api/rules` | server.py |  |
| POST | `/api/rules/reset` | server.py |  |

## /api/search

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/search` | server.py |  |

## /api/secrets

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/secrets/ai` | server.py | Write-only AI key (Credential Manager). Body: {key/clear}. |
| POST | `/api/secrets/discord` | server.py | Write-only: stores the bot token in Credential Manager; never echoed back. |
| POST | `/api/secrets/youtube` | server.py | Write-only OAuth access token for YouTube live chat. Body: {token/clear}. |

## /api/send

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/send` | server.py |  |

## /api/settings

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/settings` | server.py |  |
| POST | `/api/settings` | server.py |  |

## /api/setup

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/setup` | server.py | Non-secret setup state for the launcher: which secrets exist (booleans only) + plain settings. |

## /api/sounds

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/sounds` | server.py |  |
| POST | `/api/sounds` | server.py | Local-listening sound settings of the chat page (the page validates and merges with its defaults). |
| POST | `/api/sounds/reset` | server.py | Put every ding and chat-pop setting back to its default (the sound files themselves are not touched). |

## /api/splits

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/splits/apply` | server.py |  |

## /api/status

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/status` | server.py |  |

## /api/stream

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/stream/info` | server.py |  |
| POST | `/api/stream/info` | server.py | {title?, description?, tags?, platforms:[youtube,kick]}: edits the current/upcoming broadcast only; never starts or transitions anything. |
| POST | `/api/stream/schedule` | server.py | YouTube only: create an upcoming broadcast (never live). Called only when Ivan clicks Schedule. |

## /api/templates

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/templates` | server.py |  |
| POST | `/api/templates` | server.py |  |

## /api/test

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/test/{platform}` | server.py |  |

## /api/viewer

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/viewer/{platform}/{user_id}` | server.py |  |

## /api/viewers

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/viewers` | server.py |  |
| POST | `/api/viewers/{user}/mute` | server.py |  |
| GET | `/api/viewers/{user}/note` | server.py |  |
| POST | `/api/viewers/{user}/note` | server.py | Streamer's private note about a viewer (local only, max 500 chars; empty clears it). |

## /api/voice

| Method | Path | File | What |
|---|---|---|---|
| POST | `/api/voice/confirm/{card_id}` | server.py |  |
| POST | `/api/voice/transcript` | server.py | Called by Listen (or any ASR) with recent transcript text. Emits reply.suggested; never answers a card. |

## /api/windows

| Method | Path | File | What |
|---|---|---|---|
| GET | `/api/windows` | server.py |  |
| POST | `/api/windows` | server.py |  |
| POST | `/api/windows/restore` | server.py |  |
| DELETE | `/api/windows/{wid}` | server.py |  |
| PUT | `/api/windows/{wid}` | server.py |  |
| POST | `/api/windows/{wid}/launch` | server.py |  |

## /auth

| Method | Path | File | What |
|---|---|---|---|
| GET | `/auth/callback` | server.py | The site redirects here with the tokens in the URL FRAGMENT (never sent to a server log); |
| POST | `/auth/disconnect` | server.py |  |
| POST | `/auth/token` | server.py |  |
| GET | `/auth/{platform}/callback` | platform_api.py |  |
| POST | `/auth/{platform}/client` | platform_api.py | {client_id?, client_secret?} typed by Ivan in the launcher: id -> settings, secret -> Credential Manager. Nothing is echoed back. |
| POST | `/auth/{platform}/start` | platform_api.py |  |
| GET | `/auth/{platform}/status` | platform_api.py |  |

## /hook

| Method | Path | File | What |
|---|---|---|---|
| POST | `/hook/kick` | server.py | Kick webhook receiver (signature checked inside the connector). Kick must reach this over public HTTPS: see Docs/MULTISTREAM_PLAN.md. |

## /obs

| Method | Path | File | What |
|---|---|---|---|
| GET | `/obs/alerts` | server.py |  |
| GET | `/obs/goal` | server.py |  |
| GET | `/obs/hype` | server.py |  |
| GET | `/obs/hypebar` | server.py |  |
| GET | `/obs/poll` | server.py |  |
| GET | `/obs/predict` | server.py |  |
| GET | `/obs/{kind}` | server.py |  |

## /popout

| Method | Path | File | What |
|---|---|---|---|
| GET | `/popout` | server.py | Stream-safe chat for an OBS browser source/dock: public messages only (no cards, notes, composer, muted users). |

## /ws

| Method | Path | File | What |
|---|---|---|---|
| WEBSOCKET | `/ws` | server.py |  |
