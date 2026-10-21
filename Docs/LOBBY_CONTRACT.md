# Private match (lobby) store: contract

Owners: Helper = chat side and the local name file, Host (02) = bridge, Site (05) = store and page. Matches the site built by 05 (site commit bec0647).

DECISION (Ivan): the bots NEVER grab, store or say a lobby password. Customs use a lobby NAME only. Everything below carries the name alone.

## Data flow

1. A mod types `!lobbyname NAME` in chat. The Helper writes `Data/runtime/helper_settings.json` (`LobbyName`). Anything in that value labelled password / pass / pw is cut off and dropped. `!lobbypass` is refused ("Customs use a lobby name only").
2. If the settings file still holds a `LobbyPassword` key from before, the Helper removes it the next time it reloads the file.
3. The Host (02) pushes the NAME to the site when a match starts, with the bot key, and ends it with `active:false` at match end. The push has NO password field (send `password: ""` or omit it).
4. The site keeps it in memory only and shows it to the right readers.

## Site endpoints (built)

| Call | Auth | Body / answer |
|---|---|---|
| `POST /api/bot/match-private` | bot key | `{ "matchId": "optional", "name": "peng3", "active": true }`. Memory only. Cleared on `active:false`, at match end, or when the bot state has no live match. Name capped at 60 characters. |
| `GET /api/customs/match-private` | session | `{ "available": true, "name": "..." }`, `Cache-Control: no-store`. Readers: staff, or a signed-in player of the current match. Everyone else `{ "available": false }`, logged-out 401. |

The private match box is on `/customs` for those readers and in no public endpoint.

## Chat side (the Helper)

- Lobby answers say `Private match -> Name: <name>.` and nothing about a password.
- A password that slips into chat is never repeated: no chat answer reads one, and the packs never contain one (`Tools/test-helper-pack.py` fails if the settings file's `LobbyPassword` text appears in either pack).

## Open points

- 02: push the name at match start to `/api/bot/match-private`, and change `!pm` (`PinguinoHost/HostBots.cs` lines 68-70) to print the name only, with no password.
