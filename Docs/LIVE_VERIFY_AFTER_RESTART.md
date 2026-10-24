# Live verify after the next Host restart (12 Chatty, for 10 / 100)

Nothing here was run live. Offline state 2026-10-23: chat 396, bots 108, helper 268, Host gamble / replytest / canned (52) / subtickets all PASS, `sync-shared --check` clean. Older, wider list: `Docs/CHATTY_LIVE_CHECKLIST.md`.

**Rules:** never go live in OBS to test; use a stream that is already running, or the sim (`PINGUINO_SIM`). Chatty's raid / hype / welcome-back lines only run while the channel is live. One line per action: two lines for one action is a bug, note time + command and report it. Chatty's source loads at Host start, so the RxHeat tuning (this commit) and everything else needs this restart.

## How to check without posting a duplicate
- **Read, don't re-send:** `Data\logs\bot-sends-YYYY-MM-DD.log` (every line a bot sent, with account, status, and any 400 resend), `Suite\logs\host.log`, `Data\logs\routing.log` (skips with reasons).
- **Watch the line appear** in the chat that is already live; do not retype a command to "see it again". Cooldowns swallow the second try anyway.
- **GET only:** `GET /api/canned`, `GET /api/status` are safe to repeat; the POSTs write files.
- **Sim:** `Tools\test-host-*.py` run a private Host copy and never touch the channel.

## Checks
| # | Feature | Trigger (once) | Exact expected | Check without duplicating |
|---|---|---|---|---|
| 1 | `!tuck` | a viewer types `!tuck <name>` | one line: `<viewer> tucks <name> in nice and snug. Sweet dreams, and thank you for hanging out tonight! 🛏️🐧` | one row in bot-sends log from Chatty; second `!tuck` inside the cooldown: nothing |
| 2 | `!raid` | a viewer types `!raid` | `🐧 PENGUIN RAID 🐧 Thank you all for hanging out with InnocentPenguin tonight, you are awesome! Waddle on over and say hi!` (broadcaster's bare `!raid`: silent; real raids stay `!raid <channel>` + `!confirm raid`) | bot-sends log |
| 3 | Raid start | automation `raid_start` | Host says `Raid started! Prepare your emotes! ...` once when the raid is scheduled, NOT again when it lands | alerttest (`test-host-alerttest.py`) covers it; live: one line in the log at schedule time |
| 4 | Raid in (>= RaidMinViewers) | incoming raid | after ~7 s, after the Host thank-you, ONE Chatty line naming the raider (3 wordings: `... raiders, grab a seat`, `welcome in, raiders from ...`, `raid crew from ..., you made it!`); second raid within 2 min: nothing; raid start/out events: nothing from Chatty | bot-sends: exactly one Chatty line per raid |
| 5 | Hype train | level 2+ | `hype train level N! 🚂🐧 Keep it rolling!` or `level N already?! ...` / `choo choo, level N! ...`; one per new level, 60 s cooldown; begin/end are Host-only | log |
| 6 | Welcome-back | a regular returns after `WelcomeBackDays` (7) | one line from the people-graph pool, name only, no day counts; opted-out and bots: nothing | bot-sends; `routing.log` shows nothing extra |
| 7 | Called-out | viewer tags Chatty angrily ("stop @ing me") | one short humble reply; a heated multi-user argument or the same person twice in 4 min: silence | silence is the pass: absence of a second line |
| 8 | PgGame lines | `!gamble 10`, `!slots 10`, `!duel`, `!give`, `!shop guess 100` + `!guess name` | one Chatty line per action, in games voice (name, numbers, slot emoji reels); refusals (cooldown, round running, stake range) in Chatty phrasing; heated chat / opted-out / `GameVoice` off: the plain Host sentence, never both | bot-sends: count lines per action id; `pinguino.game.done.<id>` mark means Chatty handled it |
| 9 | Guess/refusals threading | two viewers act seconds apart | each answer threaded under its own message | look at the chat |
| 10 | `!games` | viewer types `!games` | one line listing the games that are on (`!gamble`, `!slots`, `!duel`, `!give`, Guess the Chatter via `!shop`); second within cooldown: nothing | log |
| 11 | `/api/canned` | `GET http://127.0.0.1:<port>/api/canned` | JSON list; the 3 `!discord` entries show `$(link:discord)`; `!discord` in chat posts the real Discord URL, and if the link key is missing NO line (never a literal `$(link:...)`) | one `!discord`, read bot-sends |
| 12 | Bot-send log | any bot says something | a line per send in `bot-sends-<today>.log`, file stays under 5 MB (real-size cap); a 400 from Twitch shows one resend, not two lines in chat | open the file |
| 13 | `!vanish` | a non-mod types `!vanish` | no chat reply; they are timed out 1 s (`poof`); host.log `[vanish] <name> vanished`; mods get `mods can't vanish`; repeat within 10 s: nothing | host.log |
| 14 | Firsts without bots | the first-chatter race at stream start | bots (PinguinoB0t, Chatty, Helper) never win or count as first; a viewer's `first` word gets the Host Firsts line and NO welcome next to it | `Tools/test-host-firstsbots.py` offline; live: read the log |
| 15 | RxHeat (new) | chat swearing as emphasis ("fuck yeah") then a question to Chatty | answered (not treated as heat); a real argument (>= 3 hot lines in 90 s, >= 2 users, >= 1 real put-down) still silences banter | silence/answer in chat; offline 396 checks |

## RxHeat evidence (offline only)
Four days of chat_logs replayed against the old and new pattern: heat episodes 19 -> 9; "fuck*" was 57 of 6,128 hot-line hits. Two heat tests added in `Tests/chat/harness.cs`. Revert path: the regex comment in `PinguinoChat.cs` near `RxHeat` names the previous pattern.

## If something is off
- Two lines for one action: `pinguino.said.recent` guard, host.log `[pggame]`, `PgGame event failed`.
- No Chatty line: `chat_settings.json` Enabled / ChatReplies / GameVoice, `bots.json` chat Enabled (never print the settings file, it holds the AI key); a switched-off Chatty means the Host plays the plain line.
- Unknown: who wrote `Enabled=false` on 10-19 17:05 (not found); the real-mode done-mark fallback is untested (sim returns before it).
