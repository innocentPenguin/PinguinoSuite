# PotatBotat + Nightbot removal audit

Written by Runner 2 for 00, 2026-10-20. Read-only: nothing was built, launched or pushed. No secrets in this file.

**Evidence base:** chat logs `Data\chat_logs\2026\` (256 day files, 2026-02-15 .. 2026-10-20, 670,101 lines), our command list from `GET /api/commands-doc` (155 viewer / 53 mod / 115 channel-lore), `Docs\STREAMERBOT_REPLACEMENT.md`, `Docs\HELPER_FACTS.md`, `Docs\imports\nightbot-custom-commands.txt` (142 command names), `Docs\APP_LOG.md`, and the Host source (`PinguinoHost\*.cs`).

**How counts were made.** A "use" is a viewer line that starts with the trigger. A reply is credited to a bot when that bot posts within 6 seconds. Bot lines are 977 (PotatBotat) and 31,720 (Nightbot). Limits are listed in section 6, and they matter for the verdicts.

## Verdicts

| Bot | Verdict |
|---|---|
| **PotatBotat** | **Not quite safe to remove.** Removing it loses mod-only 7TV emote add/remove, `#gpt`, and the log-lookup commands. It never ran gamble, slots, duels, points or burgie. Details in section 1. |
| **Nightbot** | **Not safe to remove yet.** The 12 repeating timers are 62% of its output, and none of them is turned on in our Host. Mods use its `!title` and `!game` constantly, and we have nothing for them. Its spam filters can't be checked from the logs (section 6). Details in section 2. |
| **StreamElements** | **Not safe to remove yet; remove last.** It runs the points games (`!gamble` 20.9k requests, `!slots`, `!give`), which our Host economy (9122ce7) does not have. Alerts, tips and the store leave no chat trace, so Ivan checks the dashboard. Details in section 7. |

Nightbot outranks PotatBotat by roughly 30 to 1 in volume, and nearly every viewer sees it. Do Nightbot's build list first.

---

## 1. PotatBotat (prefix `#`), 977 bot lines, 2026-02-15 .. 2026-10-20

Names in the logs carry invisible zero-width characters; counts below are after cleaning them.

| Feature | Uses (users) | First .. last | Our coverage |
|---|---|---|---|
| `#gpt` (AI answer; `#got` is a typo alias) | 176 (25) | 03-03 .. 10-19 | **Partial.** ChattyPinguino and HelperPinguino answer chat. Chatty's chatting is switched OFF (training mode, `HELPER_FACTS.md`). Nothing answers a `#gpt <question>` command. 22 of the replies were "please formulate a question with at least three words" errors. |
| `#add` (7TV emote add, mod only) | 93 (2) | 02-20 .. 07-14 | **NOT covered.** `HostEmotes.cs` reads emote usage only (`!emote`, `!topemotes`), with no 7TV add. |
| `#remove` / `#r` (7TV emote remove) | 18 / 8 (1) | 02-26 .. 07-13 | **NOT covered.** Same as above. Emote "Added/Removed" replies run to 10-12. |
| `#topchatters` (+ `#top`, `#topchatter`, `#chatters`, `#topchats`, `#toponline`) | about 97 (10) | 03-03 .. 10-19 | **Covered.** `!topyappers` (Leaderboards) lists top chatters by message count, all time or per month. |
| `#fl` / `#firstline` (first line a user wrote) | 52 (14) | 04-16 .. 10-19 | **NOT covered.** We have the logs but no command. |
| `#rl` (random line from a user) | 14 (6) | 04-16 .. 10-19 | **NOT covered.** Note `!rl` in our list is the Nightbot rank lore command and is unrelated. |
| `#ls` / `#lastseen` (last message seen from a user) | 32 (6) | 02-15 .. 10-20 | **NOT covered.** |
| `#ml` / `#rolelookup` (mod/role lookup) | 21 (10) | 02-28 .. 10-17 | **NOT covered.** Low value; it shows Twitch role data. |
| `#translate` | 21 (7) | 02-15 .. 09-26 | **NOT covered.** Auto language detection, replies like "JP -> US". |
| Winner/loser of the day/week/month/year (`#wotd #lotd #wotm #lotm #woty`) | about 52 (4) | 02-15 .. 07-20 | **Partial.** `!topyappers` ranks by period, but there is no "winner of the day" announcement. |
| `#subage` | 14 (1) | all on 03-03 | **Partial.** `!sub` shows tier, months and streak from our subscribers data. |
| `#isbanned` / `#banned` | 13 (2) | 04-07 .. 07-03 | **NOT covered.** Low value. |
| `#user` (Twitch user info) | 6 (3) | 04-07 .. 06-13 | **NOT covered.** Low value. |
| `#linecount` | 3 (3) | 04-24 | **Partial.** `!topyappers` shows counts, but there is no per-user lookup. |
| `#uptime` / `#myuptime` | 5 (1) | 06-25 .. 07-17 | **NOT covered.** Neither is `!uptime` (see StreamElements). |
| `#pyramid` | 6 (1) | 03-03 .. 03-15 | **NOT covered.** Test use by one person; about 196 reply lines. |
| `#8ball` | 4 (1) | 03-03 .. 06-23 | **Covered.** `!8ball`. |
| `#quiz` / `#answer` (potato trivia) | 2 / 8 | all 03-03 | **Not needed.** One day of use. |
| `#followage` / `#followers` | 3 | 03-03 .. 06-17 | **NOT covered.** StreamElements `!followage` does it (454 replies). |
| `#rank` ("farmed" potato game) | 2 | 08-08 | **Not needed.** Replies were "hasn't farmed yet". |
| `#ping`, `#always`, `#vanish`, `#ban`, `#timeout`, `#spam`, `#ambassador` | 1-3 each | 03-03 .. 10-19 | **Not needed.** Admin and error replies only. |
| Game / title changes by mod LvLMarshmello | 12 game + 8 title replies | 10-05 .. 10-17 | **NOT covered. Active and recent.** The trigger line isn't in the logs. `STREAMERBOT_REPLACEMENT.md` records that Ivan dropped title/game changes ("he will make his own"). |
| Random clip ("Random clip from #InnocentPenguin_") | 2 replies | 10-19 | **NOT covered.** Trigger not logged. |

