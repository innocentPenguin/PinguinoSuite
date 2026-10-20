# The three bots: HelperPinguino, PinguinoChat, PinguinoB0t

| Bot (default name) | Role | Job | Code | Streamer.bot action |
|---|---|---|---|---|
| **PinguinoB0t** | `core` | the game and OBS: queue, teams, matches, stats, scenes, website sync | `PinguinoBotCore.cs` | `PinguinoBot` (its own `!command` triggers) |
| **PinguinoChat** | `chat` | talks to viewers ("yaps"): memory, personality, jokes, history | `PinguinoChat\PinguinoChat.cs` | `PinguinoChat` (event triggers only) |
| **HelperPinguino** | `helper` | practical help: lobby info, how to join / register, does errands for the viewer, expands and helps | `HelperPinguino\PinguinoHelper.cs` | `PinguinoHelper` |
| (front door) | - | decides who gets each chat message | `Shared\PinguinoRouter.cs` | `PinguinoRouter` (the ONLY chat-message trigger) |

Today only PinguinoB0t has a Twitch account. The other two speak through it until you make their accounts (see "Giving a bot its own account").

## Names are data, not code: `%AppData%\BVQ\bots.json`
Created with the defaults the first time any module runs, re-read within 10 seconds. Per role: `Title` (the name viewers see), `Account` (Twitch login, `""` = no account yet), `Aliases` (what viewers call it: `@name` or the plain word), `Action` (the Streamer.bot action), `Enabled`, `Sender`, `Tag`. Also `Fallback`, `TagWhenShared` (put `[Title]` in front of a message spoken through another bot's account) and `HelperContextSeconds`.
To rename a bot: change `Title`, `Account` and `Aliases` there. Nothing else needs touching (the code only knows the roles `helper`, `chat`, `core`). Old `BotAccount` / `Names` settings in `chat_settings.json` and `helper_settings.json` still work and are added to it.

## Who answers a chat message (the router)
1. **@ing or naming ANY of the bots** (any alias, or replying to any bot's account) brings up **PinguinoChat**.
   Exception: it is about what the helper said / does -> **HelperPinguino** first: the helper spoke to this viewer in the last 2 minutes and the message is a yes / no, a short follow-up, a lobby / join / register question or names the helper; or it is a reply to the helper's account.
2. **Ordinary chat**: the helper first (it only answers practical questions and otherwise passes), then the chatbot (it listens, records, and joins in when it wants).
3. **`!commands`**: the helper (a mistyped `!register`), then the chatbot (records them). The game manager runs its own commands from its own triggers; it is not part of the router.
4. A helper question sent to the chatbot (`@PinguinoB0t what's the code`): the chatbot **defers** (no AI call, says nothing), the helper answers. If the helper does not take it either, the chatbot gets it back and must answer.

## Fallbacks (nobody is ever left without an answer)
`helper -> chat -> core`, `chat -> helper -> core`, `core -> chat -> helper`.
- **A bot is missing** (the action does not exist in Streamer.bot), **switched off** (`Enabled: false`) or **passes** ("not mine"): the next bot in the chain gets the message.
- **A bot has no voice** (no Twitch account yet): its messages are spoken by the first bot of its chain that has one. The helper's words come out of the chatbot's account if the chatbot has one, otherwise the core's; the chatbot's words out of the helper's, then the core's; the core's out of the chatbot's, then the helper's.
- **The game manager cannot be reached** (helper asks it to register / join and the action is missing or off): the viewer gets "I can't reach the game manager right now, a mod can help" from the fallback voice instead of silence.

Module -> router protocol (global variable `pinguino.result`): `handled` (done, or deliberately silent), `pass` (not mine / off: next please), `defer` (looks like the next bot's job: ask it first, come back if it passes). A module that reports nothing (an older version) counts as handled, so nothing is ever answered twice. The router sets the arguments `pinguinoRouted`, `pinguinoRole`, `pinguinoNext` (who is next) and `pinguinoNoDefer` (second round). Without the router (old setup) the helper still hands unhandled messages to the chatbot itself.

## Shared code
The registry, voice, alias and protocol code is ONE file, `Shared\PinguinoBots.cs.txt`. Every Streamer.bot action is compiled on its own, so a copy sits between `// <<PINGUINO-SHARED-BEGIN>>` and `// <<PINGUINO-SHARED-END>>` in each of: `PinguinoChat.cs`, `PinguinoHelper.cs`, `PinguinoBotCore.cs`, `PinguinoRouter.cs`.
After editing the shared file run `node Shared\sync-shared.mjs` (it rewrites the copies; `--check` only reports). Never edit the copies. `Tests\bots\run-bots-tests.ps1` fails if a copy is out of date.

## Setting it up in Streamer.bot (once)
1. New action **PinguinoRouter**: Execute C# Code = `Shared\PinguinoRouter.cs`, trigger Twitch > Chat > Message (no command filter).
2. Remove the chat-message trigger from **PinguinoHelper** and **PinguinoChat** (keep PinguinoChat's sub / gift / cheer / raid / follow triggers, and the core's command triggers).
3. Paste the new `PinguinoChat.cs`, `PinguinoHelper.cs` and `PinguinoBotCore.cs`, compile each, restart Streamer.bot. Check the action names match `bots.json` (`Action`).
4. Nothing else changes for viewers until you add accounts.
`!chatbot status` (mods) shows the chatbot's state.

## Giving a bot its own account (later)
Streamer.bot itself only sends as the broadcaster and one bot account. For a second / third bot account:
1. Make the Twitch account, and get a user access token for it with the scope `user:write:chat` (a Twitch app Client ID + the OAuth flow for that account).
2. Put it in `%AppData%\BVQ\bots_secrets.json`: `{ "chat": { "ClientId": "...", "UserToken": "...", "SenderId": "<that account's user id>", "BroadcasterId": "<InnocentPenguin's user id>" } }` (keep this file private, like `chat_settings.json`).
3. In `bots.json` set that bot's `Account` to its login and `Sender` to `"helix"`.
From then on that bot speaks as itself through Twitch's "send chat message" API; if anything is wrong it falls back to the Streamer.bot account. (This sender is written and unit-tested with a fake HTTP call but has not been tried against real Twitch.) Also add the new account's login to the website's bot list so other bots and the stream ignore it.

## Folder layout
Layout (since Oct 19 2026, everything lives under `D:\PinguinoSuite`): `PinguinoB0t\` (core bot, overlays, commands), `PinguinoChat\`, `HelperPinguino\`, `Shared\` (this doc, the router, the sync script), `Pipeline\` (the log / profile / history scripts the scheduled task `PinguinoBot Log Update` runs), `Data\` (chat logs, profiles, history, lore), `Tests\{core,chat,helper,bots,history}`, `Suite\` (dashboard, PinguinoListen, PinguinoLink), `PinguinoApp\` (opens the Suite), `Archive\` (old versions). See `README.md` in the root for the map.

## Never the same line twice
Every line a bot says goes through `PgSay` (Streamer.bot bots) or `HostApi.SendAs` (Host modules). Both drop a line that is identical (case, spacing and invisible characters ignored) to one already said in the last 30 seconds, whichever bot said it. The Streamer.bot side keeps the record in the global `pinguino.said.recent`, so Router, Chat, Helper and Core see each other's lines. A send that times out is never retried on another account (it may have gone out). New code must not call `CPH.SendMessage` or post to Helix directly. Host tests set `PINGUINO_DUP_SECONDS=0` only when they must repeat a line.
