# PinguinoSpotify <-> innocentpenguin.com: API contract (v1)

Status: DRAFT from 05 (site), Oct 19 2026. The spotify session may propose changes; 05 owns the site side, the spotify session owns the PC module. Nothing here exposes the PC: the module only makes OUTBOUND calls.

## Principles
- The **PC module owns the music state** (what plays, the queue, the rules). The site is a mirror + the public front door.
- The site works with the PC off: it shows the last known state with an "offline" badge and refuses new requests (503).
- Spotify search runs **on the site** (client-credentials flow, `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` in Railway). Public catalog data only; **no viewer Spotify tokens, ever**. The module uses the owner's own Spotify auth on the PC for playback.
- Viewer identity = the site's Twitch (or other) login. Names shown publicly are the site display name only.
- Everything is versioned: every body carries `"v":1`. The module ignores unknown fields; the site ignores unknown fields.

## Auth
- Module -> site: `Authorization: Bearer <SPOTIFY_API_KEY>` (32+ chars, a NEW Railway variable, separate from `BOT_API_KEY` so one leak does not cover both). TLS only. Optional hardening later: `X-Signature: HMAC-SHA256(body, key)` + `X-Timestamp`.
- Viewers -> site: the normal `ip_session` cookie, same-site `Origin` required, JSON only.

## Module -> site (outbound)
1. `POST /api/spotify/push` (every 3 s while playing, 10 s when idle, immediately on a change). Whole-state mirror:
```json
{"v":1,"updatedAt":1792420000000,
 "status":{"requestsOpen":true,"paused":false,"maxQueue":25},
 "nowPlaying":{"id":"spotifyTrackId","title":"","artists":["",""],"album":"","art":"https://i.scdn.co/...","durationMs":0,"progressMs":0,"isPlaying":true,"requestedBy":"displayName|null","progressAt":1792420000000},
 "queue":[{"rid":"req-123","id":"spotifyTrackId","title":"","artists":[""],"art":"","durationMs":0,"requestedBy":"displayName","votes":0}],
 "history":[{"id":"","title":"","artists":[""],"art":"","playedAt":1792419000000,"requestedBy":"displayName|null"}]}
```
   Limits: queue <= 100, history <= 50 (site keeps newest 50), strings trimmed. Response: `{"ok":true,"blocklistVersion":N}`.
2. `GET /api/spotify/poll?wait=1` (long poll, holds up to 20 s): returns pending viewer actions:
```json
{"v":1,"events":[
 {"id":"e1","type":"request","at":0,"user":"displayName","login":"twitchlogin","trackId":"..","title":"..","artists":[".."],"art":"..","durationMs":0},
 {"id":"e2","type":"vote","at":0,"user":"..","login":"..","rid":"req-123","kind":"up"},
 {"id":"e3","type":"vote","kind":"skip","user":"..","login":".."}]}
```
   Events stay pending until acked; unacked events are redelivered after 30 s; events older than 10 min are dropped.
3. `POST /api/spotify/ack` `{"v":1,"results":[{"id":"e1","ok":true,"rid":"req-123"},{"id":"e2","ok":false,"reason":"explicit_blocked"}]}` -> the viewer sees the reason. Reason codes: `queue_full`, `duplicate`, `blocked`, `explicit_blocked`, `too_long`, `requests_closed`, `cooldown`, `already_voted`, `unknown_request`.
4. `GET /api/spotify/blocklist` -> `{"v":1,"version":N,"tracks":["id"],"artists":["id|name"],"users":["login"]}` (the module enforces it too; the site also enforces on search results and requests).

## Viewers -> site (public API)
| Route | Who | What |
| --- | --- | --- |
| `GET /api/spotify/state` | public, no-store | `{v,online,lastSeen,status,nowPlaying,queue,history,you?}` names only; no logins/ids of users; `online` = last push < 30 s |
| `GET /api/spotify/search?q=` | logged in, 15/min/user | up to 10 tracks `{id,title,artists,album,art,durationMs,explicit}`; blocklisted tracks removed |
| `POST /api/spotify/request` `{trackId}` | logged in | creates a `request` event. Site rules: login required, not banned, requests open, module online, per-user cooldown 120 s, max 3 queued per user, track not blocklisted. The module has the final say (ack) |
| `POST /api/spotify/vote` `{rid,kind:"up"|"skip"}` | logged in | one vote per user per rid; skip votes are per currently playing track |
| `GET /api/spotify/now` | public, CORS open, cached 2 s | tiny `{title,artists,art,progressMs,durationMs,isPlaying,online}` for widgets |

## Staff API (mods; owner for blocklist)
`POST /api/spotify/mod` `{action,value}` via the same `queueCommand`-style event channel: `skip`, `remove <rid>`, `open|close` requests, `pause|resume`, `block-track <id>`, `block-artist <id|name>`, `block-user <login>`, `unblock-*`. Audited with `describeChange`. Blocklist edits are applied on the site immediately and by the module on its next poll.

## Pages
`/music` (public: now playing with progress, queue with upvotes, request search box, recently played) | `/overlay/music` (OBS browser source, transparent, `?theme=`, `?layout=`) | `/mod/music` (staff controls + blocklist). Theme: dark with penguin orange `#ff9900`.

## Failure behaviour
- Module offline: `/music` shows last known state + "PinguinoSpotify offline"; requests/votes answer 503.
- Site restart: state is rebuilt from the module's next push (<= 10 s). Pending events are kept in memory only: lost requests are re-requested by viewers.
- The module must tolerate non-200 from the site and back off (3 s -> 30 s).

## What needs deploying
Railway variables: `SPOTIFY_API_KEY` (shared with the module), `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` (a Spotify developer app, client credentials only; no redirect URI needed). Module side: its own copy of `SPOTIFY_API_KEY` + `SiteUrl`.

## Implemented notes (05, Oct 19 2026)
- Extra routes: `GET /api/spotify/blocklist-view` (staff), `POST /api/spotify/mod` actions: skip, remove, open, close, pause, resume, block-track|artist|user, unblock-*. Mod actions other than block/unblock arrive at the module as events `{type:"mod",action,value,user,login}` (ack them like the others).
- Request events also carry `explicit`. `/api/spotify/now` carries `serverNow` and `progressAt` (server clock ms) so widgets can interpolate progress.
- `nowPlaying.progressAt` and `history[].playedAt` are epoch ms (server clock): send `Date.now()` taken when `progressMs` was read.
- Request events also carry `sub`, `vip`, `staff` booleans (from the viewer badge at login time).