**What PotatBotat never did in these logs:** gamble, slots, duels, points and burgie. A quoted `!slots 250` appears only inside an `#rl` reply, and `#gamble` on 06-02 got "you don't have any potatoes to gamble" (1 use, 1 user). Those features belong to StreamElements, section 3. The `!burgie` lines (559 uses since 08-15) are viewers talking to the Burgie's Cozy Kitchen game, which has no chat bot reply; Nightbot's `!burger` / `!burgie` link is the only bot involvement.

### PotatBotat must-build before removal, ranked by usage

1. `#gpt`-style AI question command (176 uses). Or accept losing it; most uses are one-off curiosity.
2. 7TV emote add/remove for mods (93 + 26 uses, 2 users). Needs a 7TV editor token. A mod-only feature.
3. Title and game change for mods (20 uses in 12 days, rising). Needs the Twitch `channel:manage:broadcast` scope plus a Host step. Nightbot's `!title` and `!game` are the same need (section 2), so building it once settles both bots.
4. Log lookups `#fl`, `#rl`, `#ls` (98 uses), `#translate` (21). Our own `Data\chat_logs` can answer them cheaply; optional.

Everything else is already covered or too rare to matter.

---

## 2. Nightbot, 31,720 lines, 2026-02-15 .. 2026-10-20

The 145 imported custom commands are now served by the Host as channel lore (`channel_lore.json`; `APP_LOG.md` 2026-10-20 06:20: "135 imported, 16 exact-command-only"). This section is about everything else.

### 2a. Repeating timers (about 62% of all Nightbot lines)

Cadence is the median gap between consecutive posts, in minutes. Our Host has a timers module (`HostTimers.cs`, `Data\runtime\timers.json`), but only 3 generic timers are seeded and **all are disabled**. None of Nightbot's wording is carried over.

| Nightbot timer (reply text) | Lines | First .. last | Gap | Our coverage |
|---|---|---|---|---|
| "Say hi ... to let us know you are here!" | 3,193 | 02-17 .. 10-20 | 20 min | **NOT covered** |
| Amazon Prime free sub reminder (`!prime`) | 3,156 | 02-17 .. 10-20 | 24 | **NOT covered** (`!prime` itself is covered) |
| "Don't forget to leave a follow..." | 2,893 | 02-18 .. 07-10 | 16 | **Partial.** Our `follow` timer exists with different wording; off |
| Join the community Discord | 2,765 | 02-16 .. 07-10 | 15 | **NOT covered** (`!discord` covered) |
| "Want to interact with the stream? Try these commands..." | 1,721 | 02-17 .. 10-14 | 30 | **Partial.** Our `commands` timer, a link to /help; off |
| Daily Streams @ 5pm CDT | 1,871 | 04-23 .. 07-10 | 12 | **NOT covered** |
| "Use !support to see how you can support..." | 1,196 | 04-08 .. 10-14 | 31 | **NOT covered** |
| All my socials: linktr.ee/InnocentPenguin | 800 | 04-27 .. 07-10 | 22 | **NOT covered** |
| About-Ivan blurb ("I'm Ivan. I am a college student...") | 531 | 02-17 .. 07-09 | 60 | **NOT covered** |
| Daily RL Customs / Minecraft SMP schedule | 415 | 04-06 .. 04-23 | 17 | **NOT covered** |
| smp / hc server addresses | 73 | 10-03 .. 10-16 | 11 | **NOT covered** (HelperPinguino answers the IP on request) |

