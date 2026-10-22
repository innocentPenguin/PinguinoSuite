# Multistream plan: Kick, YouTube, TikTok into PinguinoMulti

Owner: 03 (Multi). Status 2026-10-22: design + safe parts (normaliser, platform badge, read-only connectors) being built. **Nothing here starts a stream or touches OBS.** Multi only READS chat/events from the other platforms; sending video to them (the multistream output itself) is an OBS/restream matter and is out of scope here.

## What already exists
Twitch (EventSub, read + send), YouTube chat (official, read + send, needs a token, text messages only), Discord (bot), TikTok (unofficial `TikTokLive`, comments only, off by default, package not installed). Chat rows already carry `platform` and a platform marker; alerts flow `Pipeline.on_event -> alert engine`.

## Per platform

### Kick
- **Official:** public API `api.kick.com/public/v1`, OAuth 2.1 at `id.kick.com` (authorization code + PKCE, app needs client_id/client_secret from the Kick Apps page). Scopes needed for read: `user:read channel:read events:subscribe` (send later: `chat:write`).
- **Events are WEBHOOK ONLY** (`POST /public/v1/events/subscriptions`, `method:"webhook"`): `chat.message.sent`, `channel.followed`, `channel.subscription.new|renewal|gifts`, `kicks.gifted`, `channel.reward.redemption.updated`, `livestream.status.updated`, `moderation.banned`. Kick POSTs to a public HTTPS URL, signed (`Kick-Event-Signature`, RSA-SHA256 over `id.timestamp.body`, public key from `/public/v1/public-key`, never hard-coded), dedupe with `Kick-Event-Message-Id`. Unverified apps: 1000 chat subscriptions max (irrelevant for one channel). A webhook failing for a day gets unsubscribed.
- **Consequence:** Multi runs on 127.0.0.1, so Kick cannot reach it. Options, best first: (1) the website (Railway) receives the webhook and Multi pulls the queue from it (same pattern as the site's other relays); (2) a tunnel (Tailscale funnel through Link); (3) the unofficial path below.
- **Unofficial (read only, labelled UNOFFICIAL):** Kick's own site chat uses a public Pusher websocket (`chatrooms.<chatroom_id>.v2`, event `App\Events\ChatMessageEvent`). No login, no public URL needed, works from Multi directly. Needs the numeric chatroom id (looking it up from the channel name is behind Cloudflare, so Ivan pastes it once). Can break whenever Kick changes it; ToS grey (read-only, no scraping of accounts).
- **Built tonight:** `connectors/kick.py` (Pusher read-only + `/hook/kick` signed webhook receiver ready for option 1/2), normaliser for both payload shapes.

### YouTube
- **Official** Data API v3 `liveChat/messages` (polling; `streamList` is the low-latency stream variant, quota is shared with the project, default 10,000 units/day). Already read + send. Added: Super Chat / Super Sticker, new member, member milestone, gifted memberships become events (`cheer` with the money amount, `sub`, `resub`, `gift`), with `platform:"youtube"`.
- **Ivan's one-time step:** Google Cloud project + OAuth consent (YouTube scope `youtube.force-ssl`), then the token pasted in Multi's Settings (existing `/api/secrets/youtube`). Chat scopes are "sensitive": unverified apps work only for test users (Ivan's own account is fine). Access tokens last 1 h, so a refresh token flow is the next piece (not built; today the token is pasted).
- Follows do not exist on YouTube chat (subscribers are not in the chat API).

### TikTok
- **No official LIVE chat API.** Only reverse-engineered clients: Python `TikTokLive` (isaackogan; no login needed, needs `unique_id` of a LIVE host; 4.3.8+ required after TikTok changes, so it breaks often) and the Node `TikTok-Live-Connector`. Optional paid managed services exist; not used.
- **Risk:** violates TikTok's terms (automated access to an undocumented protocol); account-level action is possible in theory, though connecting read-only to your OWN live and never logging in is the lowest-risk form (it never posts, never uses your account cookie). It can stop working any day, and some versions need a third-party signing server (a data-leak consideration: only the username goes out). Kept OFF by default, labelled UNOFFICIAL, install is Ivan's decision (`pip install TikTokLive` into Suite\.venv).
- **Events mapped:** comment -> chat; follow -> `follow`; gift (coins/diamonds) -> `cheer` with meta `gift_name`, `coins`; subscribe -> `sub`; share/like are counters only (ignored for alerts). Streak gifts are deduped on the final streak event.

## One normalised shape
Everything becomes a `ChatMessage` (platform field) and, for stream events, `event` in the existing set (`follow sub resub gift cheer raid redeem`) + `amount` + `meta {platform, currency, gift_name, tier, months, avatar, ...}`, so the activity feed, the alert engine, stats and the pop-ups need no per-platform code. Ids are `platform:channel:native_id` (dedupe survives reconnects). Alerts get a `{platform}` variable and a small platform tag on the card.

| Source event | event | amount |
|---|---|---|
| YouTube superChatEvent / superStickerEvent | cheer | whole currency units, `meta.currency` |
| YouTube newSponsor / memberMilestone | sub / resub | months |
| YouTube membershipGifting | gift | count |
| Kick channel.followed | follow | |
| Kick subscription.new / renewal | sub / resub | months |
| Kick subscription.gifts | gift | giftees |
| Kick kicks.gifted | cheer | kicks |
| TikTok gift | cheer | coins |
| TikTok follow / subscribe | follow / sub | |

## How chat shows the platform
Existing marker (text/logo/both) per row; Kick (green) and the Kick logo are added to the marker settings; OBS chat already has Kick colours. Platform filter chips show Kick as soon as its connector is registered.

## What needs Ivan (one time, I never type or click these)
1. **Kick:** create a Kick app (kick.com developer page) only if the webhook route is wanted; otherwise just paste the numeric chatroom id into Settings (kick_chatroom_id) to use the unofficial read-only feed.
2. **YouTube:** Google Cloud project + OAuth consent, paste the token in Multi Settings.
3. **TikTok:** decide yes/no on the unofficial client; if yes, `pip install TikTokLive` and set tiktok_user + tiktok_enabled.
4. For the Kick webhook: pick relay (site on Railway) or tunnel; then subscribe once with his OAuth login.

## Order of work
1. Normaliser + tests, platform badge, Kick read-only connector, YouTube/TikTok event mapping (tonight).
2. Settings UI for the three platforms in the launcher.
3. Kick webhook relay through the site + subscription helper (needs Ivan's Kick app + a site change, separate repo).
4. YouTube refresh-token flow; TikTok gift streak handling live test.
