# PinguinoMulti — Contracts (v0)

## ChatMessage
`id` `platform:channel:native_id` (stable; dedupe key) · `platform` · `channel` · `user_id` · `user` (login) · `display` · `text` · `ts` (epoch s) · `badges[]` · `reply_to` (id of parent message or "") · `reply_to_user` · `first_time` · `is_self` · `is_bot` · `raw_type`.

## PriorityDecision
`score` number · `tier` none|low|medium|high · `reasons[]` = `{rule, points, detail}`. Sum of points == score. Same inputs give the same output.

## Card
`id` `c:<message_id>` · `message_id` · `platform` · `user` · `text` · `score` · `tier` · `reasons[]` · `context[]` · `state` open|answered|missed|snoozed|dismissed · `created` `updated` `answered_at` `answered_via` (typed|platform_reply|mention|manual|click|hotkey|streamdeck|voice) · `snooze_until` · `faded`.

## Events on `/ws`
`hello{connectors,cards}` · `message{message+score,tier,reasons}` · `card.new|card.update{card}` · `conn.status{platform,...}` · `layout.changed`.

## REST (localhost)
`GET /api/status, /api/messages, /api/search?q=, /api/cards, /api/rules, /api/settings, /api/windows, /api/monitors, /api/profiles` ·
`POST /api/cards/{id}/{answer|dismiss|snooze|reopen|tier}` · `POST /api/send {platform,text,reply_to?,card_id?}` (one platform, never broadcast) · rules/settings save + reset · window CRUD/launch/restore · profile apply/save · `GET /auth/callback`, `POST /auth/token`.

## Site "Connect Multi" (built, site commit; needs deploy + live test)
Start: owner logged in on the site opens `/auth/twitch/login?multi=1` (broadcaster+staff only, else `/?multi=denied`). Scopes `user:read:chat user:write:chat`. It reuses the existing Twitch redirect URI, so **no new Twitch app redirect is needed**. After approval the site redirects to `http://127.0.0.1:8766/auth/callback#access_token&refresh_token&client_id&site_url` (fragment, nothing stored on the site). Refresh: `POST {site}/api/multi/refresh {refresh_token}` -> `{access_token, refresh_token, client_id}`; rejects any Origin header, and refuses tokens not belonging to the owner. The Multi launcher has a Connect Twitch link and a Disconnect button.

## Connection checks (in the launcher: "Run checks")
`GET /api/checks` -> `{checks:[{id,label,ok,detail,fix}]}`: keyring, site reachable, Connect link asks for `user:read:chat user:write:chat`, `/api/multi/refresh` deployed, token saved, token valid, scopes, chat connection. Never returns token values. `POST /api/open-connect` opens the Connect URL in the default browser (works from embedded/native shells).

## Bots (planned, M4)
Multi publishes `multi.claim {messageId,userId,ttl}`; Router (`Shared\PinguinoBots.cs.txt` + `sync-shared.mjs`) holds PinguinoChat while a claim is active (default off). Loop guard: Multi tags its sent ids and ignores `bot_accounts`.

## Learning v1
`GET /api/learning` -> `{enabled, min_evidence, rules:{rule:{delta,evidence,net,n,cap}}, applied}`; `POST /api/learning/reset`; `POST /api/learning/enabled {enabled}`. Evidence from the `events` log: answered +1, dismissed -1, missed -0.5, manual tier up/down +-1; 14-day half-life; a rule needs 5+ actions before it moves; delta clamped to 30% of the rule's default weight (max 12). Deltas are stored in kv `learned` and added by the scorer as part of each reason's points, so explanations still sum to the score. Reset ignores older events.

## Streamer-first claims (M4, Multi side)
`GET /api/claims` -> `{ttl_s, claims:[{message_id, platform, user_id, tier, expires}]}` — open medium/high cards for `claim_ttl_s` (default 20 s). Read-only. A bot/Router that wants "streamer first" polls it and holds off on those message ids until `expires`. The Router-side hook (`Shared\PinguinoBots.cs.txt` + `sync-shared.mjs`) is Unit 04's/owner's change and not made here.

## Voice suggestions (M4)
Opt-in (`voice_enabled`, default off). ASR (Listen) POSTs transcript text to `/api/voice/transcript`; Multi emits `reply.suggested {card_id, confidence}` (keyword overlap, threshold 0.5). It never closes a card; `POST /api/voice/confirm/{card_id}` marks it answered via `voice`. No audio or transcript is stored. Not verified: wiring to Listen's live transcript stream.

## Unified Chat page, popout, dashboard (2026-10-19)
- **Chat page**: `http://127.0.0.1:8766/?type=chat` (also window type `chat`, layout "Combined Chat"). Badges, name colours, Twitch emotes, mention highlight, mod/VIP/sub chips, per-platform filter chips, search (`/api/search`), pins (`GET/POST /api/pins`, event `pins.changed`), reply to ONE platform, priority-card strip.
- **Quick mod actions** (Twitch only): `POST /api/mod/{timeout|ban|delete}` `{message_id, seconds?}`; calls Helix directly with Multi's own token and needs scopes `moderator:manage:banned_users` (timeout/ban) and `moderator:manage:chat_messages` (delete). Without them the buttons are hidden and the call answers 502 "reconnect Twitch with moderator permissions". Every action is audited (store event + Console `mod` source). Host exposes no moderation HTTP API today; if 02 adds one, Multi can switch provider.
- **Popout / OBS**: `GET /popout?platforms=twitch,youtube&size=22&max=14&bots=show` - transparent, public chat only (no cards/notes/scores/composer/muted users, bots hidden by default).
- **Dashboard**: `GET /api/dashboard` -> `{rate_per_min, last_minute, series_15m[15], messages_last_hour, unique_chatters_hour, top_chatters[{user,platform,messages}], by_platform, open_cards}` (bots excluded from top chatters).
- **Aux device feed**: `GET /api/feed?since=<epoch>&limit=` returns `{ts, messages[]}` for the master to serve over Link. Not wired as a client yet (master/aux design is with Units 01/04; Multi's loopback-Host guard also has to allow the Link address).
- Kick is not built (needs a public webhook; decision pending).

## Chat look + stream events (increment 1, 2026-10-19)
- `GET/POST /api/chatstyle` (`{style}`, validated by `chatstyle.py`: fonts from a fixed list, #rrggbb colours, clamped numbers), `POST /api/chatstyle/reset`; WS event `chatstyle.changed`. Stored in settings.json (`chat_style`). The browser compiles it into one stylesheet (`static/style.js`), so busy chat costs nothing extra per message. Editor: `/?type=style` (live preview, auto-save). Precedence: base < platform < role < event < keyword.
- Messages carry `event` (`sub resub gift cheer raid follow redeem highlighted announcement`), `amount`, and `flags` (`new` = never seen by Multi, `returning` = back after more than `ding_session_gap_h` hours). Twitch `channel.chat.notification` (sub/resub/gift/raid/announcement) is subscribed next to chat messages; cheers (bits) and channel-point highlights come from the chat message itself. Events are stored and shown, never ranked, dinged or turned into cards.
- **For Host (02): `POST http://127.0.0.1:8766/api/events`** with the Multi module token (Authorization: Bearer / X-Pinguino-Token) and `{"type": "follow|redeem|sub|resub|gift|raid|announcement", "platform": "twitch", "user": "Name", "text": "optional", "amount": 0}` to show follows and channel-point redeems (Multi's own Twitch scopes cannot read those).
