# Session notes: 170 - Discord (supervisor for everything Discord)

Session id local_04a3d46c-8969-4af1-aed4-0f728491f3d7, started 2026-10-30 03:55 CDT by 100 - Coordinator (local_32405a3a-974d-494b-8007-01272497ad35). Works in the shared checkout (no worktree), Discord files only. Coordinates with 110 (Host) and 140 (Multi) through 100, never directly. Plan: `Docs/DISCORD_PLAN.md`.

## 1. What I did (2026-10-30)
- Read SESSIONS_STRUCTURE, worker 14's Discord inventory (shared notes `14-discord-inventory.md`), HostLive/HostAuto/HostAlertBridge, Multi's `connectors/discord.py`, the site worker's Discord reads.
- Decision: **go-live announcements live in the Host via a Discord webhook** (no bot, no intent, no token). The Host owns the live state (Twitch `/streams` every 20 s, OBS fallback), the Twitch title/game, persistence and the mod command dispatch. Multi keeps its chat connector for Phase 3 (commands in Discord).
- Commit **9de92d4** (needs a Host restart): `PinguinoHost/HostDiscord.cs` (announcer), `PinguinoHost/HostDiscordApi.cs` (routes), one-line hooks in `HostLive.cs` (exposes `LiveState.Stream` / `StreamId`, starts the announcer), `HostAutoApi.cs` (route hook), `HostFeatureCommands.cs` (`!discordtest` / `!discordstatus`, mods only). Test `Tools/test-host-discord.py` (49 checks, PASS on a scratch build; `test-host-downtime.py` still PASS).
- Commit (docs): `Docs/DISCORD_PLAN.md` (5 phases, defaults, what each needs from Ivan), this file.

## 2. How Phase 1 works (for 100 / 110)
- Files: settings `Data/runtime/discord.json` (seeded on first run: `Enabled` false, `DryRun` true, `RoleId` "", templates, `EditOnOffline` true, `OfflineGraceSec` 180, `MinGapMin` 30), state `Data/runtime/discord_state.json` (stream key, message id, posted/ended times, the posted body), secret in `Data/runtime/bots_secrets.json` `discord.WebhookUrl` (gitignored) or env `PINGUINO_DISCORD_WEBHOOK`.
- States: not configured -> disabled -> dry-run -> armed. Fresh install posts nothing.
- Once per stream key (`twitch:<stream id>`, else `day:<date>`); restart-safe; blips inside `MinGapMin` ignored; a dead webhook (404/401/403) is tried once per stream.
- Verify without going live: `!discordtest` (status), `!discordtest dry` (payload to host.jsonl source `discord`), `!discordtest send` (real `[TEST]` post, no ping), `!discordtest end`. `GET /api/discord`, `POST /api/discord/test {mode}`, `POST /api/discord/settings`, `POST /api/discord/secret {webhook}`.
- Sim Host: only a loopback webhook is ever called.

## 3. Open with Ivan (via 100; defaults in DISCORD_PLAN.md "Open questions")
Webhook URL for #announcements (sent privately, 100 pastes), ping role, text, offline edit, Phase 2 channels, Phase 3 bot token in Multi, Phase 4 roles/intents, whether the site bot = Multi bot.

## 4. Next (backlog)
1. When the webhook is in: `!discordtest send` against a test channel, then arm (`Enabled` true, `DryRun` false) - 100 does the restart + the flips.
2. Phase 2: raid-out / queue-open / clips webhooks (S, Host only, extends `test-host-discord.py`).
3. Phase 3 contract for 140 + 110: Discord lines -> Host `/api/chat-in` platform `discord`, `dc:` platform key, account link.
4. Key vault entry `DISCORD.WebhookUrl` (needs `Suite/modules.json` declaration by 120 before `Vault.Names` gets it).
5. Workers: none yet (proposal cards only once Ivan talks to this session).

## 5. Facts for whoever follows
- Discord lines in Multi are NOT dispatched to the Host today (no `dc:` key); worker 14 flagged it, unverified in Program.cs.
- The site worker's booster sync needs the Server Members intent (IVAN_GUIDE row 9); its token and the news channel id are Railway variables.
- `links.json` key `discord` is the invite's single source; `!discord` in Twitch prints it.
