# PinguinoMulti configuration reference (generated from config.py and the code)

## Environment variables

| Variable | Used by | What it does |
|---|---|---|
| `MULTI_PORT` | config.py | Port Multi listens on (default 8766). |
| `MULTI_DB` | config.py | SQLite file (default `<data>/multi.db`). Point it at a temp file for throwaway servers. |
| `PINGUINO_DATA_DIR` | config.py, console_log.py, alerts.py, scene_follow.py, alert_media.py | Folder the Suite gives every module; Multi keeps its data in `<that>/multi`. Unset = a `data` folder next to the code. |
| `PINGUINO_CORE_URL` | server.py, vault.py, ding.py | Suite core (default `http://127.0.0.1:8760`): key vault and sounds. Not `CORE_URL`: that name does nothing. |
| `PINGUINO_API_TOKEN` | server.py, vault.py, host_feed.py, intros.py, ding.py | This module's token from the Suite. Set = writes need it; unset = standalone, origin check only. Never logged. |
| `PINGUINO_MODULE_TOKEN` | host_feed.py | Token used when Multi asks the Host to say a line; falls back to `PINGUINO_API_TOKEN`. |
| `MULTI_HOST_URL` | host_feed.py, intros.py | Where the Host listens (default `http://127.0.0.1:8770`). Rehearsals point it at `scripts/fake_host.py`. |
| `MULTI_NO_SEND` | connectors/base.py, host_feed.py | `1`/`true`/`yes`/`on`: every connector and the Host say path refuse to send. Use on every test server. |
| `MULTI_NO_KEYRING` | secrets_store.py | Set: never touch Windows Credential Manager (test servers start with an empty vault). |
| `MULTI_CONSOLE_FILE` | console_log.py | Override the console log file (default `<data>/console/multi.jsonl`). |
| `MULTI_CLIP_EXTRA_HOSTS` | alerts.py | Comma list of extra http clip hosts allowed for shoutout clips. Rehearsal only. |
| `MULTI_TWITCH_TOKENS`, `MULTI_DISCORD_TOKEN`, `MULTI_YOUTUBE_TOKEN`, `MULTI_AI_KEY` | vault.py | Not environment variables: these are the NAMES of the secrets Multi reads from the Suite key vault (declared under `secrets` in the module manifest). |

Secret values (tokens, client secrets, API keys) live in the Suite key vault or Windows Credential Manager, never in settings files, logs or these docs.

## Settings keys (config.py DEFAULTS, editable in Setup or `POST /api/settings`)

Defaults for personal names (your channel, your own names, bot accounts) and sound file paths are left out on purpose; see `config.py`.

| Key | What |
|---|---|
| `channel` | - |
| `twitch_client_id` | - |
| `tiktok_enabled` | UNOFFICIAL, read-only; needs optional TikTokLive package |
| `tiktok_user` | - |
| `kick_enabled` | Kick: UNOFFICIAL read-only chat feed (public Pusher socket); official events come by webhook (POST /hook/kick) |
| `kick_channel` | channel slug |
| `link_url` | blank = http://127.0.0.1:7777 (Link): follow the OBS scene for alert profiles (scene_follow.py) |
| `feed_hype_alerts` | hype-train alerts from the Host activity feed (OFF: the Host fires them directly on /api/alerts/fire) |
| `intro_enabled` | play viewers' approved intros (Host) for first-time / returning chatters |
| `kick_client_id` | Kick developer app client id (secret goes to Credential Manager as kick_client_secret) |
| `kick_redirect_uri` | - |
| `kick_scopes` | - |
| `youtube_client_id` | Google OAuth Desktop-app client id (secret: Credential Manager youtube_client_secret) |
| `youtube_redirect_uri` | - |
| `youtube_min_poll_s` | liveChat poll floor: 5 quota units per poll of 10,000/day |
| `tiktok_sign_url` | optional own sign server for TikTokLive ("" = library default) |
| `kick_chatroom_id` | numeric chatroom id (kick.com/api/v2/channels/<slug> -> chatroom.id; pasted once) |
| `ding_platforms` | new-chatter ding: platforms it is ON for (twitch, youtube); empty = off |
| `ding_first_ever` | Twitch "first message ever" gets its own (optional) sound |
| `ding_sound` | = Streamer.bot "First TIme System (Bell)" sound |
| `ding_first_sound` | brand-new chatter (first message ever) |
| `ding_returning` | a different ding for someone who chatted in an earlier stream |
| `ding_returning_sound` | = Streamer.bot "chat (first time today)" at 50 % |
| `ding_returning_volume` | - |
| `ding_master_volume` | multiplies both ding volumes |
| `ding_volume` | Streamer.bot used 0.24 |
| `ding_scope` | stream = once per person per stream; ever = once per person, forever (Streamer.bot bell) |
| `ding_cooldown_s` | - |
| `ding_session_gap_h` | - |
| `pop_platforms` | chat pop (a sound on every message): platforms it is ON for; empty = off |
| `pop_sound` | = Streamer.bot "chat" / "chat (yt louder)" |
| `pop_volume` | Streamer.bot: 0.5 Twitch, 0.76 YouTube |
| `pop_cooldown_s` | - |
| `pop_roles` | chat pop only for these roles (mod, vip, sub, viewer); empty = everyone |
| `pop_own` | also pop for my own messages |
| `chat_style` | chat look (fonts, backgrounds, highlights); None = defaults, see chatstyle.py |
| `discord_channels` | channel ids Multi reads/sends in (bot token is in Credential Manager) |
| `priority_mode` | local / ai / auto  (AI arrives in M3; local always works) |
| `ai_provider` | anthropic / openai / ollama (key in Credential Manager as ai_key) |
| `ai_model` | - |
| `ai_daily_cap_usd` | - |
| `ai_timeout_s` | - |
| `ai_margin` | only ask AI when the local score is within this of a tier threshold |
| `host_feed_enabled` | show Host follows / channel point redeems as event rows in chat |
| `voice_enabled` | opt-in: suggest cards answered out loud (never auto-closes) |
| `claim_ttl_s` | how long a streamer-first claim holds the bots back |
| `answered_fade_s` | - |
| `missed_after_s` | - |
| `max_cards` | - |
| `retention_days` | - |
| `bot_accounts` | - |
| `my_names` | - |
