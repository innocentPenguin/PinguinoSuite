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

## Bots (planned, M4)
Multi publishes `multi.claim {messageId,userId,ttl}`; Router (`Shared\PinguinoBots.cs.txt` + `sync-shared.mjs`) holds PinguinoChat while a claim is active (default off). Loop guard: Multi tags its sent ids and ignores `bot_accounts`.
