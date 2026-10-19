# PinguinoSpotify (module `spotify`, port 8771)

A Spotify queue you own, with viewer song requests. Folder: `Suite/modules/spotify/` (stdlib-only Python, no extra installs). Registered by drop-in `module.json` (nav "Spotify", order 50). Data: `<PINGUINO_DATA_DIR>/spotify/` (`config.json` client id + rules, `tokens.json`, `state.json` queue/history/inbox, `nowplaying.txt`). Console: `console/spotify.jsonl`. Tests: `python -m unittest discover -s Suite/modules/spotify/tests` (45, no network).

## One-time setup (Ivan)
1. https://developer.spotify.com/dashboard > Create app (Web API). Needs a **Premium** account.
2. Add redirect URI exactly `http://127.0.0.1:8771/callback` (literal 127.0.0.1, not localhost).
3. Spotify page > Setup tab: paste the **Client ID** (no secret; PKCE), Save, press **Connect to Spotify**, approve in the browser.
4. Open Spotify on the streaming PC and press play once (so a device exists).
The login is stored in `tokens.json` and refreshed automatically; a revoked token shows in the pre-stream check.

## How the queue works
Spotify's API can only *append* to its queue, so we keep our own queue and push only the **head** to Spotify just before the current track ends (`jit_ms`, default 25 s; the engine polls every 2 s, 1 s near the end). Everything behind the head stays freely editable (drag, remove, play next, undo x30). The pushed head is frozen: removing it marks "skip when it starts". Skip always sends our next song first, then calls Spotify next. If the streamer clears Spotify's queue, the head is re-pushed. If nothing is playing, "Start queue" plays the head directly. When our queue is empty Spotify carries on with its own context.

**Fair ordering:** a viewer's n-th pending request sits in round n; rounds interleave (b's 1st before a's 2nd), subs/VIPs first inside a round, channel-point redeems first of all. Streamer-added or hand-moved songs are *locked* and never reshuffled.

## Rules (Settings tab, all in `config.json`)
requests open/closed, mods-only, subs-only, per-viewer limit (+ extra for subs), max queue length, max song length, block explicit, blocklist (words in title/artist, or track URI/id), blocked viewers, replay cooldown (no re-request within 60 min of playing), duplicate protection (queued or playing), approve-every-request inbox, **stream-safe** (forces no explicit + approval inbox even for mods; the broadcaster always bypasses), skip votes needed, mod instant skip.

## Chat wiring: `POST http://127.0.0.1:8771/api/chat`
For the Host / Streamer.bot (session 02). Local process, no `Origin` header, **no token needed** (low-privilege endpoint; roles are trusted from the caller):
```json
{"user": "viewername", "text": "!sr never gonna give you up", "roles": ["sub","vip","mod","broadcaster"], "redeem": false}
```
Response: `{"handled": true, "ok": true, "code": "added", "reply": "@viewername added '...' (#3 in queue)."}`. Post `reply` to chat when non-empty. `handled:false` = not one of our commands (ignore). Send **every** chat line starting with `!` (or just these commands) and let us parse.

| Command | Who | Effect |
|---|---|---|
| `!sr <name or Spotify link>` (alias `!request`) | all | request; `redeem:true` = channel-point priority |
| `!queue` / `!song` | all | next 3 / now playing + link |
| `!skip` | all | vote (needs `skip_votes`); mods/broadcaster instant |
| `!oops` | all | remove your own last request |
| `!sr open` / `!sr close`, `!srclear`, `!blocksong` | mods | toggle requests, clear viewer requests, block + skip current |

`code` values: `added pending closed mod_only sub_only blocked explicit too_long full dup_queue dup_recent limit user_blocked none lookup offline usage vote skipped removed song queue toggle clear blocked`.

## Other HTTP API (same-origin page, or module token for writes)
GET `/api/state`, `/api/overlay.json`, `/api/search?q=`, `/api/devices`, `/api/setup`, `/api/prestream`, `/api/status` (health). POST `/api/queue/{add|remove|move|play_next|play_now|clear|undo|start}`, `/api/control {action: play|pause|next|previous|seek|volume|transfer, value}`, `/api/settings`, `/api/inbox/{id}/{approve|deny}`, `/api/blocklist`, `/api/setup`, `/api/auth/start`, `/api/disconnect`.

## OBS
Browser source: `http://127.0.0.1:8771/overlay` (transparent; `?next=0` hides up-next, `?theme=light`). Text source file: `Data\runtime\spotify\nowplaying.txt` (template in Settings, rewritten on track change only).

## Pre-stream (`/api/prestream`)
`token` (not signed in = fail, not set up = warn), `premium` (fail if not Premium), `device` (warn if no active device).

## Host command API (agreed with 02)
`POST /api/chat-command` `{command, args, user, display, role: viewer|vip|sub|mod|broadcaster, isMod, isSub, msgId, redeem?}` -> `{ok, say, error, code}` (`say` <= 400 chars, empty = stay silent). Commands: sr, skip, song, queue, oops, blocksong, srclear (declared in `module.json` `commands`). `GET /api/now` -> `{title, artist, url, requestedBy}`. Host owns permissions/cooldowns; per-viewer limits, blocklist and queue rules stay here. Like `/api/chat`, a local caller without an `Origin` header needs no token.

## Website bridge (Docs/SPOTIFY_CONTRACT.md v1, outbound only)
Setup tab > "Website": site URL + `SPOTIFY_API_KEY` (stored write-only in `spotify/config.json`) + enabled. `site_bridge.py` pushes the state mirror (3 s playing / 10 s idle / immediately on change), long-polls viewer events (request, up/skip vote), applies our rules as final authority and acks with the contract's reason codes, and pulls the site blocklist when `blocklistVersion` changes (merged into the rules, never shown in our settings). Site down: back-off 3 s -> 30 s, everything keeps working locally. Site mod events (skip, remove, open, close, pause, resume) are handled; block/unblock arrive via the blocklist; request events honour the sub/vip/staff flags. Upvotes are counted and shown but do not reorder the queue.

**Key vault:** `SPOTIFY_API_KEY` is declared in `module.json` (`secrets`, test = `POST /api/test-key`) and read from the core vault with the module token (memory only, re-fetched after a 401). The key field in config.json remains an old-style fallback. Manifest also sets `singleton: true` (one instance: the master device).

**Defaults:** requests ship **closed** (`requests_open: false`); a mod opens them with `!sr open`, the UI toggle or the site. Skip works while closed. `/api/chat-command` accepts `silent:true` (ok, empty `say`; implies source "voice") and `source`; skip/blocksong are logged to the Console with that source (e.g. voice).

## Offline end-to-end trial
`python Suite/modules/spotify/tests/e2e.py` runs the REAL server against a fake Spotify and a fake site (tests/fakes.py, ~148 checks: OAuth PKCE, JIT push, skip, controls, chat/Host/voice commands, rules, approval, stream-safe, error states, token refresh/revocation, site bridge, restart persistence). `tests/demo.py` starts the same fakes with a seeded queue to look at the UI. Test-only env: SPOTIFY_API_BASE, SPOTIFY_ACCOUNTS_BASE, SPOTIFY_TICK_S, SPOTIFY_NO_BROWSER.

**Stream hooks:** `on_offline` closes song requests; `on_live` never opens them. The queue shows an ETA per song and `!sr` replies "plays in ~N min".
