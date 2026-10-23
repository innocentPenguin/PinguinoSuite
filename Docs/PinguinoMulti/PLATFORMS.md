# PinguinoMulti — Platform feasibility

Status: Twitch implemented; others are researched from prior knowledge and **must be re-verified against live docs before coding**.

| Platform | Read | Send/reply | Auth | Label |
|---|---|---|---|---|
| Twitch | EventSub WS `channel.chat.message` (`user:read:chat`) | Helix `POST /chat/messages`, `reply_parent_message_id` (`user:write:chat`) | OAuth + refresh via site | Official — **built** (untested with a live token) |
| YouTube | `liveChat.messages` polling/stream, quota-heavy | `liveChatMessages.insert`, no threads | Google OAuth (sensitive scopes) | Official, M3 |
| Kick | Official API + webhooks (needs public URL) or Pusher WS | chat send via OAuth | Kick OAuth PKCE | Official/UNOFFICIAL fallback, M3 |
| Discord | Gateway bot, MESSAGE_CONTENT intent | send/reply | bot token | Official, M3 |
| TikTok | no official LIVE chat API | none | n/a | UNOFFICIAL, read-only, off by default, M4 |

Rules: connectors declare capabilities; UI never offers what a platform cannot do; ids are `platform:channel:id`; one reader per platform.

---

# Research pass, 2026-10-23 (worker 42, verified against live docs)

Everything below was fetched on 2026-10-23. "Not verified" marks what the docs did not state. This replaces the "researched from prior knowledge" status of the table above.

## Kick (official API)
Sources: https://docs.kick.com/getting-started/generating-tokens-oauth2-flow , /getting-started/scopes , /events/event-types , /events/subscribe-to-events , /events/webhook-security , /events/introduction , /apis/chat , /apis/channels

- **App registration**: Kick account Settings -> Developer tab -> create app (client id + client secret; you set the redirect URI and optionally the webhook URL). The OAuth page only says "Kick Apps Setup page"; the exact click path is not documented there.
- **OAuth 2.1 authorization code + PKCE (S256)**. OAuth host is `https://id.kick.com` (not the API host). Authorize: `GET /oauth/authorize?client_id&response_type=code&redirect_uri&scope&state&code_challenge&code_challenge_method=S256` (`state` required). Token: `POST /oauth/token` form `grant_type=authorization_code, code, client_id, client_secret, redirect_uri, code_verifier`. Refresh: same endpoint, `grant_type=refresh_token, refresh_token, client_id, client_secret`; the response carries a NEW refresh token, store it. App token: `grant_type=client_credentials` (public data only). Revoke `POST /oauth/revoke`, introspect `POST /oauth/token/introspect`. The client secret is still sent, so it lives in Credential Manager, never in git. Token lifetimes are not stated (`expires_in` in the response).
- **Scopes (complete list)**: user:read, channel:read, **channel:write** (livestream metadata), channel:rewards:read, channel:rewards:write, **chat:write**, streamkey:read, **events:subscribe**, moderation:ban, moderation:chat_message:manage, kicks:read, ads:read, ads:write.
- **Send chat**: `POST https://api.kick.com/public/v1/chat`, JSON `{content (<=500 chars and <=2048 bytes), type: "user"|"bot", broadcaster_user_id (required when type=user), reply_to_message_id (uuid, optional)}`; scope `chat:write`; 200 -> `{is_sent, message_id}`. `type:"bot"` posts from a bot account into the channel attached to the token.
- **Set title/category**: `PATCH https://api.kick.com/public/v1/channels`, `{stream_title, category_id (int), custom_tags[<=10]}`, scope `channel:write`, 204 on success (this is what stream_info.kick_update needs).
- **Webhooks** are the only official event transport: `POST /public/v1/events/subscriptions` accepts `method: "webhook"` only (no websocket). Types, all v1: `chat.message.sent, channel.followed, channel.subscription.renewal, channel.subscription.gifts, channel.subscription.new, channel.reward.redemption.updated, livestream.status.updated, livestream.metadata.updated, moderation.banned, kicks.gifted`. Subscribing needs `events:subscribe` (GET list / POST create / DELETE by id). Limits: 10,000 subs per event type; unverified apps are capped at 1,000 for chat.message.sent.
- **Signature**: headers `Kick-Event-Signature` (base64), `Kick-Event-Message-Id`, `Kick-Event-Message-Timestamp`, plus `Kick-Event-Type` / `Kick-Event-Version`. Signed string = `<message-id>.<timestamp>.<raw body>`; RSA PKCS#1 v1.5 + SHA-256; fetch the PEM at runtime from `https://api.kick.com/public/v1/public-key` (it can rotate). `connectors/kick.py verify()` already does exactly this.
- **Public URL**: required. The webhook URL goes into the app's "Enable Webhooks" box (Developer tab). Localhost does not work; Kick suggests Cloudflare Tunnel or ngrok. Retry / auto-unsubscribe on failure: not documented (our endpoint answers 200 for ignored events on purpose).
- **Works without a public URL**: (a) the unofficial Pusher read feed in kick.py (chat only, no login); (b) outgoing REST calls: send chat, set title, list subscriptions. Follows, subs, gifts and KICKs need the webhook, i.e. the site relay (`/hook/kick` forwarded to Multi) or a tunnel.