The timers have been on for most of the year and then drop out around 07-10; the follow, discord, socials and daily-stream lines stop on **2026-07-10**, the day synchrabot started posting the same timers (see SYNCHRABOT_AUDIT.md), so those timers were taken over, not abandoned. The prime, hi and interact timers are still running as of this week. A "WWW!!!!" line (1,052, 03-26 .. 05-02) looks like a custom-command or point reply; its trigger isn't clear.

### 2b. Commands Nightbot answered

| Command | Uses answered by Nightbot | First .. last | Our coverage |
|---|---|---|---|
| `!lurk` / `!unlurk` | 763 / 26 | 02-16 .. 10-20 | **Covered** (channel lore) |
| `!pm` (private match name/password) | 317 | 03-06 .. 10-19 | **Covered** (`!pm`, shared setting; mods can set) |
| `!ip`, `!server`, `!mcrules`, `!discord`, `!dc` | 195 / 42 / 8 / 113 / 15 | 02-17 .. 10-16 | **Covered** (channel lore; HelperPinguino for questions) |
| `!ban` (joke), `!vanish` | 133 / 131 | 02-16 .. 10-19 | **Covered** (channel lore) |
| `!time` | 107 | 03-01 .. 10-06 | **Covered but broken at source**: Nightbot's own reply was the literal text `${time}` (107 times). Ours is a working `$(time US/Central)` line. |
| `!drops`, `!prime`, `!support`, `!tts`, `!7tv`, `!specs`, `!streamingpc` | 73 / 32 / 12 / 39 / 9 / 19 / 16 | 02-16 .. 10-19 | **Covered** (channel lore) |
| `!cups`, `!goon`, `!w`, `!zylo`, `!phil`, `!67`, `!burger`, `!fahh` and about 90 more jokes | 10-55 each | across the year | **Covered**: 115 channel-lore commands |
| 24 custom commands NOT imported: `!goon` (63 uses), `!cpu` (55), `!of` (38), `!hebunga` (14), `!gay` (12), `!racist`/`!racism` (13), `!topgooner` (8), `!purge` (7), `!vc` (6), `!banlist` (5), `!tinder`, `!pinguino`, `!trapaccount`, `!onlyfans`, `!feetfinder`, `!grindr`, `!twerk`, `!weiner`, `!intro`, `!stop`, `!test`, `!cmds` (14) | 1-63 each | 02-15 .. 10-19 | **NOT covered.** These exist in the Nightbot export but not in our command list. Some are crude or off-colour jokes, so this may be a deliberate omission. Ivan should confirm, because `!goon` and `!cpu` are used often. |
| `!song`, `!sr`, `!skip`, `!wrongsong`, `!volume` | `!song` mostly answered by **pinguinob0t** (867 of 1,370 uses), not Nightbot | 02-15 .. 10-20 | **Covered but not live.** A song-request module exists (`HostAuto.cs`, `HostSpotify.cs`: `!sr`, `!skip`, `!song`, `!oops`/`!wrongsong`, queue). Its code comment says to enable it when "Nightbot/StreamElements stop answering `!sr`". Nightbot's own songrequest is nearly dead: 17 `!skipsong` replies were all "no song" errors, and `!volume` got 6 replies. |
| `!commands` / `!cmds` | 50 / 7 | 02-15 .. 10-19 | **Covered** (`!commands` points to the site /help page) |
| `!title` | 212 replies | 03-02 .. 10-19 | **NOT covered.** Mod command; many replies are "Twitch API returned an error". |
| `!game` | 129 replies | 03-24 .. 10-19 | **NOT covered.** Mod command; "The stream game has been updated to: X". |
| `!addcom` / `!editcom` / `!delcom` | 195 / 260 / 65 | 02-15 .. 10-15 | **Partial.** The Host keeps its own command list and import path (`/automations`), but there is no chat `!addcom` for mods. Mods (KareBearr_, LvLMarshmello, Ivan) use this a lot; 195 `!addcom` and 260 `!editcom` in 8 months. |
| `!uptime`, `!followage` | 0 by Nightbot | | Nightbot never answered these. StreamElements answered both (section 3). |
| `!so` / `!shoutout` | Nightbot 0 | | **Covered** (`!shout`, `!so`; our own queue) |

