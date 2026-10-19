# PinguinoBot split: chatbot / helper / game manager

Goal: viewers never need to know a command. They talk normally; the bot answers practical questions and does the practical things for them.

| Part | File | Job | Streamer.bot action |
|---|---|---|---|
| CHATBOT | `PinguinoChat\PinguinoChat.cs` | conversation, memory, personality. Unchanged. | `PinguinoChat` (no chat trigger any more, see "No double answers") |
| HELPER | `HelperPinguino\PinguinoHelper.cs` | reads normal chat; answers lobby/join/register questions; does register/join/leave/position for the viewer after a "yes" | `PinguinoHelper` (trigger: Twitch > Chat > Message, no command filter) |
| GAME MANAGER | `PinguinoBotCore.cs` | queue, teams, matches, stats, website sync. Logic untouched. | the existing core action (name in `helper_settings.json` > `CoreActionName`) |

Rule of thumb: the chatbot talks, the helper does errands, the core owns the data. The helper never writes the core's files.

## 1. How the helper decides intent

1. **Gate (free):** ignore the bot itself, other bots, and `!commands` (except a mistyped `!register`, below). Only while live (`WasLive` in the core's `settings.json`, like the chatbot). Per-viewer and global cooldowns.
2. **Pending confirmation:** if this viewer has a question from the helper waiting (60 s) and says yes/yep/ok/do it -> run it. "no/nah/cancel" -> drop it. Anything else leaves it pending until it expires.
3. **Pattern pass (free, covers the common cases):** regexes for
   - `lobby_info`: "what's the code", "name and pass", "lobby password", "private match name", "pm?"
   - `how_join`: "how do I join/play/get in", "can I play", "wanna play customs"
   - `how_register`: "how do I register", "what is register"
   - `do_register`: "register me as X", "my epic is X"
   - `do_join` / `do_leave` / `position`: "add me to the queue", "take me out", "where am I in the queue"
   - `bad_register`: a typed `!register <name>`, `!register [name]`, `!register name`, or `!register my epic is X` (the core registered the wrong thing or refused it).
4. **AI only when unclear:** the message mentions queue/lobby/join/register/code/pass/play/custom/private/match words, looks like a question or request, and no pattern matched. The AI gets a tiny prompt and must return JSON `{"intent": ..., "epic": ...}` from a fixed list. **The AI never writes the reply.** Every reply is a template filled with config and live data, so it cannot invent a password or a command. Unknown intent / invalid JSON / no key = stay silent (the chatbot gets the message). AI calls are capped per hour (`MaxAiCallsPerHour`).

## 2. How it calls the game manager

Two options were considered:

- **A. `CPH.RunAction(CoreActionName, true)` with arguments (chosen).** The core already takes `command`, `rawInput`, `user`, `userName`, `userId`, `role`, `isModerator`, `isBroadcaster` from the arguments, handles locking, writes the files and replies in chat itself. The helper sets those arguments, runs the action synchronously, then restores the original arguments.
- B. The website command channel. Works for remote/web control, but needs the site token, a network hop and a round trip; it is for the website's own buttons. Not used.

Arguments the helper sets for a core call: `command` = `!register` / `!join` / `!leave` / `!pos`; `rawInput` = the Epic name (register only); `user`/`userName`/`userId` = the viewer who asked (unchanged); **`role` = 1, `isModerator` = false, `isBroadcaster` = false** (privileges are always stripped, even for a mod, so a helper call can never be a mod call).

## 3. What it must never do

- **No spend:** no channel points, bits, shop, rewards, giveaways, gifting. It calls nothing except the four allow-listed core commands and `SendMessage`.
- **No mod actions:** no `!queue`, `!kick`, `!balance`, `!win`, `!setmmr`, no timeouts/bans, no `!register @someone`. Privileges stripped (see above). Mods asking get the same help as anyone.
- **Never changes someone else's data:** the target is always the sender. An Epic name containing `@`, starting with `!` or `/`, or not 3-16 characters of letters/digits/space/`_ - .` is refused. "register X for my friend" is not an intent.
- Actions that change something (register, join, leave) are only done after the viewer's own "yes" to a message that spells out exactly what will happen (including the exact Epic name). Looking up queue position is read-only and needs no confirmation.
- The lobby name/password come from `helper_settings.json`, are only said in answer to a question about them, and are never put in the chatbot's memory or prompts (the chatbot refuses to store passwords anyway).
- It does not argue, chat or joke. Anything that is not practical goes to the chatbot.

## 4. No double answers (chatbot vs helper)

Both would otherwise fire on the same Twitch chat message. Solution with **no change to `PinguinoChat.cs`**: the helper is the only action with the chat-message trigger and it *hands the message on*:

- Helper handled it -> it answers and stops. The chatbot is not called for that message.
- Helper did not handle it -> `CPH.RunAction("PinguinoChat", true)` with the original arguments (restored first). The chatbot behaves exactly as before.
- Hand-over is also used for `!commands`, so the chatbot still sees everything it saw before.

Cost: messages the helper handled never reach the chatbot's log/memory. If that matters, add one tiny hook to the chatbot later (needs the owner's OK): the helper passes `helperHandled=true` and the chatbot records the line but does not reply (`ForwardHandled` in the helper settings turns the hand-over on for handled messages). Off by default.

## 5. Config and files

`%AppData%\BVQ\helper_settings.json` (created on first run, reloads within 10 s): `Enabled`, `LobbyName` (`peng2`), `LobbyPassword` (`""` = "no password"), `CoreActionName`, `ChatActionName` (`PinguinoChat`), `LiveOnly`, cooldowns, `UseAi`, `MaxAiCallsPerHour`. The AI provider/key/model are read from the chatbot's `chat_settings.json` (one key to manage). Reads (never writes) the core's `players.json`, `live_state.json`, `settings.json`.

Tests: `Tests\helper\run-helper-tests.ps1` (stub Streamer.bot, fake AI, throwaway data folder).

---
**Update (Oct 19):** with the new `PinguinoRouter` action (see `Shared\BOTS_DESIGN.md`) section 4 changes: the router is the only chat-message trigger and decides the order; the helper reports `handled` / `pass` to it and no longer hands messages on itself (it still does when no router is installed). Names and accounts now come from `%AppData%\BVQots.json`.
