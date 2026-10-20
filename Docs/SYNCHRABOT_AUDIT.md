# SynchraBot audit (read-only)

Prepared by Runner 2 for 00, 2026-10-20. Sources: chat logs `Data\chat_logs\2026\*` (2026-02-15..2026-10-20, ~670k lines), `Data\runtime\chat_profiles.json`, `Docs\*`, `Data\lore\proposals_for_bots.md`. No builds, no pushes, no secrets. Trigger-to-reply attribution is heuristic (a bot reply within ~6s of a viewer trigger), so small counts near timers are noisy.

## 1. Who/what it is

- Account `synchrabot` (display "SynchraBot"). It is the chat bot of Synchra (dash.synchra.net, a multi-chat/stream tool). One line on 2026-07-09 07:57 says "Watch with multi-chat: https://dash.synchra.net/watch/twitch/innocentpenguin_".
- **It holds the mod badge** (`chat_profiles.json`: `"synchrabot": {msgs 5200, activeDays 99, mod: true, bot: true}`), first message 2026-07-09, last 2026-10-20 02:06. Mod rights are what let it run timers and a queue.
- Earlier presence: it was a chatter before it ever spoke. It was on StreamElements leaderboards by 04-21 (3,220 points) and 05-04 (13,725 watch minutes), and viewers asked "what tf is synchrabot" on 03-30. Probably it sat in chat as a lurker from about March, then became active on 07-09 once someone turned its features on.
- **Who runs it is NOT proven by the logs.** Viewer reactions: "@SynchraBot stop trying to be me" (07-10), "yh get rid of this" (07-11). Ivan on 07-21: "you arent supposed to be here @SynchraBot" and "@SynchraBot leave". The same Ivan did not remove it, and its config clearly carries Ivan's own text (Discord, socials, "Daily Streams @ 5pm CDT", "my name is Ivan"), so someone with dashboard access configured it. Ivan has to say who.
- Total: 5,286 lines by the bot (5,368 mentions). By month: Jul 1,256, Aug 2,119, Sep 1,161, Oct 748 (declining).

## 2. Behaviour catalogue

### 2a. Queue (~3,100 lines, about 60 percent of all its output)
Triggers (viewer to bot, answered): `!join` 2,152, `!pos` 438, `!leave` 215, `!position` 4. Period 07-09..10-15; join median gap 5.2 min. 185 distinct users.

