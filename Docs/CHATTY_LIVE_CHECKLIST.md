# Chatty live checklist (after the next Host restart)

Nothing below has been seen live yet; all of it passes offline (chat tests 348, canned 32, gamble). Do NOT go live in OBS to test: use a stream that is already running, or the sim. Chatty's raid/hype/welcome-back lines only run while `WasLive` is true. One reply per action is the rule: if you ever see two lines for one action, note the time and the command and report it to 10.

Needs the Host restart (`App\Update-Module.ps1 host`, coordinator only): Chatty source is loaded by the Host at startup.

## Commands
| Try | Expect |
|---|---|
| `!tuck <name>` | one warm line tucking that person in, nothing else |
| `!raid` (as a viewer) | the PENGUIN RAID line (still waiting on Ivan's OK of the wording); bare `!raid` by the broadcaster stays silent |
| `!games` | one line: !gamble, !slots, !duel, !give (only those switched on) and Guess the Chatter (start via !shop); second `!games` within the cooldown: nothing |
| `GET /api/canned` (loopback) | list of canned commands; `POST` set/add/test/cooldown leaves a `.bak`; no delete |

## Reactions (only while live)
| Event | Expect |
|---|---|
| Raid with >= `RaidMinViewers` | after about 7 s (the Host's thank-you goes first) ONE Chatty welcome naming the raider; a second raid within 2 min: nothing |
| Hype train level 2+ | one line per new level (60 s cooldown); begin/end are the Host's, Chatty stays silent |
| A regular back after `WelcomeBackDays` (default 7) | one private welcome-back line from the Host's people-graph pool (`TimeoutReward.PeopleGraph.WelcomeLine`: banded by days away, warmer for chat regulars; extra lines in `Data\lore\welcome_lines.json`), name only, no numbers; a recent supporter gets the thank-you version; opted-out viewers and bots never get anything |
| Someone tells Chatty off ("stop @ing me") | one short humble reply; a heated argument that only tags it: silence; same person's tag twice in 4 min: second is skipped (unless a real question) |
| Calm "bots are cool" chat, 3 lines, then a question to Chatty | answered (bots alone is no longer heat) |

## PgGame lines (the Host decides who posts; check for exactly ONE line each)
| Action | Expect |
|---|---|
| `!gamble 10`, `!slots 10` (win / lose) | one Chatty line with name, numbers; slots show real emoji reels (🍒 🐟 ⭐ ⚽ 🐧) |
| `!duel @x 10`, `!accept`, `!decline` | challenge tags the opponent; result names both |
| `!give @x 5` | one thank-you line |
| `!shop sub` (Get a sub, if enabled) | one line: price taken, a mod will gift; refusal passes the reason (e.g. already waiting) |
| `!shop guess 100`, `!guess name` | start: quotes the chat line with tries and payout; wrong: "N tries left"; right / out of tries / timeout: reveals the chatter. Each one line |
| Same with `GameVoice` off in `chat_settings.json` | the plain Host line instead, never both |
| Heated chat or opted-out viewer | plain result, no banter |

## What to look at if something is off
- Two lines for one action: `pinguino.said.recent` guard + Host log `[pggame]` / `Clog` "PgGame event failed".
- No Chatty line: `chat_settings.json` Enabled / ChatReplies / GameVoice (never print that file, it holds the AI key), or Chatty offline (`WasLive` false; PgGame ignores it).
- Replies not threaded: Twitch reply needs the viewer's msgId; Chatty pins it in cx since 92d6fb0.

## Offline test commands (all green at the last run)
```
powershell -NoProfile -ExecutionPolicy Bypass -File Tests/chat/run-chat-tests.ps1
cd PinguinoHost; dotnet build -c Release -o /tmp/hostchkNN
PGTEST_PORT=8961 PYTHONIOENCODING=utf-8 python Tools/test-host-gamble.py /tmp/hostchkNN/PinguinoHost.dll
PYTHONIOENCODING=utf-8 python Tools/test-host-canned.py /tmp/hostchkNN/PinguinoHost.dll
node Shared/sync-shared.mjs --check
```
