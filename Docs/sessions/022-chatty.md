# 022 - ChattyPinguino (fork of 02 PinguinoBots)

Owner of `PinguinoChat/PinguinoChat.cs` (the chat personality bot) and its tests `Tests/chat/`. Reports to 02 ([02 - PinguinoBots](local_58156ab8-4c1b-4654-a4a3-48687e71d813)); takes orders relayed from 00 ([00 - Pinguino](local_9b055c40-005d-4fad-892a-7133e1382dd1)). Last updated: 2026-10-23.

## 1. What was built / changed, and why (newest first)

| Date | Commit | What | Why (Ivan, relayed by 00) |
|---|---|---|---|
| 10-23 | aa42de0 | Slot reels are real emoji: 🍒 🐟 ⭐ ⚽ 🐧 (🐧 = jackpot) in `HostGamble.cs` defaults + live `Data/economy/gambling.json`; test that they survive the send path | Ivan: "!slots must use ACTUAL EMOJIS", then his symbol set (no bell, diamond or 7) |
| 10-23 | f88f5eb, 23d11d6 | **Chatty voices the games.** `PgGame` event handler (`GameEvent`/`GameLine`), `!games` / `!game` (canned entry using new `$(games)` variable), Guess the Chatter how-to answer (points to `!shop`), `GameVoice` + `GamblingFile` settings, docs (`Docs/ECONOMY_CONTRACT.md` PgGame contract + role split, `Docs/COMMANDS.md`). Host half by 02 = b1d8c42 | Ivan: "make Chatty Pinguino handle gambling and games"; "pinguinobot will be utility" |
| 10-23 | 5e6cddf | **Stay out of arguments.** Heat detector (`IsHeated`: 3+ lines from 2+ people in 90 s with insults/swearing/bots-debate words), called-out detector (`RxAtBot`) with a `[CALLED OUT]` prompt hint (short, humble or kindly defending), per-user reply gap (`ReplyGapSec` 240 s, skipped for real questions, attacks, or a live conversation). Prompt rule added. Settings `StayOutOfArguments`, `ReplyGapSec` | Ivan: Chatty must not argue or jump into arguments, may defend itself if attacked ("dont do that again pinguinobot" gets a humble reply); stop answering the same person's tag twice in a few minutes (LvLMarshmello 22:32 and 22:34) |
| 10-22 | 7b2feae (+ route in 07d8ddf) | **Canned-command editor backend** `PinguinoHost/HostCanned.cs`, `/api/canned` (GET list, POST set/add/test/cooldown), loopback only, `.bak` on every save, no delete, test `Tools/test-host-canned.py` (32 checks). Suite page requested from 01 (not confirmed built) | Ivan said YES to the canned-command editor |
| 10-22 | 57be4a1 | Raid + hype-train level-up reactions, welcome-back lines (private, name only, honours opt-outs), friendlier mod refusals, `!chatbot status` says why it is quiet, toggleable end-of-stream recap (default OFF). Host forwards `TwitchHype`, `StreamOnline`, `StreamOffline` | Ivan approved these (not the wheel) |
| 10-22 | 643795f | Shared logging: the same warning/error is logged once per 30 min (`PgLogRepeat`) | Nightly check of repeated log lines |
| 10-21 | 1515390 | `!tuck`, `!raid` raid-call line (bare `!raid` silent in Host), `!rank` playlist-name matching | Ivan's requests |
| 10-20/21 | many | See `git log -- PinguinoChat Tests/chat` for the full history (canned Nightbot port, audit R1-R3, offline mode, lore, gate, 8ball, opinions) | |

## 2. Decisions and reasons; what failed

- **Engine in the Host, voice in Chatty.** Gambling math, balances and cooldowns stay in `HostGamble.cs` (source of truth). Chatty only turns a finished action into one line. The Host decides who posts (Chatty if `Enabled && ChatReplies && GameVoice`, else its plain line) so there are never two replies; the 30 s `PgSaidRecently` guard is the second safety net.
- **No AI for game lines or `!games`**: templates only, so they are fast, cheap and never drift.
- **Heat detection is heuristic** (word list + 2 speakers + 3 lines). `bot`/`bots` are in the word list on purpose (Ivan named the bots debate), so a calm "bots are cool" chat by 3 people could count as heated and silence mentions that are not questions. Tune `RxHeat` if it is too eager.
- **Canned editor has no delete** (disable instead) and keeps `.bak`, on purpose (no deleting user data).
- **`!raid` text** is waiting for Ivan's OK (quoted to 00).
- **Failed / tripped on:** (a) Python heredocs through the shell turned `\b` into a backspace character in the C# regexes; always check `grep -c $'\x08' PinguinoChat.cs` after scripted edits and write patch scripts with the Write tool, not shell heredocs. (b) A shell `git commit -m "...$(games)..."` executed `$(games)`; use single quotes. (c) `git commit -- <paths>` fails for untracked files: `git add` first. (d) Tests need `Live(true)`, and `_liveChecked` caches live state for 10 s.