### 2c. Filters, timeouts and moderation

The logs do **not** contain a trace of any Nightbot filter. There are no "[warning]" lines, no Nightbot messages about links, caps, symbols or spam, and the 990 timeout/ban events in the logs read only "`user was timed out for 120s`" with no actor name. Durations seen: 1s (178), 120s (162), 600s (115), 60s (95), 300s (44), 10s (35), 1800s (20). So "Nightbot timed them out" can't be proven or disproven from chat. Nightbot's spam filters, if enabled, are silent. **Only Ivan's Nightbot dashboard (Spam Protection tab) can say what is on.** Our side has no link, caps, symbol or emote-spam filter at all (Twitch's own AutoMod is separate).

---

## 3. Related finding: StreamElements, not PotatBotat, runs the points and games

00's brief named gamble, slots, duels, points and burgie as PotatBotat features. The logs show they belong to **StreamElements** (28,010 lines). Out of scope here, but it decides whether the points economy survives any removal:

| StreamElements feature | Uses | Replies | Our coverage |
|---|---|---|---|
| `!gamble` | 20,885 | 11,659 | **NOT covered** (we have `!points`/pengs only) |
| `!points` | 3,320 | 2,425 | **Covered.** `!points`/`!pengs` from imported SE data |
| `!watchtime` | 1,766 | 1,285 | **Covered.** `!watchtime` |
| `!give` | 927 | 614 | **NOT covered** |
| `!slots` | 826 | 414 | **NOT covered** |
| `!followage` | 738 | 454 | **NOT covered** |
| `!duel` | 531 | 357 | **NOT covered** |
| `!8ball` | 103 | 68 | **Covered** |
| `!leaderboard` | 58 | 45 | **Covered** (site leaderboards) |
| `!uptime` | 13 | 8 | **NOT covered** |

PotatBotat itself held 3,300 to 4,320 StreamElements points in February (Ivan reset it to 0 via `!setpoints`, and it later showed 0 points); it is an ordinary chatter in that economy.

---

## 4. What to build first (ranked)

1. **Turn on / port the timers.** 62% of Nightbot output. Port the 11 timer texts into `timers.json` and enable them (Host module exists). Needs Ivan's wording choices.
2. **Mod `!title` and `!game`.** About 340 Nightbot replies plus PotatBotat's 20 recent ones. Needs a Host step with the Twitch `channel:manage:broadcast` scope. Reverses the earlier "dropped" decision in the Streamer.bot cutover notes, so 00 and Ivan must agree first.
3. **Mod `!addcom` / `!editcom` / `!delcom`** (520 uses). Without them, mods can't add jokes in chat.
4. **Enable the song-request module** when Nightbot stops (`!sr`, `!skip`, `!oops`). Already built; just switch on.
5. **Check Nightbot's spam filters** on its dashboard, and replace any that are on.
6. **Ask Ivan about the 24 non-imported commands** (`!goon` 63, `!cpu` 55, `!of` 38).
7. **PotatBotat:** `#gpt`-style command, 7TV `!add`/`!remove` for mods, and `#fl`/`#rl`/`#ls` log lookups. Optional, lowest usage.

## 5. Safe to drop

- PotatBotat: `#quiz`, `#answer`, `#rank`/potato farm, `#pyramid`, `#8ball` (we have ours), `#ping`, `#always`, `#vanish`, `#ban`, `#timeout`, `#spam`, `#ambassador`. One-day tests or admin noise.
- Nightbot: `!skipsong` and `!volume` (broken), `!time` (broken in Nightbot, ours works), the `WWW!!!!` filler, and its default `!commands` link.

## 6. Limits of this audit (don't over-read it)

