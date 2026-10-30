# Discord plan (170 - Discord, 2026-10-30)

What the PinguinoSuite should do in Ivan's Discord server (invite discord.gg/fktz5sq4b8), in phases. Each phase says what it needs from Ivan, what the default is, and which part of the suite owns it. Nothing here connects to Discord until Ivan provides the secret named in the phase; every feature has a visible "not configured" state until then.

## Where Discord stands today (read-only inventory, 10-28 + 10-30)

| Piece | State |
|---|---|
| Go-live / raid / customs posts | **New (Phase 1, commit 9de92d4)**: Host posts one webhook message per stream, edits it to "stream ended". Off until a webhook URL exists and `Enabled` is flipped. Before this: nothing posted to Discord at all. |
| Multi Discord connector (`Suite/modules/multi/connectors/discord.py`) | Reads one or more channels into the unified chat and can reply as the bot. Never authorised: no token in Credential Manager, `discord_channels` empty ("needs_auth"). Plain text only, no embeds, never pings. |
| Site worker (`PinguinoSite/worker/index.js`) | Reads #announcements into the site news and the member list for booster sync, with `DISCORD_BOT_TOKEN` + `DISCORD_NEWS_CHANNEL_ID` in Railway. Needs the privileged Server Members intent for boosters (sync state `intent` until then). Never posts. |
| Twitch chat | `!discord` says the invite (Helper/Chatty/Router); the raid line and lore link the invite from `Data/runtime/links.json` key `discord`. |
| Bot identity in Discord | The application name/avatar live in the Discord Developer Portal, not in the repo. Whether the site's bot and Multi's bot are the same application: unknown. |

## Recommended target layout (defaults; Ivan edits freely)

Channels, in this order:

| Channel | Purpose | Who posts |
|---|---|---|
| #announcements | go-live post (1 per stream), schedule changes, big news | Host webhook (Phase 1); Ivan |
| #raids-and-customs | "we raided X, go say hi" with the !leftbehind link, customs queue open/closed, match results | Host webhook (Phase 2) |
| #clips | clips the bots post on Twitch, mirrored here | Host webhook (Phase 2, optional) |
| #general | chat; Multi reads it into the stream dashboard | members |
| #rocket-league | LFG, ranks, customs talk | members |
| #bot-commands | !points !watchtime !rank !queue in Discord | PinguinoB0t bot (Phase 3) |
| #mod-log (private) | mod actions mirror, strike check-ins, Host warnings | Host webhook (Phase 4, mods only) |

Roles, with the colour of the Penguino look (orange on dark):

| Role | Given by | Phase |
|---|---|---|
| @Live Ping | self-assign (a reaction role or the Discord onboarding) | 1: the go-live post pings it |
| @Mods | Ivan by hand | now |
| @Sub | booster/sub sync (Twitch sub list from the Host, matched by linked account) | 4 |
| @Booster | Discord's own Server Booster role; the site reads it | 4 (site already does this when the intent is on) |
| @Customs Player | registered Epic in the Host (`!register`), synced | 4 |

## Phase 1 - go-live announcements (DONE in code, waits for a webhook)

Owner: Host, `PinguinoHost/HostDiscord.cs` (+ `HostDiscordApi.cs`). Decided for the Host over Multi because the Host already owns the live state (`LiveState`, Twitch `/streams` every 20 s, OBS fallback), holds the Twitch title/game/thumbnail, persists state in `Data/runtime`, has the mod command dispatch and sim mode. A webhook needs no bot, no intent and no token in the repo.

Behaviour:
- When the Host sees the stream live, one POST to the webhook: role ping (optional), "innocentpenguin_ is LIVE on Twitch!", an orange embed with the stream title, game, link twitch.tv/innocentpenguin_, the live preview image and the game box art, posted as "PinguinoB0t".
- Once per stream, keyed by the Twitch stream id (or the day when Twitch is unreachable). A Host restart while live never re-posts. A blip (offline for a moment, new stream id within `MinGapMin`, default 30 min) never re-posts.
- Offline for `OfflineGraceSec` (default 180 s): the same message is edited to "Stream ended" (grey, no image, no ping), once.
- States: `not configured` (no webhook), `disabled` (`Enabled` false), `dry-run` (payload logged, nothing sent), `armed`. Fresh install = not configured + disabled + dry-run, so nothing can reach Discord by accident.
- Mods: `!discordtest` (status), `!discordtest dry` (log the payload), `!discordtest send` (a real `[TEST]` post, pings nobody), `!discordtest end` (edit the last real post to ended now). `!discordstatus` = status. Audited like every mod command.
- API (loopback, token for POST): `GET /api/discord` (state, settings, what was posted; never the webhook), `POST /api/discord/settings {Enabled, DryRun, RoleId, Content, Description, ...}`, `POST /api/discord/test {mode}`, `POST /api/discord/secret {webhook}` (stored in `Data/runtime/bots_secrets.json`, gitignored; `""` removes it).
- Secret lookup order: env `PINGUINO_DISCORD_WEBHOOK`, then `bots_secrets.json` `discord.WebhookUrl`. Never logged, never in API output. (Key vault: `DISCORD.WebhookUrl` can be added to `Suite/modules.json` + `Vault.Names` later; adding an undeclared name today would break the vault refresh loop, so it is not done.)
- Sim Host never calls a non-loopback URL. Test: `Tools/test-host-discord.py` (fake webhook + fake Helix, 49 checks).

Needs from Ivan:
1. A webhook URL for #announcements (Discord: channel settings > Integrations > Webhooks > New Webhook > Copy URL). Paste it into the Host with `POST /api/discord/secret` or into `bots_secrets.json` under `discord.WebhookUrl`. 100 can do the paste if Ivan sends it privately (never in a commit or a channel message).
2. Optional: the role id to ping (`RoleId`), or `everyone` / `here`.
3. Then: `!discordtest send` once in a test channel's webhook, then switch the webhook to #announcements, set `Enabled` true and `DryRun` false.

