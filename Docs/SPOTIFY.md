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
GET `/api/state`, `/api/overlay.json`, `/api/search?q=`, `/api/devices`, `/api/player`, `/api/player-token`, `/api/setup`, `/api/prestream`, `/api/status` (health). POST `/api/queue/{add|remove|move|play_next|play_now|clear|undo|start}`, `/api/control {action: play|pause|next|previous|seek|volume|transfer, value}`, `/api/settings`, `/api/inbox/{id}/{approve|deny}`, `/api/blocklist`, `/api/player/status`, `/api/setup`, `/api/auth/start`, `/api/disconnect`.

## Built-in player (native playback, no Spotify desktop app)
Spotify plays inside Pinguino as the Connect device **PinguinoSuite**, using the Spotify Web Playback SDK in the page `http://127.0.0.1:8771/player` (open it from Setup > Built-in player > *Open player window*, or keep it in a pinned window/tab; the Host/app can load it in a hidden WebView2).
- **Needs:** Spotify Premium and a Widevine-capable host (Edge/Chrome/WebView2 with DRM). The page loads `https://sdk.scdn.co/spotify-player.js` (internet).
- **Re-auth once:** scopes now include `streaming` and `user-read-email`. Existing logins lack them: Setup > Connect again. Until then `/api/player-token` answers 409 `NEEDS_REAUTH` and the card says so.
- **Token:** `GET /api/player-token` -> `{access_token, expires_in}`. Refused (403) for cross-site/foreign-origin/bad-Host requests; a non-browser caller needs `PINGUINO_API_TOKEN` (401 otherwise); `Cache-Control: no-store`; never logged, never in `/api/player`, `/api/state` or the Console.
- **Selection:** the page heartbeats `POST /api/player/status {device_id, state, error, sink_ok, sink_note}` every 5 s (live = report < 20 s old). While live, the engine transfers playback to it when it is not the target (checked every 6 s once Spotify lists the device), starts the queue/background playlist on it, and keeps the JIT queue logic unchanged. If the streamer picks another device by hand (`/api/control transfer`), auto-selection pauses for 10 min. Setting `player_native` = off disables all of this.
- **Own volume:** setting `player_volume` (0-100; UI box, `!volume`, `/api/control volume`) is applied by the page with `player.setVolume`, independent of the Spotify app and the Windows master. `GET /api/player` returns the full player state (state, live, active, volume, sink, needs_reauth).
- **Separate output (limit):** the page lists outputs (`enumerateDevices`/`selectAudioOutput`), saves the choice (`player_sink`, `player_sink_label`) and tries `setSinkId` on reachable media elements. The SDK plays in a cross-origin iframe, so this usually **cannot** be applied, and the page then shows "not applied". There is one audio element, so **no second "monitor" output / stream-vs-monitor mix is possible**. Reliable routes: Windows Settings > Sound > Volume mixer (per-app output for the player window/WebView2) to a virtual cable for OBS, or capture the player window as an OBS source (per-source volume and monitoring in OBS).
- **Unverified (browser-side, needs a real run with Premium):** SDK load and Widevine playback in WebView2, device appearing in Spotify's list, autoplay unlock (the *Enable audio* button), `setVolume`, and any `setSinkId` effect. Offline tests cover only the token guard, device selection/transfer logic, manual-override hold, volume storage and status handling (fake Spotify).

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