## YouTube Data API v3 live chat
Sources: https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list , .../insert , https://developers.google.com/youtube/v3/determine_quota_cost , https://developers.google.com/identity/protocols/oauth2/native-app , https://developers.google.com/identity/protocols/oauth2#expiration

- **Quota**: default 10,000 units/day per Cloud project, reset at midnight Pacific. `liveChatMessages.list` = **5**, `.insert` = **20**, `liveBroadcasts.list` = 1, `videos.list` = 1. `search.list` has its own 100 calls/day bucket; do not use it to find the stream.
- **Polling math**: 10,000 / 5 = 2,000 list calls per day. At a 6 s interval that is about 3.3 h of chat per day (2.8 h at the 5 s floor we use today). A 5 h stream does NOT fit unless the interval is stretched (10 s -> 5.5 h) or Google grants a quota extension. Each sent message costs 20 (50 messages = 1,000 units). Recommendation: poll at max(`pollingIntervalMillis`, 10 s) while live, stop on `liveChatEnded` / `offlineAt`, show the day's spent units in the UI. `liveChatMessages.streamList` (streaming) exists but its docs page returned 404 for me: quota and availability **not verified**.
- **list**: `liveChatId` (from `liveBroadcasts.list` `snippet.liveChatId`), `part` = id|snippet|authorDetails, `maxResults` 200-2000 (default 500), `pageToken` = previous `nextPageToken`; `pollingIntervalMillis` in the response is the minimum wait. Errors: `liveChatEnded` (403), `liveChatDisabled` (403).
- **Scopes**: `insert` accepts `youtube` or `youtube.force-ssl`. The list page does not name scopes (so whether `youtube.readonly` alone works is **not verified**). Ask once for `https://www.googleapis.com/auth/youtube.force-ssl`: it covers read, send and the title/schedule edits in stream_info.
- **Installed-app flow**: auth `https://accounts.google.com/o/oauth2/v2/auth`, token and refresh `https://oauth2.googleapis.com/token`, revoke `https://oauth2.googleapis.com/revoke`. Redirect = loopback `http://127.0.0.1:<port>`; out-of-band copy/paste and custom URI schemes are no longer supported. Always PKCE (S256). Refresh tokens are always returned for installed apps; add `access_type=offline` (the page does not mention it; harmless). `client_secret` is optional in the exchange per the page; Desktop clients are issued one anyway, keep it in Credential Manager.
- **Refresh-token gotchas**: a Cloud project in **Testing** status with external users -> refresh token expires after **7 days** (fix: publish the consent screen to "In production"; as a sensitive-scope app it stays "unverified" with a warning screen and a 100-user cap, fine for one person). Unused for 6 months -> dead. 100 refresh tokens per account per client id (oldest silently invalidated). Revoked access, or a password change with Gmail scopes -> `invalid_grant`, Ivan must consent again.