## 3. For the next session

- **Run the tests:** `powershell -NoProfile -ExecutionPolicy Bypass -File Tests/chat/run-chat-tests.ps1` (337 checks at the last run). Host: `cd PinguinoHost && dotnet build -c Release -o /tmp/hostchkNN`, then `PYTHONIOENCODING=utf-8 python Tools/test-host-canned.py /tmp/hostchkNN/PinguinoHost.dll` and `Tools/test-host-gamble.py`. Shared block: `node Shared/sync-shared.mjs --check`.
- **Chatty is source loaded by the Host** at startup (`Program.cs`), so a Host restart loads changes. Only 00 restarts/rebuilds/launches (standing rule). Never go live in OBS. No site push. Never `cat` settings files (they hold the AI key).
- **Do not edit `HostGamble.cs`, `Program.cs`, `HostSiteBridge.cs` without pinging 02** (02 asked).
- **Gotchas:** C# 7.3 only. Names: the bot account is `chattypinguino`; `Say(c,msg)` prefixes `@Display`. `canned_commands.json` is reloaded by Chatty and the Host about every 4 s. Variables in canned text: `$(user)`, `$(touser)`, `$(luck)`, `$(games)` (the editor validates only these). Chatty is asleep offline (`IsLive()` from `settings.json` `WasLive`, or global `pinguino.offlinemode`); `PgGame` ignores IsLive.
- **Settings added recently** (`chat_settings.json`): `ReactRaids`, `RaidMinViewers`, `ReactHype`, `WelcomeBack`, `WelcomeBackDays`, `RecapOnStreamEnd` (off), `StayOutOfArguments`, `ReplyGapSec`, `GameVoice`, `GamblingFile`.
- **Open / unverified live:** nothing from the last two days has been seen live yet: `!tuck`, `!raid`, raid/hype reactions, welcome-back, called-out handling, PgGame lines, `!games`, `/api/canned`. After the next Host restart: try each once, check there is exactly one reply per game action and the reels show as emoji.

## 4. Future ideas (priority order)

1. Live-verify everything above after the restart; tune `RxHeat` / reply gap from real chat.
2. Suite page for the canned editor (list, toggle, edit, test line, add, cooldown) - asked of 01; build it ourselves if 01 never does. Optional: per-command use counts.
3. `kind=guess` / `kind=shop` PgGame events so Chatty can voice Guess the Chatter and the shop too (02 offered to add them if wanted).
4. Decide whether the stream recap should be on, or use the Host's `Session.Line()` instead (02 may prefer that).
5. A per-viewer "no banter" flag for games beyond the memory opt-out (`optout` arg is wired but the Host only sets it for opt-outs).

## 5. Where the history lives

- Session id `7135181f-2c8d-4cec-8cda-1c0d6edae3ff`; transcript `C:\Users\ivanm\.claude\projects\D--\7135181f-2c8d-4cec-8cda-1c0d6edae3ff.jsonl`.
- Useful greps: `PgGame`, `StayOutOfArguments`, `canned editor`, `welcome-back`, `LvLMarshmello`, `tuck`, `/api/canned`.
- Edit helper scripts (temporary) are in the session scratchpad `...\scratchpad\edit*.py`.

## 6. Things Ivan may be forgetting

- **Waiting on his OK:** the `!raid` line - "🐧 PENGUIN RAID 🐧 Thank you all for hanging out with InnocentPenguin tonight, you are awesome! Waddle on over and say hi!" (`skipBroadcaster`, only runs for others).
- **Unanswered:** should the end-of-stream recap be turned on? (default off); per-command use counts in the editor?
- **Not built yet:** the canned-editor Suite page (requested from 01, no confirmation seen).
- **Risks:** heated-chat detection can silence normal mentions during a lively bots discussion; the called-out defence is prompt-driven (AI), so check the first real attacks for tone. Games are voiced by two code paths (Chatty + Host fallback); the first live game test should confirm there is exactly one line each.
- **Setup/keys:** nothing new needed. `gambling.json` is gitignored live data; the emoji symbols were written there directly.
- **Held:** the end-of-night 4-tier docs + 3x code audit stays held until he says done.
