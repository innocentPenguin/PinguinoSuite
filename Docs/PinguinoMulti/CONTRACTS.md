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