## TikTok LIVE (TikTokLive library, unofficial)
Sources: https://github.com/isaackogan/TikTokLive , https://pypi.org/project/TikTokLive/

- **Version**: PyPI latest **7.0.1** (2026-09-10); 7.0.0 2026-08-18; Python >= 3.10; licence **modified AGPL-3.0** (read LICENSE before ever distributing Multi; private use is fine).
- **Login**: none. Connect with only the creator's `@unique_id`; the stream must be live (offline -> connect error, our loop retries).
- **Sign server**: requests are signed by a third-party signature server, default **Euler Stream**; `tiktok_sign_url` swaps it; an Euler API key is optional and lifts rate limits. README: "not a production-ready API", reverse-engineered; Euler's paid WebSocket API is the recommended production route.
- **Events** (`TikTokLive.events`): `CommentEvent`, `GiftEvent` (streakable gifts: `streaking` / `repeat_count`, count only when the streak ends), `FollowEvent`, `ShareEvent`, `LikeEvent` (batched counts), `SubNotifyEvent` (subscribe / renew / gift sub), `SuperFanEvent`, `RoomUserSeqEvent` (viewers). There is **no `SubscribeEvent`** in the README, so the `hasattr(tev, "SubscribeEvent")` guard in tiktok.py never registers a sub listener (fixed in item 3). Class names move between releases: always `getattr`.
- **Risks**: TikTok ToS, breaks without notice when the protocol changes, depends on the sign server, AGPL, gifts are coins/diamonds not money, no sending possible. Keep OFF by default and never let it block the other platforms.

## What Ivan must provide (one page)

| # | What | Why | Recommended default |
|---|---|---|---|
| 1 | **TikTok @handle** and a yes to installing TikTokLive 7.0.1 into the Multi venv | comments, gifts, follows, shares, likes | yes; handle goes in setting `tiktok_user`; AGPL is fine for private use |
| 2 | **Kick developer app** (Settings -> Developer): redirect URI `http://127.0.0.1:8766/auth/kick/callback` (or what the launcher UI shows), scopes `user:read channel:read channel:write chat:write events:subscribe`; client id into config, secret into Credential Manager (he enters it himself) | send chat, set title/category, official events | create it; webhook URL = site relay `https://<site>/hook/kick` once the site exposes it |
| 3 | **Kick channel slug + numeric chatroom id** | unofficial read feed | slug in `kick_channel`; id from `kick.com/api/v2/channels/<slug>` once |
| 4 | **Google Cloud project**: enable YouTube Data API v3, consent screen **published to production** (not Testing), OAuth client type **Desktop app**; client id into config, secret into Credential Manager | a refresh token that does not die after 7 days | do exactly this and accept the "unverified app" warning |
| 5 | **YouTube quota decision** | 10,000 units/day = ~3 h of 6 s polling | poll >= 10 s while live (~5.5 h/day); request a quota extension only if streams run longer |
| 6 | Click **consent** himself for Kick and YouTube (I only build the URLs) | hard rule | launcher buttons |
| 7 | Public URL for Kick webhooks (site relay or tunnel) | follows / subs / gifts / KICKs from Kick | site relay |

## Config fields per platform (for the launcher UI; item 4, 2026-10-23)
Settings live in `config.DEFAULTS` / `config.save_settings` (flat keys, only keys present in DEFAULTS are saved) and in the server.py settings allowlist. Keys marked NEW must be added to both by whoever owns them (the connectors already read them with safe defaults). Secrets are never settings: they go to Credential Manager (service `PinguinoMulti`, `secrets_store.put`) and the UI only shows set / not set.

