# Private match (lobby) store: contract

Owners: Helper (01/02 fork) = chat side and the source file, Host (02) = bridge, Site (05) = store and page. Status: PROPOSED, 05 may change paths or field names, tell the other two.

Goal: the private match name and password live on the site in a PRIVATE store, readable only by signed-in players and staff. Chat never shows the password.

## Data flow

1. A mod types `!lobbyname NAME` or `!lobbypass PASS|off` in chat. The Helper writes `Data/runtime/helper_settings.json` (`LobbyName`, `LobbyPassword`, `LobbyUpdatedAt` UTC ISO, `LobbyUpdatedBy` login). That file stays the one local source of truth (the Helper, `!pm` and the Host read it).
2. The Host bridge (02) sees `LobbyUpdatedAt` change (file stamp poll every 10 s, plus once at start) and pushes to the site. It uses the same bot key as the other bridges (`Boards.SiteKey()`, header as in SITE_BRIDGES.md), never logs the password, retries with backoff, and keeps the last pushed `LobbyUpdatedAt` in `Data/runtime/lobby_push.json` so a restart does not re-push.
3. The site (05) stores it privately and shows it on a sign-in page.

## Site endpoints (proposed)

| Call | Auth | Body / answer |
|---|---|---|
| `POST /api/bot/lobby` | bot key (staff-write) | `{ "name": "peng3", "password": "", "hasPassword": false, "updatedBy": "login", "updatedAt": "2026-10-20T21:00:00Z" }` -> `200 {"ok":true}`. Last write wins by `updatedAt` (an older one answers `200 {"ok":true,"stale":true}`). |
| `GET /api/bot/lobby` | bot key | same shape, so the Host can recover after a site wipe. |
| `GET /api/lobby` | signed-in session, role player-in-queue-or-match, mod or owner | `{ "name", "password", "hasPassword", "updatedAt" }` |
| `/lobby` (page) | same as `GET /api/lobby` | shows name and password for signed-in players/staff, otherwise a sign-in prompt. |

Hard rules for the site: `Cache-Control: private, no-store` on the GET, the password is never in server-rendered public HTML, sitemap, `/api/faq`, `/api/commands`, logs or analytics, never in a URL or query string, and the public pages show at most the name or nothing. A player who is not in the queue or a match gets 403.

## Chat side (done in the Helper)

- Chat answers (`what's the lobby code`, a queue answer, `!lobbypass` with no value) give the NAME and, when a password exists, `the password is on <site>/lobby (sign in), or ask a mod`. With no password they say `no password`.
- The mod command reply never echoes the password either. A mod who types the password in chat has already shown it in chat, so mods should set it from the site page once 05 adds staff-write there, or tell the Host to take it from the site (see below).
- `LobbyPagePath` in `helper_settings.json` (default `/lobby`) is the page the Helper names.
- The public and mod knowledge packs never contain it (`Tools/test-helper-pack.py` fails the build if the current password text appears in either pack).

## Open points for 05 and 02

- 05: confirm the paths, the sign-in rule for "player in the current match", and whether staff can also edit on the page. If staff edit on the site, the Host polls `GET /api/bot/lobby` and writes the same fields into `helper_settings.json` (so chat and `!pm` follow). Say so and I will leave the file as the shared copy.
- 02: `HostBots.cs` line 68-70 (`!pm`) still prints the password in chat. It should print the name and the same "password is on the site" line.