- Trigger lines for bot replies that came from a bot's own commands (title/game changes, random clip) aren't in the logs, so those counts are of **replies**, not requests.
- Reply-to-trigger matching is a 6-second window. Where a Nightbot timer fired close to a user command, a reply can be credited wrongly (for example `!gamble` shown as answered by a timer line). The per-command totals above use the matched count; treat small numbers as approximate.
- Timeout events carry no actor, so filter activity can't be attributed to Nightbot (section 2c).
- The 6 August to 20 October window covers 8 months of ~256 stream-day files; PotatBotat's counts are small enough that single users dominate (for example `#add` is 2 users).
- "Covered" means the command exists in `/api/commands-doc` or the Host source. It does not mean the output was tested against Nightbot's exact reply. Sixteen channel-lore commands are exact-command-only, so variables like `$(eval ...)` in `!attack` may not work.
- I did not read `Docs\COMMANDS.md`, `TRIGGERS.md` or `ACTIONS.md` in full; coverage comes from the live command list and the Host source.

---

## 7. StreamElements (added at 00's request), 28,010 bot lines, 2026-02-15 .. 2026-10-20

Counts are bot lines by category (regex on the reply text), so they are replies, not requests. Request totals come from the viewer lines that start with the trigger (the `who.mjs` figures in section 3). StreamElements is the busiest points and games system in the channel. Most of what it does in chat is the **gambling economy**, and our Host economy (commit `9122ce7`) replaces only the balance and watch-time part of it.

### 7a. What it does in chat, with our coverage

