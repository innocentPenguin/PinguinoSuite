# Private match (lobby) store: contract

Owners: Helper = chat side and the local source file, Host (02) = bridge, Site (05) = store and page. This matches what the site built (05, site commit bec0647).

Goal: the private match name and password live on the site in a PRIVATE store, readable only by staff and by the signed-in players of the current match.

## Data flow

1. A mod types `!lobbyname NAME` or `!lobbypass PASS|off` in chat. The Helper writes `Data/runtime/helper_settings.json` (`LobbyName`, `LobbyPassword`, `LobbyUpdatedAt` UTC ISO, `LobbyUpdatedBy` login). That file is the one local source of truth (the Helper, `!pm` and the Host read it).
2. The Host bridge (02) pushes it to the site when a match starts and when the values change while a match is live. It uses the same bot key as the other bridges, never logs the password, and ends the push with `active:false` when the match ends.
3. The site keeps it in memory only, and shows it to the right readers.

## Site endpoints (built)

| Call | Auth | Body / answer |
|---|---|---|
| `POST /api/bot/match-private` | bot key | `{ "matchId": "optional", "name": "peng3", "password": "", "active": true }`. Name and password are capped at 60 characters. Memory only. Cleared on `active:false`, when the match ends, or when the bot state has no live match (cleared at match end, Ivan's rule). |
| `GET /api/customs/match-private` | session | `{ "available": true, "name": "...", "password": "..." }`, `Cache-Control: no-store`. Readers: staff, or a signed-in player whose Twitch name or site member is in the current match (blue or orange of the bot state). Everyone else gets `{ "available": false }`, logged-out users get 401. |

The private match box is on the `/customs` page for those readers. It is in no public endpoint (the site tests check it).

## Chat side (the Helper, commit e134683 plus the pointer fix)

- Chat answers (`what's the lobby code`, a queue answer, `!lobbypass` with no value) give the NAME and, when a password exists, `the password is on <site>/customs (sign in), or ask a mod`. With no password they say `no password`. `LobbyPagePath` in `helper_settings.json` (default `/customs`) is the page named.
- The mod command reply does not echo the password.
- The public and mod knowledge packs never contain it (`Tools/test-helper-pack.py` fails if the current password text appears in either pack).

## Open points

- A standing lobby that survives restarts and is readable by queue members needs `POST/GET /api/bot/lobby`, `GET /api/lobby` and staff edit. 05 will build it only if 05 or 00 approves it. Until then the store above is the one in use.
- 02: push at match start to `/api/bot/match-private`, and fix `!pm` (`PinguinoHost/HostBots.cs` lines 68-70), which still prints the password in chat.
- Pending decision (Ivan): whether chat answers say the password again. Nothing about that is built yet.