| Platform | Settings keys (type, default) | Secrets (Credential Manager names) | Written by sign-in |
|---|---|---|---|
| Twitch | `channel` (str), `twitch_client_id` (str) - existing | `twitch_tokens` (site "Connect Multi") | - |
| Kick | existing: `kick_enabled` (bool, false), `kick_channel` (slug), `kick_chatroom_id` (digits). NEW: `kick_client_id` (str ""), `kick_redirect_uri` (str "http://127.0.0.1:8766/auth/kick/callback"), `kick_scopes` (str, default "user:read channel:read channel:write chat:write events:subscribe") | `kick_client_secret` (Ivan enters) | `kick_token`, `kick_oauth` |
| YouTube | NEW: `youtube_client_id` (str ""), `youtube_redirect_uri` (str "http://127.0.0.1:8766/auth/youtube/callback"), `youtube_min_poll_s` (number, 10; quota guard, 5 units per poll) | `youtube_client_secret` (Ivan enters) | `youtube_token`, `youtube_oauth` |
| TikTok | existing: `tiktok_enabled` (bool, false), `tiktok_user` (@handle, with or without @). NEW (optional): `tiktok_sign_url` (str "" = default Euler Stream sign server) | - | - |
| Discord | existing: `discord_channels` (list of ids) | bot token | - |

Routes for the launcher (file `platform_api.py`; one line in server.py: `import platform_api` + `app.include_router(platform_api.router)`): `GET /auth/{kick|youtube}/status` -> `{client_id_set, client_secret_set, signed_in, can_refresh, expires_at, scope, redirect_uri}`; `POST /auth/{p}/start` -> `{ok, url}` (UI opens `url` in the browser; Ivan clicks consent himself) or `{ok:false, error}`; `GET /auth/{p}/callback` is where the platform redirects (returns a small "signed in" page). Redirect URIs must match the ones registered in the Kick app / Google Desktop client exactly (Google accepts any 127.0.0.1 port for Desktop clients).

### Behaviour with no token (audit)
- `viewers.py`: no token -> that platform simply has no count (dash in UI), no HTTP call, no log. A failing call now logs one warn line per 30 min per platform (before: swallowed silently).
- `stream_info.py`: no token -> `{"connected": false, "error": "..."}` with no network call, no log.
- `connectors/*`: retry loops (`needs_auth` every 10-30 s) used to emit a `conn.status` event on every pass; `Connector.set_status` now suppresses identical repeats (heartbeat every 30 s) and still logs only on a change.

## Status 2026-10-23 (end of day)

| Item | State |
|---|---|
| Kick/YouTube **Connect cards** | Built: `static/connect.js` (one include in `index.html`) adds a card per platform to the launcher: client id + secret fields (id -> settings, secret -> Credential Manager via `POST /auth/<p>/client`, never echoed back), status text, "Sign in" button that opens the consent URL in a new tab. Ivan clicks consent himself. Proven on a throwaway server (`tests/e2e_connect.py`): callback GET passes the origin/token middleware, POSTs need same-origin. Needs a Multi restart to appear. |
| Kick chat **send** + stream **title** | Built (`chat:write` / `channel:write`); `send` capability only shows once a token with `chat:write` exists. |
| Kick **webhook relay** (site mailbox) | Multi side built: `connectors/kick_relay.py` (`to_webhook`, `replay`, `pull_once`; re-verifies Kick's RSA signature through `Kick.ingest_webhook`, dedupes by message id, never advances past a transient failure). Site side (receive + `GET /api/bot/kick/events?since=`) is NOT built; contract is in the side-session note `40-kick-webhook-relay.md`. No Multi poller yet by decision: wire `pull_once` to a timer only when the site route exists. `POST /hook/kick` on Multi still works for a tunnel. |
| TikTok | Adapter built and tested with mocks; TikTokLive is NOT installed (waits for Ivan's yes). |
| Failure modes | YouTube: 401 -> `needs_auth`; 429 / 403 quota -> back off 2-10+ min (honours `Retry-After`, cap 1 h); network down / bad JSON -> retry 20 s. Kick: bad websocket frames skipped, bad channel lookup is a clean error. TikTok: any error -> retry 30 s. Covered in `tests/test_connectors.py`. |
| Cards | `cards.py` hardened for odd stored cards, NaN scores and concurrent reads (`tests/test_cards_fuzz.py`). |