| StreamElements feature | Bot lines | First .. last | Requests (viewer lines) | Our coverage today |
|---|---|---|---|---|
| `!gamble` results ("won/lost N points", "went all in") | 11,466 | 02-20 .. 10-20 | 20,885 | **NOT covered.** `HostEconomy.cs` has no wager command. By far the most used SE feature. Also "Just one more !gamble all" (74 lines), a loss-streak line. |
| `!roulette` replies ("in roulette", min-bet errors) | 3,729 | 02-20 .. 10-19 | 9 typed `!roulette`; most are the `!gamble` flavour | **NOT covered.** Same wager engine as `!gamble`. |
| `!slots` / `!slot` ("you got A \| B \| C and lost N") | about 1,900 (74 wins) | 02-15 .. 10-18 | 826 `!slots`, 1,644 `!slot` | **NOT covered.** Min bet errors "minimum bet for !slots is 100" show it is actively used. The 74 wins are against about 1,820 losses. |
| `!points` / rank ("has N points and is rank X/132") | 3,300 | 02-18 .. 10-20 | 3,320 | **Covered.** `!points`, `!pengs` (Host economy). Includes rank of N. |
| `!watchtime` | 1,825 | 02-15 .. 10-20 | 1,766 | **Covered.** `!watchtime`, `!topwatch`. |
| `!top` / top points ("Top 5 points: ...") and "Top N minutes" | 845 + about 120 | 02-18 .. 10-19 | | **Covered.** `!toppoints`, `!topwatch` (lists raised to 500 in 9122ce7). |
| `!givepoints` / `!give` ("X gave N points to Y", usage and "you only have" errors) | 1,825 (includes about 196 error lines) | 02-20 .. 10-19 | 927 | **NOT covered.** No transfer command in `HostEconomy.cs`; only mod `!addpoints` / `!removepoints`. |
| `!duel` ("wants to duel you for N points", `!accept`, `!deny`) | 753 | 02-25 .. **08-22** | 531 | **NOT covered.** Last seen in August, so use has faded; low priority. |
| `!setpoints` (mod override: "set X points to N") | about 655 (558 on the `PinguinoB0t` account, 97 on Ivan's) | 03-29 .. 10-19 | | **Partial.** `!addpoints` / `!removepoints` adjust by an amount; there is no "set to exact value". Used mostly to restore balances; one session reset to 0 after test gambles. |
| `!followage` | 705 | 02-17 .. 10-19 | 738 | **NOT covered.** Needs the Twitch follow API. |
| `!uptime` / "streaming for 7 hours" | about 10 | 02-15 .. 10-03 | 13 | **NOT covered.** Trivial. |
| `!queue` (Duos/doubles queue: "!queue join", "!q open") | 350 (about 210 are "no active queue" or "missing title" errors) | 02-24 .. **07-06** | 136 SE answers (of 1,014 `!queue`) | **Covered.** Our own BVQ queue answers `!queue` (351 replies), and SE's last use was July. |
| `!8ball` | 68 | | 103 | **Covered.** `!8ball` (ChattyPinguino). |
| `!leaderboard`, `!commands` links | 74 + 85 | to 10-19 | 58 | **Covered** (site leaderboards, `/help`). |
| Emote combos ("5x ... combo") | 175 | 02-17 .. 10-20 | automatic | **NOT covered.** SE's chat combo feature; cosmetic. |
| Giveaway (`!ticket`) | 2 lines | 04-23 only | | **NOT covered.** Used once ("Sub Giveaway", 2,500 points per ticket). |
| Moderation-ish replies ("how about you dont do that Keepo", "not a valid username") | about 105 | 03-26 .. 10-17 | | Part of the commands above. |
| SE's own timers (Discord, "I'm Ivan..." blurb, "Try these commands") | 26 + about 30 | **02-15 .. 02-16** (plus Discord line to 10-13) | | **Not needed.** They stopped on 02-16; Nightbot's timers replaced them (section 2a). |
| `!songrequest` / `!sr` | 1 line (02-17: a refusal to disable it) | 02-17 | `!sr` is 674 requests with 638 unanswered | **Covered but not live.** SE's song requests are not running, and the built Spotify module (`HostAuto.cs`, `HostSpotify.cs`, disabled) is the replacement. No bot answers `!sr` today. |

### 7b. Store, redemptions, tips, alerts, events

- **Store and redemptions:** no StreamElements store or redemption lines exist in the chat logs. Redemptions that show up are from **SoundAlerts** (2,631 lines, 02-15 .. 10-20): "redeemed Hydrate for N pinguino points" (636), "Mimimimi" (336), "Crab Rave" (190), "says hi!" (352), "wants everyone to hydrate!" (270). SoundAlerts spends **pinguino points**, which is a separate currency from SE's loyalty points as far as the logs show. It is not part of this removal, but it's a third bot that stays.
- **Tips, subs, cheers, raids:** StreamElements never says anything about them in chat. Our `pinguinob0t` thanks raids and Prime subs (for example "KareBearr_ just subbed with Amazon Prime!" on 02-16, the raid welcome on 02-15). The tip/alert **overlay** (OBS browser source) leaves no chat trace, so whether alerts are still on it can't be seen here. Ivan has to check his StreamElements overlay list and tip page.
- **Chat stats:** only the "Top N minutes" lines (about 120) and the Offline Chat minutes board ("1. nightbot (12,460)"). Covered by `!topwatch` / `!topyappers`.

### 7c. Verdict: StreamElements

**Not safe to remove yet. Remove it last, after the points games are rebuilt or deliberately retired.**

Reasons, ranked by usage:
1. **`!gamble` / roulette** (20,885 requests, about 15,200 replies): the most-used feature in the whole channel, and the main reason people hold points. Our economy earns and shows points but has nowhere to spend them. Build first: `!gamble <n|all>` with the same odds and the same "went all in" announcements.
2. **`!slots`** (about 2,400 requests): same wager engine; second build.
3. **`!give`** (927 requests): small build, and it keeps players from losing the transfer between friends.
4. **`!setpoints`** (mod override, 655 uses): add a "set to N" option beside `!addpoints`.
5. **`!followage`** (738) and **`!uptime`** (13): small; they need Twitch Helix calls.
6. Skip or defer: `!duel` (dead since August), giveaways (once), emote combos (cosmetic), SE timers (replaced), SE queue (replaced by BVQ).
7. **Not visible in chat:** alert overlay, tip page and any SE store items. Ivan checks these in the StreamElements dashboard before cancelling.

Points balances are safe to move: `9122ce7` imports them from the SE API with a dry run, a confirm and a backup, and keeps the imported baseline apart from newly earned points. Do the import once more right before the cutover so balances don't drift.

### 7d. Roll-up across the three bots

| | Bot lines | Safe to remove now? | Build first (ranked) |
|---|---|---|---|
| PotatBotat | 977 | Close; losing 7TV add/remove and `#gpt` is the cost | mod 7TV add/remove, `#gpt`, `#fl`/`#rl`/`#ls` |
| Nightbot | 31,720 | No | timers, mod `!title`/`!game`, mod `!addcom`, song module, filter check |
| StreamElements | 28,010 | No (last) | `!gamble`/roulette, `!slots`, `!give`, `!setpoints`, `!followage`, then check the overlay |

Limits for this section: the category regexes are heuristic, so a few lines may be sorted into a neighbouring row (the "other" bucket held 2,884 lines before the breakdown above); request totals count every viewer line starting with the trigger, including ones the bot did not answer. SE's overlay, tips and store are not logged anywhere in chat, so those are marked "check in the dashboard" rather than assessed.