Reply formats (with the bot's own typos):
- "@U You joined the queue!" 1,077 (80 days)
- "@U You joined the queue as postion #N" 471+
- "@U You are already in the queue at position N" 595+
- "@U You are #N" 404 / "@U You are in position N" 18
- "@U You left the queue!" 126 / "@U You have left the queue" 36
- "@U You are not in the queue" ~76 / "@U Position already taken" 5 / "@U You have joined the queue as number: N" 2

Top users in replies: yoohoo15 218, Phil_Flock 158, cups0ftea 157, blizzyfvv 102, pineyapplie 100, ash_wagawaga 99, penguinslittlebro 89, timothyokongo 83, Unninocence 75, gonkilluagg 68.

Several reply wordings exist, so more than one queue config or version was in use.

### 2b. Timers (about one message per 50 min each; they run during streams)
| Text | Lines | First..last |
|---|---|---|
| "Don't forget to follow so you get notified when I go live!" | 445 | 07-10..10-20 |
| "Daily Streams @ 5pm CDT" | 442 | 07-10..10-20 |
| "Join the community Discord! ... → !discord" | 439 | 07-10..10-20 |
| "All my !socials: linktr.ee/InnocentPenguin" | 424 | 07-10..10-19 |
| "Say !rank for my rank!" | 380 | 07-31..10-20 |
| "Join the discord to socialize, share epic clips ..." | 110 | 07-10..10-15 (18 min gap) |
| "Hello! my name is Ivan. I am a daily streamer, College Rocket League player, and weightlifter!" | 12 | 07-10..07-11 |
| "Check out the website for more information: innocentpenguin.com" | 24 | 10-15..10-19 |

The first five Nightbot timers (follow, discord, socials, daily-stream, about) stopped on 07-10, the day synchrabot's identical timers began. **Synchrabot took over those Nightbot timers.** That corrects BOT_REMOVAL_AUDIT section 2a.

### 2c. Canned answers
- `!discord` ~108 lines "Join the discord..." (99 answered by synchrabot).
- `!epic` answer "InnocentPenguin" ~104 (51 by synchrabot vs 245 by Nightbot; per the month table in my run, from 07 to 10 Synchra answers `!epic` alone almost every time: Oct 8 of 8). Nightbot stopped answering `!epic` after Aug.
- `!socials` 17, `!brian` 12 (the trigger has 1,153 uses overall, but most are unanswered, probably an in-joke), `!tip` 4 (StreamElements tip link), `!website` 4.
- Minor/noisy (likely timer collisions): `!gamble` 34, `!points` 12, `!song` 9, `!burgie` 9, `!top` 6, `!followage` 6, `!give` 5, `!slot` 5, `!lurk` 3, `!vanish` 3, `!accept` 3. Two "Bet is too low, minimum is N" lines on 07-21 show a gamble-type command existed at least once.

### 2d. Moderation
No moderation actions by synchrabot in any log (no bans/timeouts/deletes attributable to it). The account itself was timed out 4 times (07-24 22:36 10s and 22:46 30s, 07-27 22:25 10s, 07-29 00:05 10s) by an unknown actor.

## 3. Other integrations it touches
- Synchra multi-chat watch page (one link, 07-09).
- StreamElements tip link (`!tip`).
- Discord invite (`!discord`), the same one Nightbot used.
- `!ip` is NOT Synchra. 195 of 269 `!ip` uses were answered by Nightbot ("smp.innocentpinguino.com port:19132"), and none by synchrabot, so 02's earlier note ("Nightbot/synchrabot already answer !ip") was half right: only Nightbot.
- `!rank` timer promotes the `!rank` command, which Nightbot answers ("Peak GC2, Current C3"; 13 of 223 uses answered). `rocketrankbot` also exists: it joined on 03-02 06:13 and Ivan added a rank command with it, so there are three parties around `!rank`.
- Rocket League: no direct tie from synchrabot beyond the intro text.

## 4. Overlap with our bots
| Synchra function | Our module | Status |
|---|---|---|
| Queue `!join/!pos/!leave` | PinguinoB0t BVQ (!join 1,530, !leave 292, !pos 8; replies "You're #1 of 2 in the queue") | **Duplicate**. In Jul-Sep both answer the same `!join`; per the table in my run roughly 36+41+11 pinguinob0t+synchrabot double answers. In Oct B0t answered 372 `!join` to synchrabot's 130, so viewers are migrating. |
| Timers (follow, daily, discord, socials, rank, website) | `HostTimers.cs` (`timers.json`, 3 generic timers disabled) | Not built. This is the main gap. |
| `!discord`, `!socials`, `!epic`, `!website` | ChannelLore/Helper `!discord` | Helper answers `!discord` too, so it **doubles** with Synchra and Nightbot. |
| `!tip` | StreamElements tip page | Host has no tips handling. |
| `!rank` | none (Nightbot text, rocketrankbot) | Unowned. |
| Gamble/points | Host economy 9122ce7 has `!points !pengs !watchtime !toppoints !topwatch`, no gamble | Synchra gamble was minor/short-lived. |

## 5. What replacing each function takes
1. **Queue**: B0t BVQ already does it. Needs only that Ivan stops the Synchra queue (dashboard) so one bot answers. Check B0t covers `!position`, "already in queue at N", and the join-queue-while-closed case. Low risk.
2. **Timers**: add 6 entries to Host `timers.json` (follow, daily 5pm CDT, discord, socials, rank, website), roughly 50 min apart and only while live. Small build, medium effort. Open point: the rule (every N minutes vs minimum chat lines) is not visible in logs; the 18 vs 50 min gaps suggest a lines-based rule.
3. **Canned answers**: put `!epic`, `!socials`, `!website`, `!brian` into the Helper/ChannelLore command set. `!brian`'s intended reply is unknown (most uses get no reply).
4. **`!rank`**: decide a single owner (our command, or keep rocketrankbot).
5. **Presence/mod badge**: it is a mod. Removing it also removes any sync of Synchra chat widgets (SynchraChat is listed as an independent widget in `Docs\STREAMERBOT_PARITY.md`).

## 6. Risks and unknowns only Ivan can answer
- Who owns/administers the Synchra account and who invited it as mod? (Ivan said it isn't supposed to be there on 07-21.)
- Dashboard settings: exact timer intervals/line thresholds, queue config, what other commands/automations are on, any alerts/overlays/widgets that depend on it (SynchraChat).
- Does Ivan pay for or depend on any Synchra subscription?
- Is `!brian` meant to answer something?
- If removed without replacements, timers (follow/discord/schedule) go silent, as they did when Nightbot's stopped on 07-10.
- Removing the bot and Nightbot's timers at the same time would leave the channel with no promotion messages.

## 7. Staged removal plan
1. Ivan confirms ownership and exports/screenshots the Synchra dashboard settings (timers, queue, commands).
2. Pick one queue bot: leave B0t BVQ on, turn the Synchra queue off. Watch 2-3 streams for duplicate answers.
3. Build and enable the 6 timers in Host `HostTimers.cs` with the same wording; run alongside Synchra for one stream, then disable Synchra's timers.
4. Move `!epic/!socials/!website/!brian` and any `!rank` decision into Helper/ChannelLore; retire the Synchra and Nightbot duplicates (and the duplicate `!discord`).
5. Remove the mod badge, then part/disconnect the account last. Re-check the logs for 3+ days for lost behaviour (timers, queue replies).
