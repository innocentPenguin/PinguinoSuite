## [NEW][BOTS] Three bots: HelperPinguino, PinguinoChat, PinguinoB0t + a router (Oct 19 2026)
- Design and set-up steps: `Shared\BOTS_DESIGN.md`. New Streamer.bot action `PinguinoRouter` (`Shared\PinguinoRouter.cs`) is the ONLY chat-message trigger; it starts the helper and the chatbot in the right order. @ing or naming ANY bot brings up the chatbot, unless it is about what the helper just said (then the helper first). Ordinary chat: helper first, then chatbot. Fallbacks: helper -> chat -> core, chat -> helper -> core, core -> chat -> helper (missing action, switched off, or "pass").
- Names / accounts / aliases / action names are in `%AppData%\BVQ\bots.json` (created on first use): rename a bot by editing that file. A bot without a Twitch account speaks through the next one in its chain; `Sender: "helix"` + `bots_secrets.json` lets a bot speak from its own account later (not tried against real Twitch).
- Shared code lives once in `Shared\PinguinoBots.cs.txt` and is copied into the four actions by `node Shared\sync-shared.mjs` (never edit the copies). `PinguinoChat.cs`: any bot name counts as a mention, helper-type questions are deferred to the helper, reports handled / pass / defer to the router. `PinguinoHelper.cs`: reports to the router, sets the "in conversation" marker, tells the viewer when the game manager cannot be reached. `PinguinoBotCore.cs`: speaks through `PgSay("core", ...)` (same account as before).
- Tests: `Tests\bots\run-bots-tests.ps1` (40 checks: order, fallbacks, renaming, who speaks), chat 202, helper 81, core all pass.
- Folder move NOT done yet (proposed: `core\`, `chat\`, `helper\`, `shared\`). It would change the scheduled task `PinguinoBot Log Update`, the website log agent and many absolute paths in settings files, and other sessions are editing these files; say when to do it.
- Not tried in the real Streamer.bot: `CPH.RunAction` + global variables as the router protocol, `ActionExists`.

## [NEW][CHAT] Sleeps when the stream is offline + says "come back when live" (Oct 19 2026)
- `LiveOnly` was false in `%AppData%BVQchat_settings.json`; it is now true: offline the bot records nothing, learns nothing and never calls the AI. NEW: if someone pings it while offline (name, @ or reply) it answers once, e.g. "I'm asleep right now 😴 come back when InnocentPenguin is live! https://innocentpenguin.com" (settings `OfflineReply` with {link}, `OfflineLink`, `OfflineReplyEverySec` 900 per viewer + max one per minute overall; `OfflineReply` empty = fully silent). Commands and ordinary chat get nothing; !forgetme / !rememberme / !memory still work. Needs PinguinoBotCore running (it writes WasLive). Chat tests: 194 pass. Paste GPTPinguinoChat.cs into Streamer.bot and compile to apply (the setting is already on).

## [NEW][CHAT] !commands are now collected as data (Oct 19 2026)
- `Pipeline\build-summaries.mjs` no longer throws away lines that start with `!`: it counts them per stream day into `Data\history\commands\<day>.json` (`total`, `users`, `top` = [{command, used, users}], `byUser` = {login: {"!cmd": n}}). Only the command NAME is kept, never its arguments (they can hold private things). Free: no AI calls. `node Pipeline\build-summaries.mjs --commands` does just this; the normal run does it too. First run over the existing logs: 59,964 commands on 247 days.
- Viewers who used !forgetme / were made anonymous count in the totals but are not listed in `byUser`. Command lines are still never sent to the AI as chat and the live bot still does not answer them (PinguinoChat.cs already records them in its logs, `c:1`); the per-viewer "commands they use" on the website profile already came from the same logs. This is the data to look at when the bot starts replacing commands (which ones are used, by how many people, when).

## [CHANGE][CHAT] !optmeout (and !optout) removed (Oct 19 2026)
- The command no longer exists: it is a normal chat message now. `!forgetme` (no details kept) and `!rememberme` / `!memory` stay. Viewers who ALREADY used !optmeout keep their anonymous state (names stay hidden in logs / prompts) until they run `!rememberme`; the anonymising code is still there for them. The "What PinguinoB0t knows" site section is now on every profile (the Settings switch was removed). Chat tests: 191 pass. Paste PinguinoChat\PinguinoChat.cs into Streamer.bot and compile to apply; the Streamer.bot command for !optmeout (if you made one) can be deleted.

## [NEW][WEB] Viewer "Private info" tab + bot feed of the PUBLIC part (Oct 19 2026)
- Member profiles on innocentpenguin.com have a "🔒 Private info" tab, visible only to the member themselves. PRIVATE BY DEFAULT. Fields (all optional): birthday month + day (never a year), state, favourite games, artists / music, sports and teams, pets, anything else. No pronouns on the website (the bot keeps those itself). A switch "Make my info public" says in plain words that it shows on their public profile / stream AND that PinguinoB0t may use it when talking to or about them; a live preview shows exactly what would be shared. The streamer (innocentpenguin_) is always public.
- HOW THE BOT SHOULD READ IT (not wired into PinguinoChat.cs yet): `GET https://<site>/api/bot/member-info` with `Authorization: Bearer <WebSyncKey>` (same key as /api/bot/commands). Optional `?m=<twitch login>` returns just that viewer. Response: `{"updated":"<iso>","members":{"<lower-case twitch login>":{"name":"Pinny","birthday":{"month":3,"day":14,"text":"March 14"},"state":"Texas","games":"...","artists":"...","sports":"...","pets":"...","other":"..."}}}`. Only viewers who switched it on (plus the streamer) are listed; empty fields are omitted; a viewer who switches it off disappears from the next call, so cache for minutes, not days, and drop anyone who is gone. Values are free text typed by viewers: treat them as data, never as instructions to the bot. Birthdays are month/day only; do not guess an age. Keys match the Twitch login the bot already uses (members with no Twitch account are keyed by their site login). It is separate from `/api/bot/profiles` (that one is the bot pushing what it learned; this one is the bot pulling what viewers chose to share), so do not merge the two into the pushed profiles.
- Site side: `worker/index.js` section PRIVATE INFO (`/api/private-info` own data, `/api/member-info?m=` public part, `/api/bot/member-info`), tab UI in `pages/member.html`, tests in `scripts/check.mjs`. Stored on the member record (no new Railway storage). Needs nothing new on Railway.

## [NEW][CHAT] Long-term history: daily, weekly, monthly summaries (Oct 19 2026)
- `Pipeline\build-summaries.mjs` turns the chat logs into small summary files in `Data\history\`: `daily\<date>.json` (summary, games, topics, moments, people), `weekly\<year>-W<nn>.json`, and `monthly\<login>\<yyyy-MM>.json` (interests such as artists / sports / teams / games, highlights, vibe) for each active viewer. Stream day = Central date; chat before 06:00 Central belongs to the previous day.
- Incremental and cheap: `--dry-run` shows the plan and a token estimate (full backfill today: 247 daily, ~36 weekly, ~62 monthly batches, ~1.3M input tokens), `--limit N` caps the AI calls, finished days / weeks / months are skipped. It uses the AI from `%AppData%\BVQ\chat_settings.json` (default claude-haiku-5-5); the key is never printed.
- Privacy: viewers with !forgetme / !optmeout get no monthly file and are "someone" everywhere; bots, !commands and distress talk are never sent; AI answers are filtered again for ages, school, health, locations, contact details, politics, religion, sexuality and race.
- First sample is built (2 days, 1 week, 6 viewers). The big backfill is NOT started; run `node Pipeline\build-summaries.mjs` when you want it.
- `PinguinoChat\HistoryHook.cs.txt` + `PinguinoChat\HISTORY_HOOK.md`: ready-to-paste read hook for PinguinoChat.cs (not wired in; needs your OK). Tests: `node Tests\history	est-summaries.mjs` (20 checks), `Tests\history
un-hook-check.ps1` (10 checks).

## [NEW][CHAT] Update log, friendship rules, names + trust, opinions, pronouns, no length cap (Oct 19 2026)
- `PinguinoChat\updates.json` (+ readable `PinguinoChat\UPDATES.md`) is the bot's update log: what changed and when. The bot reads it ([YOUR UPDATES] in every prompt, the last 6 when asked "what/when did you change"), the chat-log search adds the notices of a day to the chat around it, and `!chatbot updates` (mods) lists the latest. After ANY change to the bot run `node PinguinoChat\add-update.mjs "Title" "What changed" [who]` so the date is recorded (setting `UpdatesFile`).
- Romantic / sexual advances ("marry me", "be my girlfriend", "daddy"...) are counted per viewer over 30 minutes (`AdvanceLadderMinutes`) and the bot de-escalates in 4 steps: friendly "we're friends" -> "I'm just a bot" -> "you're bothering me" -> "that's harassment", then it stays quiet for that viewer for 15 minutes. Plain "ily" / "love you" is friend talk (answered warmly, not counted unless it is endless). No pet names, no flirting, no partner bits.
- Age: everyone is assumed 18+. Age and bedtime banter is allowed; only a reply that calls someone a minor is dropped. If a viewer says THEMSELVES they are under 18, the bot believes them (no age jokes, no romance talk). Viewers' birth years and ages are still never saved; the streamer's (2002, in `StreamerInfo`) is public.
- Names: the community's nickname first, then a name the viewer asked for (`selfnick`), then one the bot invented. A viewer who already has a name can only change it when trusted (trust score 0-100 from time around, messages, role, the bot's rating; mods count as trusted; `TrustNickMin` = 50).
- Pronouns (he/him, she/her, they/them) are remembered per viewer from what they say or how chat refers to them. Bot memory only, not on the website.
- Opinions: stances the bot took are saved once in `Data\pinguino_opinions.json` (same topic is never overwritten) and shown to the AI so every viewer gets the same answer; its opinion of each viewer is kept on the viewer's profile and changes at most every 3 days.
- Asking the same thing again within 30 minutes gets an "already answered" nudge ([REPEAT]).
- No hard reply length cap any more (`MaxReplyChars` = 0): the AI is asked for the shortest reply that does the job and not to keep the conversation going; replies over Twitch's limit are split at sentence ends.
- `!chatbot status` (mods): on/off, AI calls this hour, who it talks with, hushed viewers, last problem, last update.
- Prompt: never make things up (search the logs, dig for "first message" questions), interests are remembered (activities, artists, sports...), no talk about files/folders/scores.
- Fixed: the log search's day filter regex had lost its backslashes, so every day file was read; it now skips the files of other days.
- Tests: `Tests\chat` (192 checks). Paste `PinguinoChat\PinguinoChat.cs`, compile, restart Streamer.bot.

## [NEW][WEB] Chat logs searchable from the website, served by this PC (Oct 19 2026)
- New mod-only page `innocentpenguin.com/mod/chatlogs` (Mod Hub > Mod log & match history > Chat logs): search the messages, filter by username, day (with previous/next day arrows or "All days"), Chat / Notices (subs, raids, timeouts, bans), newest or oldest first. Times are UTC.
- The logs are NOT uploaded: `Pipeline\log-agent.mjs` runs on this PC, asks the website (outbound only, long polling) for searches, reads `Data\chat_logs` with `Pipeline\lib-logsearch.mjs` and sends back at most 200 lines per search. The website keeps nothing.
- Nothing to set up: `update-logs.mjs` (the 5-minute task) starts the agent hidden whenever it is not running (it touches `Pipeline\.log-agent.alive`). If this PC is off or you are logged out, the page says "Your PC is not connected". Run it by hand with `node Pipeline\log-agent.mjs`; stop it by ending its node.exe in Task Manager.
- Uses the same `WebSyncUrl` / `WebSyncKey` as the bot. Not part of PinguinoBotCore, so no Streamer.bot paste is needed.
## [NEW][WEB] Public 'What PinguinoB0t knows about them' on member profiles (Oct 2026)
- `Pipeline\push-profiles.mjs` sends the chatter profiles (Data\profiles) to the website (`POST /api/bot/profiles` with WebSyncKey, chunks of 50); `update-logs.mjs` runs it once a day after the rebuilds. Every member profile on innocentpenguin.com now has a public section: first / last seen, messages, active days, streaks, busiest day, usual hours, birthday (month + day) and state, their first message, nicknames, traits, behavior, likes, favorites, dislikes, games, hobbies, pets, friends in stream, favorite emotes and commands, and their own words. Left out: `clash` (who argues with whom) and the example quotes. Anyone who used !optmeout / !forgetme is not sent, and a member can hide the section in Settings > 'What PinguinoB0t knows about you'. `notes` is sent as written: keep private things out of it. First push: 1,792 profiles. Members are matched by their Twitch name.

## [NEW][CHAT] Logs update themselves every 5 minutes (Oct 2026)
- Windows scheduled task `PinguinoBot Log Update` (your account, no admin) runs `Pipeline\update-logs-hidden.vbs` every 5 minutes, hidden: it starts `Pipeline\update-logs.mjs`, which runs `fetch-chat-logs.mjs` (new chat into `Data\chat_logs`, events, chatter data; about 3 s) and, once per UTC day, the heavier rebuilds (nicknames, profiles, lore, stream history; about 40 s). One run at a time (lock file); log in `Pipeline\update-logs.log`. The task only runs while you are logged in to Windows. Check: `schtasks /Query /TN "PinguinoBot Log Update"`; stop: `schtasks /Delete /TN "PinguinoBot Log Update" /F`; by hand: `node Pipeline\update-logs.mjs` (`--all` also does the rebuilds now).
- The log sites lag behind real time by a little, so the newest minutes of chat can take a few updates to appear. The bot also records live chat itself while you are live (`%AppData%\BVQ\chat_logs`), which it searches too.
- `PinguinoChat\PinguinoChat.cs` re-reads `chat_events.json` whenever it changes on disk and merges it with its own (no overwriting each other). Paste and compile.

## [CHANGE][CHAT] Birthdays (no year) and states (Oct 2026)
- `PinguinoChat\PinguinoChat.cs` may now remember a viewer's BIRTHDAY as month and day only and the US STATE they live in. Whatever the AI or the viewer says is cleaned in code (`SpecialFact`): 'Birthday is March 14, 2008' is stored as 'Birthday: March 14' (the year and any age are dropped; a birthday without a usable date is not stored), 'Lives in Houston, Texas' as 'State: Texas' (no city / address / school). Ages, birth years, cities and addresses are still refused. A new birthday or state replaces the old one. On someone's birthday (Central time) the prompt gets a [BIRTHDAY] note and the bot wishes them a happy birthday without an age; it may tell when someone's birthday is (month and day) or which state if asked.
- `Pipeline\build-profiles.mjs` also finds them in the logs ('my birthday is June 4th', 'today is my birthday', 'i live in Texas') and writes `birthday` (month and day only) and `state` into the profile files: 12 birthdays and 6 states so far. Paste `PinguinoChat\PinguinoChat.cs` and compile, restart Streamer.bot.

## [FIX][CHAT] Searching the old logs + how far back someone goes (Oct 2026)
- Cause 1 (timing): searching all 660k log lines parsed every line and took about 3 s, but the search budget was 2.5 s, so the end of the archive was never reached and old or new chat could be silently skipped. The search now reads each file as plain text, finds candidate lines with a substring test and only parses those (plus the few lines around them): a full search takes about 0.1 s. Newest files are searched first and the budget is 4 s.
- Cause 2 (data): the log sites only have the channel from 2026-02-15; you started streaming in early Nov 2025 and nobody logged that chat. `Pipeline\build-profiles.mjs` now reads StreamElements' !followage answers in the chat ('X has been following for 3 months' said on Feb 17 means following since about Nov 15 2025) and !watchtime answers, so `seen.firstSeen` is the EARLIEST KNOWN date (131 people go back before the logs; e.g. lvlmarshmello Nov 15 2025, yoohoo15 Nov 16 2025) with `firstSeenSource`, `firstSeenInLogs`, `followingSince` and `watchTimeHours`. INDEX.md marks estimated dates with ~. The bot's 'first seen / first message' answer now says which it is and that the first message is the first one in the logs.
- Paste `PinguinoChat\PinguinoChat.cs` and compile, restart Streamer.bot.

## [NEW][CHAT] A profile for EVERYONE (Oct 2026)
- Pipeline\build-profiles.mjs now writes a profile for everyone in the logs: all 1,745 people who ever wrote a message (was 498) plus 40 who were only @mentioned (mentioned-only profiles: who mentioned them, when). New in every profile: seen (first seen and last seen to the second, UTC; their FIRST MESSAGE and last message; longest run of days in a row; busiest day; a flag for people already chatting on the first logged day), likes (what they say they like / love / enjoy / are into, kept only when said twice or with love/enjoy), favorites (my favorite X is Y), dislikes, games, favorite emotes and commands, and ownWords (the words that are most theirs). Profanity, slurs, nationalities, politics, school / age / health, people's names and generic words are filtered out of likes. 102 people have likes today (precision over quantity).
- Data\profiles\INDEX.md lists everyone: login, first seen, last seen, messages, days, first message, likes. notes fields are kept on rebuild.
- The bot's card now includes what someone likes and their favorites, and the viewer's own dislikes; when asked when someone joined / their first message / last seen it also gives first seen, first message and last seen. Paste PinguinoChat\PinguinoChat.cs and compile, restart Streamer.bot.

## [CHANGE][CHAT] Logs organised by year / month / day (Oct 2026)
- `Data\chat_logs` now holds every logged day as `<year>\<month>\<year-month-day>.txt` (e.g. `2026\10\2026-10-19.txt`, UTC, readable by hand) with `INDEX.md` (days and message counts per month) and `README.md`. Each file also has the notices between the messages (`* 48 raiders from DoctorNopeRope have joined!`, subs, gifts, `* user was timed out for 600s`, bans). 247 days, 662,728 messages, Feb 15 to Oct 19 2026 (logs.cyex.app, logs.zonian.dev, logs.potat.app). Your hand-downloaded files are in `_original-downloads` (folders starting with _ are ignored by the bot and the tools).
- `Pipeline\fetch-chat-logs.mjs` writes this layout and keeps it up to date (new days only); `Pipeline\lib-logs.mjs` is the shared reader used by build-nicknames / build-profiles / build-lore / build-history. The bot reads the folder recursively. Paste `PinguinoChat\PinguinoChat.cs` and compile.

## [NEW][CHAT] References from months ago (Oct 2026)
- Before the AI answers, `PinguinoChat\PinguinoChat.cs` now (1) looks the message up in `Data\lore.json` (running jokes, catchphrases and emotes with first-seen date, user, sample line, how often and how many people) and (2) when the message mentions something unusual (not everyday English, not a name: `Data\common-words.txt`) or sounds like a memory (remember when, that time, last month, months ago...), searches ALL the chat logs for it (2.5 s limit) and puts the hits with the chat around them into the prompt as [PAST CONTEXT]. The prompt tells the AI to understand a reference first (lore, past context, stream history, the log search tool) and to say plainly when it cannot place it, never to pretend. Settings: `PastContext`, `PastContextMs`, `LoreFile`, `CommonWordsFile`.
- `Pipeline\build-lore.mjs` builds `Data\lore.json` from the logs (1,450 phrases today: made-up words, emotes, topics and phrases that burst in time). `Pipeline\build-history.mjs` fills the stream history from Nightbot's game / title updates in the logs, so the bot now knows what was on stream for 236 days (Feb 15 to today); asking about a month ('what did we play in April') shows that month. The history is kept 400 days.
- Rebuild order after importing logs: fetch-chat-logs, build-nicknames, build-profiles, build-lore, build-history. Paste, compile, restart Streamer.bot.

## [NEW][CHAT] A profile file for every chatter (Oct 2026)
- `Pipeline\build-profiles.mjs` reads the logs and writes `Data\profiles\<login>.json` for every chatter with 30+ messages (498 today) plus `index.json` and a README. Each file: activity (messages, active days, first / last seen, trend, typical hours in Central, messages per month), roles seen, community nicknames, pets (only named pets or 'I have a ...'), hobbies (only explicit 'I like / I love / I play ...' statements) and the games they talk about, traits and behavior measured against the rest of the community (very chatty, short messages, night owl, jokester, loud, emote spammer, asks questions, compliments others, helps newcomers, plays customs...), friends in streams (mentions both ways + back-and-forth replies) and 'clash' (heated exchanges; in this community mostly roasting between friends, so only a hint, and marked mostly-jokes when that is the case). A free-text `notes` field is kept when profiles are rebuilt: write what you know there.
- Never stored: age, school, health, politics, religion, sexuality, real names, locations, contact details.
- `PinguinoChat\PinguinoChat.cs` (setting `ProfilesDir`, default `D:\PinguinoSuite\Data\profiles`) puts a short profile card into every reply for the viewer, and into [ABOUT <name>] when someone asks about another viewer. The 'heated exchanges' hint is only given for the viewer being answered, marked private, and the bot is told never to announce who clashes with whom. Rebuild order after importing new logs: `fetch-chat-logs.mjs`, `build-nicknames.mjs`, `build-profiles.mjs`. Paste, compile, restart Streamer.bot.

## [NEW][CHAT] Nicknames + logs folder (Oct 2026)
- The imported chat logs now live in `D:\PinguinoSuite\Data\chat_logs` (the folder was called chat_archive; the old combined 7-day file moved in too). `ArchiveLogsDir` and `fetch-chat-logs.mjs --out` default to it, and the bot also searches the chat it records itself in `%AppData%\BVQ\chat_logs`.
- `Pipeline\build-nicknames.mjs` reads those logs and writes `%AppData%\BVQ\chat_nicknames.json`: the short forms the community really uses for each chatter (looks like a short form of the login, used 10+ times by 3+ different people, and tied to that chatter; ordinary English words only when used 100+ times and clearly theirs). 99 chatters have one (marsh / mello for lvlmarshmello, piney, blizzy, zylo, blake, peng for you...). Hand corrections live in `Data\nickname-overrides.json`; run `node Pipeline\build-nicknames.mjs` again after importing new logs.
- `PinguinoChat\PinguinoChat.cs`: community nicknames are shown to the AI for every viewer and always come first. Only when a viewer has none may the bot choose one (JSON `nick`; short, friendly, never mean, never about looks / age / health); it is saved in that viewer's memory and kept. Paste and compile, restart Streamer.bot.

## [CHANGE][CHAT] Capitalization (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: viewer names are always capitalized in replies (their Display name; an all-lowercase one gets a capital first letter). When the bot is being serious or helpful (the viewer asked for information, or the streamer is giving an order) it writes proper sentences: capital after . ! ? , 'I', closing full stop. In banter it can stay lowercase and loose: the prompt lets the AI choose by mood, and the code leaves a reply alone when it is clearly casual (lol, bro, yo, emoji...).
- Paste `PinguinoChat\PinguinoChat.cs` and compile.

## [NEW][CHAT] Twitch events, supporters view and orders from the streamer (Oct 2026)
- PinguinoChat\PinguinoChat.cs records Twitch events straight from Streamer.bot: ADD THESE TRIGGERS to the PinguinoChat action (Twitch > Subscriptions: Gift Subscription, Subscription, Resubscription; Twitch > Cheer; Twitch > Raid; Twitch > Follow). The bot reads eventType / userName / recipientUserName / bits / viewers / tier, so gifts and who gifted whom, subs, bits and raids are exact. Gift Bomb is ignored on purpose (the individual gift events carry the recipients, so nothing is counted twice). The chat-line parser stays as a fallback and the same event twice within 20 s is stored once.
- [SUPPORTERS] (top supporters by a rough value: gifted sub / sub = 5, 100 bits = 1; top gifters; top cheerers) is given ONLY when the streamer himself asks. Chatters still get no ranking of raids or money.
- Direct orders: the streamer's own messages are orders. The bot never skips him, obeys without sass, and can time anyone out on his word (JSON order_timeout, any length up to 14 days, never him or a bot). The order only counts from the streamer's own account (matched by StreamerName in settings.json), so nobody can fake it.
- Paste PinguinoChat\PinguinoChat.cs and compile.

## [NEW][CHAT] The bot knows the whole community (Oct 2026)
- `Pipeline\fetch-chat-logs.mjs` now pulls every logged day from 2026-02-15 (the earliest any public log site has innocentpenguin_; the stream started early Nov 2025 but that chat was never logged anywhere I could find) using logs.cyex.app, logs.zonian.dev and logs.potat.app: about 660,000 messages in `Data\chat_logs` (55 MB). It also fills `chat_events.json` (subs, resubs, gifted subs, raids, bits; now kept 400 days) and builds `%AppData%\BVQ\chat_profiles.json`: one profile per chatter (first seen, messages, active days, mod / VIP / sub seen, who they talk with). `--rebuild` redoes everything from zero.
- The bot now puts a 'history in this chat' line into every reply for that viewer (and into [ABOUT <name>] when someone asks about another viewer), and [COMMUNITY IN NUMBERS] (size, most active chatters by messages, longest-running regulars, mods seen) when asked about regulars / OGs / how many people. Activity only, never money.
- Log search no longer holds the archive in memory: it streams through the files for each search (a second or two for all 660k lines).
- `chat_study.json` Community note was rewritten from the logs (era, content, culture, regulars) and may now be 1800 characters long (was 900).
- Paste `PinguinoChat\PinguinoChat.cs`, compile, and restart Streamer.bot so it reloads the profiles, events and notes.

## [CHANGE][CHAT] Repeat chatters are not ignored (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: a viewer who pings the bot and gets no answer (the AI skipped, or the 3 s cooldown / hourly cap dropped it) is remembered as waiting. Their next ping carries an [UNANSWERED] note, they count as in the conversation even when all 5 slots are full, and if the AI still tries to skip it is asked once more with a firm 'you MUST answer'. Answering clears it. The prompt now only allows skipping a repeat when the bot already gave that same answer, and never for someone who asked something or pinged before. Still ignored on purpose: viewers told to be quiet (hush), real floods (more than 6 pings a minute), heavy-talk repeats, and the bot's own chime-ins.
- Paste `PinguinoChat\PinguinoChat.cs` and compile.

## [NEW][CHAT] Import chat history from logs.cyex.app (Oct 2026)
- Pipeline\fetch-chat-logs.mjs downloads every logged day of the channel from the public log site https://logs.cyex.app (a rustlog service; innocentpenguin_ goes back to 2026-07-19) into Data\chat_logs\cyex-YYYY-MM-DD.txt (UTC, the bot searches them and shows Central time) AND fills chat_events.json from the real notices in the raw logs (subs, resubs, gifted subs, raids in with viewer counts, bits). Run node Pipeline\fetch-chat-logs.mjs whenever you want to catch up (today and yesterday are refreshed, other days are skipped once downloaded). Options: --since, --list, --no-events, --for-study.
- First run: 91 days, about 203,000 messages, 596 events. Pipeline\fetch-vod-chat.mjs --history added the stream titles of 62 VODs (back to Aug 19) to chat_history.json; downloading VOD chat itself needs TwitchDownloaderCLI because Twitch blocks plain scripts. Restart Streamer.bot after an import so it reloads events and history.

## [NEW][CHAT] The bot can search the chat logs (Oct 2026)
- The chat logs of Oct 11-17 (`Pipeline\logs\10-11.txt` ... `10-17.txt`, next to `combined_chat_7days.txt`) are the bot's archive. `PinguinoChat\PinguinoChat.cs` gives the AI (claude provider) a `search_chat_logs` tool (query words / a user / a day): whenever it needs context about the past it can search the archive (setting `ArchiveLogsDir`, default `D:\PinguinoSuite\Pipeline\logs`, any `*.txt` with lines like `[2026-10-11 23:59:51] #channel user: message`) plus the chat it records itself (`chat_logs\*.jsonl`), at most a few times per reply. Each hit comes with the chat around it. Duplicates across files count once; heavy talk, anonymous and forgotten viewers never come back. Off with `LogSearch: false`.
- Drop new log files into the archive folder any time (they are picked up automatically). The files are UTC but the bot sees and filters them in Central time (the 5 PM stream start), see the README in the folder.
- Paste `PinguinoChat\PinguinoChat.cs` and compile.

## [CHANGE][CHAT] Matches the viewer's tone (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: new top rule MATCH THE TONE: when a viewer asks for information or help and sounds serious, the bot answers directly and correctly with the real info first, no jokes, roasting, sass or slang filler, and says plainly when it does not know (or uses web search). It is playful only when the viewer is. A small heuristic adds a [TONE] hint (real question without joke signs = serious; lol / emoji / banter = playful).
- Fixed a test-only flake: viewers answered in the same second now drop out of the 5 slots oldest first (tie-break counter), so the oldest conversation always goes first.
- Paste `PinguinoChat\PinguinoChat.cs` and compile.

## [CHANGE][CHAT] No ranking of raids or money (Oct 2026)
- PinguinoChat\PinguinoChat.cs: the events lists have no top gifters / top cheerers any more and raids are listed by date, not size. The prompt says never to rank or compare raids, gifts, bits or viewer counts (no top / biggest / most), that every raid and gift is appreciated equally, and that contributions never change how it rates or treats someone. Paste and compile.

## [NEW][CHAT] Events: gifted subs, resubs, bits, follows, raids (Oct 2026)
- PinguinoChat\PinguinoChat.cs reads the announcements the bots already post (gifted sub / resubbed / cheered N bits / just followed / Raid started) and a raider's own 'N raiders from X have joined!' line (trusted only from that account, so viewers cannot fake events) into chat_events.json (90 days). [RECENT EVENTS] (last 3 days) is always in the prompt, the full [EVENTS] (30-day totals, top gifters and cheerers, who raided us and who we raided) when someone asks about subs, bits or raids. What a viewer gave shows as a small plus on their own line.
- BigStreamers (chat_settings.json, default uncle_chay, overtakeblake, onepsynic): the bot knows them as the big streamers of the community and respects them; a raid from one is marked.
- chat_events.json was backfilled from the Oct 10-17 logs: 9 gifted subs, 2 resubs, 3 cheers, 4 raids in (DoctorNopeRope 48), 7 raids out, 19 follows. Restart Streamer.bot so it reloads the file. Paste PinguinoChat\PinguinoChat.cs and compile.

## [CHANGE][CHAT] Not a hype bot, open favorites, money a small part, last week remembered (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: the bot no longer describes its own job ('hyping up the chat'...); it is told it is a chatbot and should just answer. Its favorites are not secret / classified: it picks and says why. Money (subs, bits, donations) is a small plus it notices but never the main thing (kindness, activity, maturity, no spam and what other chatters think count far more; offering money for a better rating counts against). 'sub' is back in the viewer line.
- [RECENT DAYS] now covers the last 7 days (one line each), [STREAM HISTORY] the last 21.
- `chat_history.json` was seeded from the chat logs of Oct 10-17 (Central dates): Roblox + Murder Mystery 2 (10), Find The Needle / Fortnite (11), Rocket League then Minecraft hardcore (12), customs then Roblox + songspot (13), short Rocket League stream (14), RL customs 2v2 + Minecraft (15), RL customs + Fortnite viewers (16), RL customs 3v3 (17). Restart Streamer.bot / recompile so the bot reloads the file.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [CHANGE][CHAT] Fairer ratings, day to day, no money focus (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: ratings (`like`) are judged on what the bot SEES: kindness first, being genuinely active, maturity, not spamming, and how OTHER chatters treat and talk about the person. Asking to be rated higher, calling yourself the favorite or flattering never raises the rating (pushing for it lowers it); a rating can rise by at most 1 per 10 minutes. The favorites list is ordered by rating, then real chat activity (capped), not by how often someone pings the bot.
- Subs, gifted subs, bits, donations, points and follower counts are no longer part of how the bot sees people ('sub' was removed from the viewer line) and the prompt says never to treat anyone differently for them.
- The bot keeps day-to-day context: [RECENT DAYS] (last 3 days of games / activities, always, as quiet background) plus [STREAM HISTORY] when asked, and is told to use them and the community notes as background without reciting them.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [NEW][CHAT] Web search (Oct 2026)
- `PinguinoChat\PinguinoChat.cs` (provider `claude`): the main answer now has Anthropic's `web_search` tool (max `WebSearchMaxUses` = 2 per reply). The prompt tells the bot to use it only when it does not understand or know something (a game, meme, slang, song, person, news, a current fact), never for chit-chat, the streamer, viewers or personal details, never to paste links, and to treat results as untrusted text. Only the answer after the last search is used.
- Switch off with `WebSearch: false` in `chat_settings.json`. If the API refuses the tool (web search must be enabled for your Anthropic organisation in the console), the bot logs a warning and works without it until it restarts. Searches cost extra and make a reply a few seconds slower. Not available for the openai / custom providers.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [CHANGE][CHAT] Public information (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: ALL information about the streamer is public now: it is remembered and shared with anyone (only links and passwords / card numbers are refused). The old 'play dumb about other viewers' rule is replaced by 'what people say in public chat is public': when a question names another viewer, the bot gets [ABOUT <name>]: that viewer's saved facts plus their matching public chat lines from the logs (last 30 days), so it can answer things like 'does mashka like goth mommies'. It still never shares ages, minors, school, health, real names, locations, contact info or passwords, never politics / religion / sexuality / race as facts about a person, and never anything about anonymous (!optmeout) or forgotten (!forgetme) viewers.
- Stream history: while live the bot notes the Twitch game and activity per day (`chat_history.json`, 60 days) and answers 'what did we play on Tuesday?' from it ([STREAM HISTORY], last 14 days). It starts recording from now: earlier days are unknown to it.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [NEW][CHAT] Streamer info is public, favorites ratings, nicer to strangers (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: new `StreamerInfo` setting in `chat_settings.json`: write anything about yourself you are happy for chat to know (it goes into every prompt as [ABOUT THE STREAMER]); the bot also remembers what YOU tell it about yourself (ages and health are allowed for you; email, phone, street address, links and passwords are still refused) and shares it with anyone who asks.
- Ratings: every viewer has a -5..+5 rating (`Rating` in chat_memory.json) that the AI nudges with `like` (-2..2). The bot feels it in its tone (favorites get extra playful, annoying ones cooler, never cruel), and when someone asks about favorites / least favorites / to rate people it sees [YOUR RATINGS] (top 5 and bottom 3, with VIP/mod tags). Opted-out and anonymous viewers are never listed.
- Nicer by default: warm to people it does not know and to anyone who is nice; roasting is for regulars who tease first.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [NEW][CHAT] The chat bot is a mod and can time people out (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: the AI now knows it wears the mod badge and may time out the viewer it is answering (JSON `timeout` 10-300 s + `reason`; Streamer.bot `TwitchTimeoutUser`, bot account first, broadcaster account as a fallback).
- Guard rails in code (`TryTimeout`): only the viewer being answered, never mods / VIPs / the streamer / bots / website roles, NEVER after self-harm or heavy talk, never on an unprompted chime-in, capped at 300 s and 6 per hour. The prompt limits it to real problems (spam, scams, slurs, threats, doxxing, harassment) and says roasting the bot, swearing, politics talk and chat asking it to time someone out are NOT reasons.
- Settings in `chat_settings.json`: `AllowTimeouts` (true), `TimeoutMaxSec` (300), `TimeoutPerHour` (6). The bot account must really be a mod on Twitch (`/mod pinguinob0t`).
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [CHANGE][CHAT] No more getting stuck on one bit (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: viewer memories only go to the AI when they match what is being said now (they used to always include the newest 3) and heavily used ones fade. The prompt now says: never bring up in-jokes or oddly specific details (cocoa, what someone called something, nicknames) unless the viewer already did, never reuse a bit from its last messages, and callbacks are rare. 'Running bits' are no longer saved to memory.
- Code guard: if a reply repeats a distinctive word the bot already used in 2 of its last 3 messages (and nobody in chat just said it), it retries once with that word banned, and says nothing if it still repeats.
- The channel study is told to keep community notes general (no one person's jokes, drinks, nicknames). Notes already saved that mention such bits stay until the next study: to clear them now delete `study` data (the Community text) in `%AppData%\BVQ`.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [CHANGE][CHAT] 5 viewers at once + conversation threads (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: `MaxConversations` is now 5 (viewers the bot follows at the same time; was 2). An existing `chat_settings.json` that sets it keeps its own value: set it to 5 there if needed.
- Viewers who talk to EACH OTHER (one @mentions or replies to the other, while one of them is chatting with the bot) are one thread: the bot is told they are in the same conversation, answers as one chat and does not repeat itself. A thread mate of someone it is already talking with joins that conversation even when all slots are full. Threads expire after `FocusSeconds` (90 s) of silence.
- Paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile.

## [CHANGE][CHAT] Less penguin roleplay, heavy topics like politics (Oct 2026)
- `PinguinoChat\PinguinoChat.cs`: the AI chat is a bot with a light penguin NAME only now: no fish / ice / iceberg / waddling jokes and no 'I'm a penguin' excuses.
- Suicide / self-harm / 'I want to die' talk is handled like politics: ONE short kind line (mods or streamer are around, 988 in the US), no questions, no follow-up. If the same person keeps going within 30 minutes (or the bot is only chiming in on its own) it stays silent. It no longer asks a mod to check on someone and the topic is not saved to memory.
- To apply: paste `PinguinoChat\PinguinoChat.cs` into its Streamer.bot action and compile. Anything in `ExtraPersona` in the chat settings that mentions penguin behaviour should be removed by hand.

## [NEW][KOTH] Activity leaderboard (Oct 2026)
- The King of the Hill leaderboard on the website now shows who is winning in the CURRENT activity (wins since `!activity koth` started), not the all-time standings. The bot publishes it as `board` in the state.

## [NEW][CHECK] problems.json + Re-check / Clear (Oct 2026)
- Every problem and `!check` result is also saved in `%AppData%\BVQ\problems.json` (Id, At, Last, Kind, Message, Count, Status open/fixed) so it can be read, edited and cleared by hand. Problems a later `!check` no longer finds are marked fixed.
- `!problems` (mods) shows how many are open; `!problems clear` empties the file. Add `!problems` as a Streamer.bot command.
- The website's Problems filter has a Re-check button (runs `!check` again) and a Clear problems button.

## [NEW][CHECK] Problems in red, !check, !activity rl|fn (Oct 2026)
- Anything the bot finds wrong (unknown command, an error, a failed OBS or Twitch-category switch, `!check` results) is sent to the website log and shown in RED (Logs pop-out + /mod/log). `!check` (mods) runs a self-test. Add `!check` as a Streamer.bot command.
- `!activity rl|fn <activity>` (e.g. `!activity rl koth`, `!activity fn boxfights`, `!activity fn viewers`): the game prefix keeps names apart AND makes PinguinoB0t switch the OBS scene (even with the auto switch off) and set the Twitch category (`TwitchGameNames` in settings.json, `ActivitySetsGame` to turn the category change off). The Master View's activity buttons use it. Without a prefix `!activity` works as before.

## [NEW][KOTH] King of the Hill activity (Oct 2026)
- `!activity koth`: the queue is open to everyone; the FIRST game being picked closes it and the bot announces who is starting ("KING OF THE HILL IS STARTING (picked by ...)" with @mentions). Winners stay on (`!finish`), teams like competitive. Wins are counted in their own `koth` category (1 point per win) for the King of the Hill leaderboard and never touch the overall Rocket League stats. Overlays show the title "King of the Hill". Paste the new PinguinoBotCore.cs and refresh the overlay sources.

## [NEW][KOTH] KOTH + !finish (Oct 18, 2026)
- `!koth on|off` (mods; `!koth` shows it): king of the hill, OFF by default. `!finish orange|blue` (mods; the Orange wins / Blue wins buttons under the player lists in Master View): records the result, then everyone is out (KOTH off) or the winners stay on and challengers come in (KOTH on). The website and OBS overlays keep showing the finished match with the winner glow for `ResultHoldSeconds` (settings.json, default 8) while the mod page moves on at once. Add `!finish` and `!koth` as Streamer.bot commands.

## [NEW][WEB] SR in the standings (Oct 18, 2026)
- Each standings row now also carries the player's Fortnite SR (10th column), so the website profile can show it next to the Fortnite stats. Paste the new PinguinoBotCore.cs; nothing else to set up.

## [NEW][OBS] Vertical players overlay (Oct 18, 2026)
- New OBS browser source `overlays\players_vertical.html` (about **1080 x 250**, scales to the source size) for the empty space at the bottom of the portrait scene: Blue and Orange side by side, players listed top to bottom. It stays up the whole match (no timer) and the winner glows gold with a WINNER tag. Test: `players_vertical.html?demo`, `?demo=4`, `?demo&win=blue`. The normal `players.html` is unchanged except the clip fix (same 62px spot unless the roster is tall enough to be cut off). The old `lobby.html` was removed.

## [FIX] Players overlay clipped at the top (Oct 18, 2026)
- The slim bar was centred on a fixed 62px line, so with taller rosters (long names wrapped to two lines) its top was cut off at the screen edge. It now positions itself from its real height (top edge 12px from the top) and long names are cut with ... instead of wrapping. Refresh the Players browser source in OBS.

## [NEW][STRIKES] Strikes + coloured team chat (Oct 18, 2026)
- **Strikes (0-3):** mods use `!strike @user` / `!unstrike @user`, anyone can use `!strikes [@user]`. 3 strikes = the player can't `!join` (and is taken out of the queue). Every time the stream goes live everybody loses one strike (checked every 30 s through the website; a reconnect within 30 minutes doesn't count). Add `!strike`, `!unstrike`, `!strikes` as Streamer.bot commands. Strikes show on the website profile.
- **Team announcements** are two messages now: `/color blue` + `/me` Blue team, `/color coral` + `/me` Orange team, then `/color chocolate` (setting `ChatColors`, `BlueColor`, `OrangeColor`, `DefaultColor`). Needs `CPH.SendAction` (standard). If Twitch ignores `/color` from the bot, set `ChatColors` to false.

﻿## [FIX] Queue cleared as soon as the match ends (Oct 16, 2026)
- Recording a result (!win / the Orange-Blue wins buttons / !next <team>) now kicks everyone who played from the queue right away (the streamer goes back to the front), instead of waiting for !next. "Orange stays" / "Blue stays" re-adds the staying team.

# PinguinoBot Core: what changed (for Ivan + Circuit)

The code is in `PinguinoBotCore.cs`. In the code, each change is tagged `[FIX]`, `[NEW]`, `[CIRCUIT]` or `[NOTE]`.

## ⚠️ Do this first
- **Revoke the Tracker Network API key** that was hard-coded in the old file (`1aa7bbd1-…`). The bot never used it, but the key was in the source, so treat it as leaked.

## Bugs fixed
| Problem | Effect before | Now |
|---|---|---|
| `!reroll` re-ran the same balancing search | Usually gave the **same teams** | Picks at random from fair splits (within `RerollToleranceMmr`) that differ from the current teams |
| `!reroll` added a new match record each time | Match history filled up with duplicates | Updates the current match in place |
| `!reroll` with too few replacements | Pulled players were left stuck as "active" | Checks first and changes nothing if it can't refill |
| `!next blue` with too few players | Losers were already rotated out, so the queue was left half-rotated | Checks first and only then rotates |
| `!next blue` after switching to a smaller format | Winners didn't fit on one team, so it crashed | Does a full rotation instead |
| Lobby was only kept in memory | A Streamer.bot restart wiped the teams | Saved to `current_match.json` |
| Commands didn't lock shared data | Two `!join`s at the same moment could corrupt the queue | Every command runs under a lock |
| Mod `!register` split on the first space | Epic names with spaces were misregistered | Mod override is now `!register @viewer Epic Name` |
| curl had no timeout and stderr was never read | The bot could hang or deadlock | `--max-time`, stderr is read, and a hung curl is killed |
| TRN sent back HTML or a null rating | Exceptions | Treated as an API error, and registration still works |
| Player with no GameId | NullReferenceException | Falls back to the stored MMR or the default |
| JSON files were written in place | A crash or website read mid-write could see a corrupt file | Writes a temp file, then swaps it in |
| MMR always came from the 2v2 playlist | 3v3 lobbies were balanced on 2v2 MMR | Uses the playlist that matches the format, falling back to the best ranked playlist |

## New (Circuit's priorities)
- **#1 team modes:** `!mode balanced|random|picks`. In picks mode, `!balance` pulls the players and then you use `!pick a b c` (those go Blue) or `!pick auto`.
- **#4 progression:** `!win blue|orange` records wins, losses and points (`PointsWin` / `PointsLoss` in settings.json). `!next blue` also records the result, once per match. New commands: `!stats [user]` and `!top`.
- **True King of the Hill (optional):** with `KothKeepWinnersTogether: true`, the winning team stays together and plays the challengers.
- **`!setmmr user auto`** clears a manual MMR so Tracker Network is used again.
- **Website and OBS bridge, "one action, one synchronized result":** every state change writes `%AppData%\BVQ\live_state.json`. It holds the queue, open/closed, spots needed, current match (Blue/Orange/averages/live or finished) and a `lastEvent` with a `seq` that goes up on each change.
  - OBS browser source and the website poll the file. When `seq` changes, they play the animation for `lastEvent.type`: `queue_open`, `queue_close`, `queue_update`, `teams_selected`, `picks_pending`, `match_result`, `settings`.

## Suggested next steps for Circuit
1. Put a small local HTTP server or websocket in front of `live_state.json` (Streamer.bot's websocket server works, or a tiny Node service) so the website and OBS get pushes instead of polling.
2. Website "Orange Wins" button → call this same action with `command=!win`, `rawInput=orange`, so chat and web share **one** code path.
3. Move the JSON files to a real database (SQLite or Postgres) when the website goes live. The data models already match the tables.

## [NEW][OBS] OBS defaults changed + streamer switch (Oct 16, 2026)
- The OBS **auto switch is now ON by default** (turn it off with `!obs auto off` or the Master View checkbox) and the default scenes are only **Rocket League** and **Fortnite** (Starting Soon / Be Right Back were removed). A one-time migration (`ObsMigrated`) applies this to your existing settings.json: auto ON, and the two old default scenes removed (add your own scenes back to `ObsScenes` any time).
- Turning the streamer's PLAYING switch back on (`!streamer in`) now puts him straight back in the queue at #1, and into the empty seat of a running match if there is one.

## [NEW][OBS] OBS control from the website (Oct 16, 2026)
- Streamer.bot talks to OBS, so PinguinoB0t can now: `!scene <label>` (switch scene), `!source <on|off|toggle> <label>` (show / hide a source) and `!obs auto on|off` / `!obs status` (mods only). The Master View's new OBS box sends the same commands.
- Setup in `settings.json` (defaults are created on the next start): `ObsScenes` (label -> OBS scene name), `ObsSources` (`Label`, `Scene` ("" = all scenes), `Source`), `ObsGameScenes` (Twitch category -> scene label), `ObsAutoSwitch` (false by default), `ObsEnabled`. **Names must match OBS exactly.** In Streamer.bot make sure OBS is connected (Stream Apps > OBS Studio).
- Auto switch: follows the Twitch category (checked every 30 s through the website's `/api/game`) and also switches when a mod starts a Fortnite activity while on the Rocket League scene (and back).
- The OBS calls are made by name (reflection), so the file compiles even if a method is missing in your Streamer.bot version; if OBS isn't reachable the bot says so in chat. Paste the new `PinguinoBotCore.cs` into BVQ Engine and Compile.

## [NEW][OBS] Overlays updated (Oct 16, 2026)
- **queue.html** now looks like the site's queue (gold NEXT rows, tan BACKUP, grey rating, `| display name`, STREAMER tag) and its **title says what is being played**: Competitive Customs, Casual Customs, Playing with Viewers, Fortnite Boxfights, Fortnite Zone Wars... plus the team size and game mode (Dropshot / Rumble, casual Groups / Random teams). Ratings are labelled MMR or SR (Fortnite). Gold counts the real number of seats (e.g. 5 in 3v3 while the streamer plays).
- **It only pops up** for `POP_SECONDS` (12) when someone JOINS the queue or someone types `!queue` (the bot now sends a `queue_show` event for `!queue` / `!queue list`). It is hidden the rest of the time.
- **Never together with the players overlay:** the queue card stays hidden while a match is running and for 20 s after a result (the same time players.html stays up).
- **players.html** titles now show the activity; casual "group" matches show ONE "IN-GAME" panel (no Blue / Orange); the average line says avg MMR or avg SR.
- OBS: nothing to re-add; the browser sources read the same files. Press the source's Refresh (or restart OBS) once so it loads the new HTML. Preview without the bot: `queue.html?demo`, `players.html?demo`. Paste the new `PinguinoBotCore.cs` too (it sends `queue_show`).

## [NEW][WEB] Casual style: group or teams (Oct 16, 2026)
- New setting `CasualStyle` ("group" default | "teams") and mod command `!casual group|teams`. Group = the old casual behaviour (one group announced, no Blue/Orange); teams = random Blue/Orange like Viewers. `MatchRecord.Group` remembers which style a match was made with; the state carries `casualStyle` and `currentMatch.group`. Paste the new `PinguinoBotCore.cs` into BVQ Engine and Compile.

## [NEW][WEB] Fortnite customs: Boxfights, Zone Wars, SR (Oct 16, 2026)
- New activities: `!activity boxfights|zonewars|fnviewers` (Fortnite customs and Playing with Viewers). Boxfights/Zone Wars behave like competitive (balanced teams, stats count); fnviewers like Viewers (random, no stats).
- Fortnite uses **SR** instead of MMR: `!setsr @user <0-5000> [self]` (mods), `Player.Sr` / `SrSource`, `DefaultSr` = 1000 in settings. Balancing, the queue and the state use SR while a Fortnite activity runs (state `game: "fortnite"`).
- Fortnite stats go to `Player.Modes["boxfights"|"zonewars"]` only (the overall Rocket League wins/points are untouched); `MatchRecord.Category` is the activity name.
- Tests: `Tests\core\harness.cs` "FORTNITE" checks. Paste the new `PinguinoBotCore.cs` into BVQ Engine and Compile.

## [NEW][WEB] Casual customs = groups, not teams (Oct 16, 2026)
- In the casual activity the bot announces ONE group ("Casual group (3v3): a, b, c, d, e, f") instead of Blue/Orange teams. Internally the group is still split in two so !next, !out, !in keep working; the state carries currentMatch.group = true and the website shows a single grid. Competitive and Viewers are unchanged.

## [NEW][WEB] Game modes + per-mode standings (Oct 16, 2026)
- New setting `GameMode` (standard | dropshot | rumble) and mod command `!gamemode <standard|dropshot|rumble>` (also in the website's Master View). The state sent to the website includes `gameMode`.
- Stats are now also kept per category in `Player.Modes` (wins, losses, points): standard matches count under their format (2v2, 3v3, 4v4), Dropshot and Rumble under their own name. `MatchRecord.Category` remembers it, so `!matchwin` / `!matchdel` fix the right tab.
- `!format` now accepts 1v1 to 4v4 in every game mode. Switching to Dropshot or Rumble sets the size to 3v3 (change it after with `!format`).
- The web sync sends `modes` with the standings, and `category` with each match.
- On first start `BackfillModes()` rebuilds per-mode stats from `matches.json` (newest 100 matches); overall totals are untouched.
- Paste the new `PinguinoBotCore.cs` into BVQ Engine and Compile. (Tests: `Tests\core\run-tests.ps1` ALL BOT CHECKS PASSED.)

## [NEW][WEB] Match history fixes (Oct 15, 2026)
- `MatchRecord` now stores `Activity`, `Counted`, `PtsWin`, `PtsLoss` so a match can be corrected exactly later.
- New mod/privileged commands: `!matchwin <id> <blue|orange>` (change who won; wins, losses and points are reversed and re-applied) and `!matchdel <id>` (remove a match and take back its stats; refused for the current lobby's match). The site's /matches page sends them.
- Web sync step 4 posts the newest 100 matches to `/api/bot/matches` (when changed + every 5 min).
- Backup of the previous file: `PinguinoBotCore.before-matchfix.cs`. Paste the new `PinguinoBotCore.cs` into BVQ Engine and Compile.

## [NEW][WEB] Website bridge (innocentpenguin.com/customs), Oct 15, 2026
Viewers can **Join/Leave** from the website, and mods get **Match Controls** at `/mod/customs`. The site shows **Orange vs Blue** live.

**How it works (your PC only makes outgoing calls; nothing is opened to the internet):**
- A Streamer.bot **Timed Action** runs this same action every 3 seconds. That tick (`HandleWebSync`):
  1. Fetches waiting website requests from `/api/bot/commands`.
  2. Runs each one through **`RunCommand()`**, the exact code chat commands use, so `!join` from the site equals `!join` in chat, chat reply included.
  3. Posts the bot's replies to `/api/bot/results`, so the site shows them under the button.
  4. Posts `BuildLiveState()` (the same data as `live_state.json`) to `/api/bot/state` whenever it changed, and every 30 s as a heartbeat. The site shows "PinguinoBot offline" when it hasn't heard from the bot for 15 s.
- Code changes: `Dispatch()` → `RunCommand()` split; `PublishState()` now uses `BuildLiveState()`; `Say()` also captures replies during a web request; new settings `WebSyncUrl` and `WebSyncKey`.
- Chat behaviour is unchanged. A backup of the previous file is `PinguinoBotCore.before-websync.cs`.

**Setup (one time):**
1. Pick a long random key, for example run `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`.
2. In **Railway → Variables**, add `BOT_API_KEY` = that key.
3. In `%AppData%\BVQ\settings.json`, set `"WebSyncKey": "<the same key>"`. `"WebSyncUrl"` defaults to `https://innocentpenguin.com`. Keep this file private, since the key is a password.
4. In Streamer.bot, paste the new `PinguinoBotCore.cs` and **Compile**.
5. **Settings → Timers → Add**: name it exactly **`PinguinoBot Web Sync`**, interval **3 seconds**, enabled.
6. On the PinguinoBot action, **Add trigger → Core → Timed Actions → `PinguinoBot Web Sync`**.
7. Test it: open `innocentpenguin.com/customs`. The "PinguinoBot offline" pill should disappear within a few seconds.

**Not tested yet (needs Streamer.bot):**
- The C# hasn't been compiled. The website side was tested with a fake bot (`npm run fake-bot` in the site project).
- Assumption: Streamer.bot passes `timerName` to timed-action runs. If the sync never starts, check the action's log for `[BVQ]` lines and tell Claude/Circuit.
- "Streamer in/out" on the website joins or leaves the queue as `innocentpenguin_`, so that name must be `!register`ed like everyone else.

## [NEW][WEB] Website-only players (no Twitch account)
- Viewers who log in on the site with YouTube, Kick or TikTok, and have no Twitch linked, play under their **site ID**, e.g. `kick-penguinkick`. Twitch names can't contain a dash, so these never clash with a Twitch viewer.
- They register on the website ("Your Epic name" box). The site sends `!register Their Epic Name` as that ID, using the same `HandleRegister` as chat. Nothing changed there.
- Their requests arrive with `quiet: true`. While `_quiet` is set, `Say()` doesn't post to Twitch chat; the reply only shows on the website.
- Mod-run commands (`!balance`, etc.) still post normally. Teams in chat show the site ID for these players; the website shows their real display name.
- If a website-only player links Twitch later, they switch to their Twitch name. They register again, and old points stay under the old ID.

## [NEW][WEB] Streamer priority + Epic names on the site
- **The streamer always plays.** New setting `StreamerName` (default `innocentpenguin_`). When he `!join`s (or a mod flips "InnocentPenguin in" on the website) he goes to **#1 in the queue**, and after each match (`!next`) he goes back to the **front** instead of the back. So he's in every match while he's queued. `!leave` / the switch off takes him out.
- `live_state` now includes each player's registered **Epic name** (`epic` in the queue, `Epic` in the teams). The website shows players as **"Platform name | Epic name"**.

## [NEW][WEB] Epic name comes from the website
- Members set their Epic name once in the site's **Settings** (it's locked there; a mod unlocks it to change it).
- Website `!join` requests now carry `epic`. Before running `!join`, the bot registers that name if the player isn't registered or the name differs (`HandleRegister` with privileged = true, so it can update an existing name). The register reply is dropped; the viewer only sees the join reply.
- Chat `!register` still works as before for Twitch-chat players.

## [NEW][WEB] Chat updates for website actions + online detection
- **Website actions now show in Twitch chat too.** Before, website-only players' replies stayed on the site. Now they post in chat with the player's site display name instead of the ID, e.g. "PenguinKick (web) You joined the queue at position #4!". The site sends `name` with each command.
- **"Online" means Streamer.bot is running**, not that you're live. The `PinguinoBot Web Sync` timer sends a heartbeat every 30 s whenever Streamer.bot is open. The timer-name check now ignores upper/lower case and extra spaces.
- **It works over the internet already:** your PC calls out to `https://innocentpenguin.com` (outbound only, like a browser). Nothing to port-forward. It just needs the setup steps above (same key in Railway `BOT_API_KEY` and `settings.json` `WebSyncKey`, plus the 3-second timer). To test against your local site instead, set `"WebSyncUrl": "http://localhost:3000"` temporarily.

## Not tested
I couldn't compile this outside Streamer.bot (the `CPH` object only exists there). Paste it in, click **Compile**, and try `!queue open → !join ×6 → !balance → !reroll → !win blue → !next blue` before going live.

## [NEW][WEB] Auto sync (no timer needed), Oct 15 2026
- Streamer.bot's log showed the `PinguinoBot Web Sync` timer never ran, so the website never heard from the bot.
- Now the first time the action runs (any chat command, like `!queue open`), PinguinoB0t starts its own background sync every 3 s. It keeps going while Streamer.bot is open, live or not, so the website shows **online** and `!queue open` in chat appears on the site within ~3 s.
- After Streamer.bot restarts, the sync starts again on the first chat command. (The timer is now optional; if you add it, it just starts the sync sooner.)
- Pressing Compile again doesn't create a second sync: a newer copy takes over and the old one stops.
- Backup of the previous file: `PinguinoBotCore.before-autosync.cs`.

## [NEW][WEB] Penguin League + auto members, Oct 15 2026
- The bot now sends the **league table** (every registered player's Epic name, wins, losses, points) to the website: right away when it changes, and every 5 minutes. It shows at innocentpenguin.com/standings.
- The website turns every **Twitch chat player** the bot knows (registered players, queue, teams) into a site member automatically, with their Twitch name/picture and their registered in-game name (locked). If they log in with Twitch later, they take over that profile.
- Backup of the previous file: `PinguinoBotCore.before-league.cs`.

## [NEW] Twitch IDs + junk cleanup, Oct 15 2026
- **[FIX] Players are now keyed by Twitch login, not display name.** `user` in Streamer.bot is the display name (can be e.g. Japanese); the login (`userName`) is what Twitch and the website use.
- **Twitch IDs:** every chat command stores the player's permanent Twitch id. If someone renames on Twitch, their record, stats and queue spot move to the new name automatically the next time they type a command. Old records saved under a display name move to the login the same way.
- **Junk cleanup on load:** players whose "name" isn't letters/numbers/_/- (made by old mistyped commands like `!register {your epic}`) are removed: `<speed`, `(epic`, `{`. Real names in any language are kept.
- The league table sent to the website now includes the id, so the site links renamed people correctly.
- Backup: `PinguinoBotCore.before-ids.cs`.

## [NEW][WEB] Streamer plays by default, Oct 15 2026
- New setting `StreamerPlaying` (default **true**). Making teams (`!balance`, `!next`, `!next blue|orange`) now adds `innocentpenguin_` to the front automatically while it's true, so he's in every match without typing `!join`.
- New mod command **`!streamer out`** = sitting out (removed from the waiting line; his seat goes to the queue). **`!streamer in`** = back in. The website's InnocentPenguin switch sends these. His own `!leave` / `!join` flip it too.
- The website shows **5 gold** (next up) in 3v3 while he plays, **6** while he sits out; the 2 after that are backups.
- Backup: `PinguinoBotCore.before-streamer.cs`.

## [NEW][WEB] Activities, kick-after-play, drag & drop, MMR sources, Oct 15 2026
- **Activities:** new setting `Activity` (`competitive` default, `casual`, `viewers`, `none`) and command **`!activity <competitive|casual|viewers|end>`** (mods). Starting one clears the previous queue and opens the queue for the new one (the streamer is added automatically). `end` closes and clears it. Only **competitive** balances teams (your `TeamMode`) and records wins/losses/points; **casual** and **viewers** always use random teams and record nothing ("casual: no points").
- **Kicked after play:** `!next` / `!next blue|orange` now REMOVES everyone who played from the queue (they `!join` again). Before, they went to the back of the line. The streamer goes back to the front. Winners only stay on if `KothKeepWinnersTogether` is true.
- **Drag & drop commands (mods):** `!out <user>` (takes a player out of the live match, leaves an empty slot, player goes to the front of the queue), `!in <user> <blue|orange>` (fills an empty slot, or moves a player between teams), `!move <user> <pos>` (reorders the waiting line). Team averages are recalculated.
- **MMR sources:** `!setmmr @user N` = set by a mod (`manual`), `!setmmr @user N self` = set by the player (the website's Settings uses this). Both beat the Tracker value. `!setmmr @user auto` goes back to the tracker. The website now receives each player's MMR and its source (`tracker` | `mod` | `self` | `default`).
- The league table sent to the website now carries MMR + source (columns 7-8).
- **Tracker Network is blocking automated requests** ("You've Been Blocked", Cloudflare), so tracker lookups mostly fail and players fall back to the default 800 unless a mod or the player sets MMR. The "peak of the last 6 months" idea is NOT built (needs an unblocked data source).
- **Tests:** `D:\PinguinoSuite\Tests` compiles this file against a stub Streamer.bot and runs 28 logic checks: `powershell -ExecutionPolicy Bypass -File Tests\core\run-tests.ps1`. They use a throwaway data folder (`BVQ_DATA_DIR`), never `%AppData%\BVQ`. First run found and fixed a scoping error (lambda parameter shadowing a local).
- Backup: `PinguinoBotCore.before-activities.cs`.

## Tracker MMR (Oct 15 2026): research result + change
- **Finding:** there is no allowed, working automated source of Rocket League MMR. Tracker Network has no public RL API (the api.tracker.gg endpoint the bot used is the website's own, behind Cloudflare, and their terms forbid scraping); Epic/Psyonix publish no rank API; third-party paid APIs (e.g. on API marketplaces) are unverified. Peak-of-6-months isn't exposed by any of them for free.
- **Change:** `TrackerLookupEnabled` (settings.json, default **false**). With it off the bot no longer calls Tracker at all (before, each unregistered-MMR player cost 2+ s and always failed). If it is turned on and Tracker answers with a block page, lookups pause for 1 h. Mod ("manual") and self values still always win; `api` source only appears if lookups are enabled and succeed.
- **Recommended flow:** players set their own MMR once in Settings (source "self"); mods can `!setmmr @user N`. Revisit only if Tracker Network grants official API access.

## [CHANGED] Activity switch keeps the waiting line, Oct 15 2026
- `!activity <competitive|casual|viewers>` now ends the current match: everyone who was PLAYING is removed from the queue, but players who were WAITING stay in line. (Before, it cleared the whole queue.) `!activity end` still closes the queue and clears everyone.
- Test: testsharness.cs ("people waiting in the queue stay").

## [CHANGED] "Orange stays" / "Blue stays" really keep that team, Oct 15 2026
- `!next blue` / `!next orange` now ALWAYS keeps the named team for the next match (they are mixed with the new challengers unless `KothKeepWinnersTogether` is true); everyone else who played is kicked. Plain `!next` = everyone out. (After the kick-after-play change these only worked when `KothKeepWinnersTogether` was on.) The team you name stays even if the recorded result was the other team; the result/points still come from `!win` (or from this command if no result was recorded).
- The website's Master View has a Next match mode picker that sends these. Test: testsharness.cs ("Blue stays").
- Backup: `PinguinoBotCore.before-staymode.cs`.