## Personalization (Settings tab, generated from `config_schema.py`)
Every setting has a default, a label and a one-line help; edited ones show an "edited" tag and a reset arrow. Groups: who can request (open, mods/subs only, stream-safe, approval and who needs it, queue size, links/names allowed), limits per role (viewer / sub / VIP overrides, mod bypass, cooldowns, per-artist cap), songs (min/max length incl. a sub max, explicit, replay cooldown, blocklists), order and priority (fair queue on/off, sub and redeem priority), skipping, chat wording, playback/text file, OBS overlay look. **Chat wording:** command prefix, per-command word lists (`cmd_aliases`, eg add `tune` for !sr; Host's `command` field follows them), `reply_prefix`, and 36 reply templates (`msgs`) with `{user} {song} {title} {artist} {pos} {eta} {limit} {votes} {need} {link} {by} {mine} {last} ...`; empty = silent; unknown placeholders render empty). Extra commands: `!lastsong`, `!mysongs`, `!songhelp`. **Presets:** relaxed, balanced, strict, subs, mods, safe, closed (never open/close requests except "closed"). Export/import JSON, partial/full reset (`POST /api/settings/reset {keys?}`), `POST /api/preset {name}`, `GET /api/settings/schema`, `POST /api/msgs/preview {template}`. Invalid values are ignored and keep the old setting. Overlay: `ov_theme dark|light|glass|minimal`, accent colour, width, size, radius, font, show art/requester/progress, hide when paused; query overrides `?theme= &accent= &art=0 &width=`.

## Cycle 1 additions
Schedule (open/close requests at set times and days, transitions only so manual toggles win in between), background playlist when idle and nothing is queued (only while requests are open by default), autostart of the queue when idle, per-viewer per-stream request cap, queue length cap in minutes, priority and trusted viewer lists, auto-skip of blocklisted (or explicit in stream-safe) songs that start playing from any source, volume min/max and mod `!volume [n|+n|-n]`, mod `!playnext <song>`, queue Shuffle and "Remove viewer…", Stats (top requesters, repeat songs, this stream), `nowplaying.json` and optional `queue.txt` for OBS/Streamer.bot, keyboard shortcuts (space play/pause, n next, p previous). Bug fixes: keep-alive no longer poisoned by a refused POST with a body; a 204 blip between songs no longer drops the previous song from history.

## Cycle 2 additions
Genre blocklist (`block_genres`, matched against the artist's Spotify genres, cached, lookup failure = allow, broadcaster exempt), add a whole playlist/album to the queue (Search tab; `POST /api/queue/add_context {link, shuffle, limit}`; needs the playlist scopes, so reconnect once if the first login predates them), your own saved presets ("＋ Save mine", also applied via `/api/preset`), overlay request alerts (`ov_alerts`, `ov_alert_s`), mod `!sr safe on|off`, 2-minute search cache (protects Spotify's rate limit during chat bursts), clear error when port 8771 is already taken.

## Cycle 3
Quiet handling of dropped keep-alive connections (no tracebacks in the Console; idle connections time out after 30 s). Optional chat announcements: `announce_track_on` / `announce_request_on` (off by default) queue lines that the Host polls with `GET /api/announcements?since=<seq>` -> `{seq, lines:[{seq, ts, text}]}` and posts to chat (we have no chat connection of our own); wording is editable (`announce_track`, `announce_request` templates).

## Cycle 4: Songify parity (see `Docs/SONGIFY_PARITY.md`)
New settings (Settings tab, all in `config_schema.py`):
- `chat_requests` (default on): turn off for reward-only requests; chat `!sr` then answers with the `reward_only` message. Redeems via `/api/chat-command` still work.
- `refund_on` (list of `none, too_long, full, lookup, offline, limit, blocked`): when a redeem is rejected with one of these codes, `/api/chat-command` returns `"refund": true` and the reply uses the `refunded` message. The Host's redeem automation must act on that field (the Host has no `channel:manage:redemptions` scope yet).
- `global_cooldown_s` (default 0): minimum seconds between any two requests; staff bypass.
- `clear_on_offline` (default off): viewer requests are cleared when the stream goes offline.
- `playlist_add`: playlist ID or URL; accepted requests are also added there. Needs the new playlist scopes, so reconnect Spotify once.
- `cmd_roles`: lines like `skip=moderator,vip` to limit who may use a command (broadcaster always allowed); denied users get `cmd_denied`.

New commands (all renamable): `!songpos` / `!pos`, `!songnext` / `!next`, `!songlike` / `!like` (staff; saves the playing track, needs `user-library-modify`), `!togglesr` (staff), alias `!songban` on blocksong, `!songcommands` on help.

New endpoints: `POST /api/blocklist/import` (text of bare 22-char track IDs or URIs, one per line, `#` comments; returns `{added,total}`), `GET /api/queue.json` (public queue, no IDs or URIs), pages `/queue` and `/overlay/queue` (OBS widget; query `?count ?theme ?accent ?width ?size ?eta ?now`).

Not done yet: synced lyrics widget, sub-tier or follower request caps, paying with pengs, public exposure of `/queue` through the site.

## Request bans: !srban / !srunban
Mods and the streamer: `!srban <user>` stops that viewer from requesting (reply: "can no longer request songs", templates `ban_ok`/`unban_ok`/`ban_usage`); `!srunban <user>` lifts it. Stored in the `blocked_users` setting (persists across restarts, shown and editable in Settings -> Blocked viewers, returned by `GET /api/settings`). Banned viewers get the `user_blocked` reply on `!sr`. Site-pulled bans are kept separately and are not removed by `!srunban`.

## Cycle 5: song outcomes, bonus queues, sub tiers
- **Outcomes:** every history entry has `outcome` (`played` or `skipped`) and `skipped_by` (mod name, `vote`, `streamer`, or `spotify` when cut off with >20 s left). Songs withdrawn before playing (`!oops` = wrong song, mod block, denied from the inbox, removed while queued) go to a `rejects` log.
- **PinguinoBot feed:** `GET /api/song-log?limit=50&minutes=60` -> `now`, `recent` (with outcome), `lastHour` (what played in the last hour, to avoid repeats), `skipped` (per-song skip counts = not liked), `withdrawn`. `outcome` is also on the site history rows.
- **No repeats:** `dup_cooldown_min` (60) already blocks anything played in the last hour; new `skip_cooldown_min` (180) blocks songs that were skipped (reply `dup_skipped`).
- **Bonus queues:** extra request slots on top of `per_user_limit`: `bonus_t1/t2/t3` (defaults 2/3/4) for Tier 1/2/3 subs and `bonus_vip`; the best one applies. `limit_sub`/`limit_vip` still set an exact total. The old `sub_extra` migrates into all bonus settings.
- **Sub tier input:** `/api/chat-command` accepts `subTier` (1/2/3 or 1000/2000/3000) next to `isSub`; `/api/chat` accepts roles `sub_t1|sub_t2|sub_t3`. Plain `sub` = Tier 1. The Host must send the tier for T2/T3 to count.