Needs a Host restart: commit 9de92d4 (100 builds; the file set is HostDiscord.cs, HostDiscordApi.cs and three one-line hooks in HostLive.cs, HostAutoApi.cs, HostFeatureCommands.cs).

## Phase 2 - raid, customs and clip posts (same webhook pattern)

Owner: Host (`HostDiscord.cs` grows a second webhook per channel). Needs: one webhook per target channel (#raids-and-customs, optionally #clips), stored next to the first one as `discord.RaidsWebhookUrl`, `discord.ClipsWebhookUrl`.
- Raid out (`raid_out` automation, Host already knows the target): "We raided **{target}**: twitch.tv/{target}. Left behind? `!leftbehind` in Twitch chat gives the link." One post per raid id.
- Customs: queue opened (`queue_open` edge the Host already fires) with the mode/format and how to join; match results optional (off by default: noisy).
- Clips the bots post on Twitch (`clips_recent.json` already tracks them): mirror the URL, Discord unfurls the clip.
- Each post type has its own `Enabled` flag, defaults: raids on, customs open on, results off, clips off.
Estimate: S. Tests: extend `test-host-discord.py` with the raid/queue triggers (the sim lines `raidpick` and the queue commands exist).

## Phase 3 - PinguinoB0t presence in Discord (bot token)

Owner: a new Host module? No: **Multi** already has the Gateway connection, reconnect logic, the 30 s duplicate guard and the no-ping rule, so Discord commands run through Multi, which forwards them to the Host like any foreign-platform chat line (`POST /api/chat-in`, platform `discord`), and the Host answers through Multi `/api/send`. Work:
- Multi: hand Discord-origin lines to the Host's command dispatch (today Discord lines are shown in the dashboard only; the Host has `yt:`/`tt:` platform keys but no `dc:`). Owner 140 Multi for the forward, 110 Bots for the `dc:` platform key and the economy lookup by linked account. 170 writes the contract and tests.
- Commands in #bot-commands only: `!points`, `!watchtime`, `!rank`, `!queue` (status), `!discord` is pointless there, `!commands` links the site. Account link: Discord user -> Twitch login via the site's existing Discord link (the site keeps `doc.discord` links for boosters) or a `!link <twitch login>` the mods confirm.
- Slash commands (`/points`) are nicer but need an application id + command registration; start with `!` commands (zero setup), slash later.
Needs from Ivan: the bot token (Developer Portal > Bot > Reset Token) pasted into Multi (Settings > Discord, stored in Credential Manager), the Message Content intent toggled on, the bot invited with Send Messages + Read Message History on #bot-commands and #general, and the channel ids. Estimate: M (two areas).

## Phase 4 - roles and sync (bot token + Server Members intent + Manage Roles)

Owner: site worker for boosters (exists, needs the intent), Host for subs/customs players (new), through a small Discord REST helper in the Host or Multi.
- Boosters: already read by the site when Server Members intent is on (Docs/IVAN_GUIDE.md row 9). Nothing to build; verify `sync.discord == ok`.
- @Sub: the Host knows the sub list (`SubBoard`, `/api/subs`); matched to Discord members by the same link table as Phase 3; the bot adds/removes the role daily. Needs Manage Roles and the role placed below the bot's role.
- @Customs Player: everyone with a registered Epic (`!register`), same mechanism.
- Mod-log mirror (#mod-log webhook): `ModAudit` entries and Host warnings, mods only. Webhook, no bot needed.
Needs from Ivan: Server Members intent, Manage Roles permission, the role ids, a decision whether subs get a role at all. Estimate: M.

## Phase 5 - server tidy-up (Ivan with 170's checklist)

Welcome channel text + rules, onboarding questions (pick @Live Ping), channel descriptions that match the site wording (130 owns the site text), invite link check (`links.json` key `discord` is the single source), a pinned "how the bots work" post generated from `Docs/SITE_FAQ.md`. No code; a Docs checklist.

## Rules kept in every phase
- Never two posts for one event (stream key / raid id / clip id de-dup, persisted in `Data/runtime/discord_state.json`).
- No ping except the go-live role ping; test posts never ping.
- No secret in git, logs, chat or API output; webhook/token only in `bots_secrets.json`, Credential Manager or Railway variables.
- Everything has a dry-run and a mod test command before it goes to a real channel.
- Penguino look: orange 0xFF8000 embeds on Discord's dark theme.

## Open questions for Ivan (defaults in brackets)
1. Webhook for #announcements: will you create it and send the URL privately? [yes; 100 pastes it into the Host]
2. Ping on go-live: a dedicated @Live Ping role that people self-assign [recommended], @everyone, or no ping? [role]
3. Go-live text: "{ping} innocentpenguin_ is LIVE on Twitch!" + title + game + link + preview image [keep]; anything to change?
4. Edit the post to "Stream ended" when the stream ends (3 min grace) [yes]
5. Phase 2 channels: one #raids-and-customs channel for raid-out + queue-open posts [yes], clips mirror [no for now]
6. Phase 3: PinguinoB0t answering !points/!watchtime/!rank/!queue in a #bot-commands channel via Multi, with the bot token in Multi's Credential Manager [yes, after Phase 1 is verified live]
7. Phase 4: subs and customs players get Discord roles (needs Manage Roles + Server Members intent) [yes for boosters now (site), subs/customs later]
8. Is the site's Discord bot (Railway `DISCORD_BOT_TOKEN`) the same application you would give Multi? [reuse one application, one token]
