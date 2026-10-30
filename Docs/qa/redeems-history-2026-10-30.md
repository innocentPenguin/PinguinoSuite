# Channel-point redemption history (T14, worker 14, 2026-10-30)

Read-only rebuild. No live data written, no state-changing Host call (only `GET /api/rewards` was read), no secrets printed. All times UTC (stream starts about 22:00 UTC = 5 PM Central), months are UTC months, so a late-evening US stream spills into the next UTC day.

## Answer: how many times was the pushup redeem used?

| | count |
|---|---:|
| SoundAlerts "says DO PUSHUPS!!!" lines in the chat logs, 2026-02-16 to 2026-10-30 (deduped, all sources) | **168** |
| minus 7 lines typed by the broadcaster account (`innocentpenguin_`, all sound-test sessions, see below) | **161 viewer redemptions on record** |
| estimate for 2026-02-04 to 2026-02-15 (chat logs start 02-15 03:53; Streamer.bot only shows SoundAlerts posted 134 lines in that window, pushups are about 8% of SoundAlerts lines) | about 10 (range 5 to 16), NOT in the 161 |
| 2025-12-10 to 2026-02-03 (the reward already existed) | no per-event record anywhere, unknown |

So: **161 verified, about 170 to 175 likely since 2026-02-04, plus an unknown number in Dec 2025 and Jan 2026.** The 161 is counted across all three Pushups-family rewards (every title), because every one of them plays the same SoundAlerts sound and prints the same chat line.

Validation that one line = one redemption: Host's own redemption feed (`Data/runtime/runtime/site_activity.json`, EventSub) overlaps the chat logs for 2026-10-28 00:10 to 10-30 01:50. In that window the feed has 9 "Pushups" redemptions and the chat has 9 "DO PUSHUPS" lines, same users, 2 to 8 seconds apart. Same check for Hydrate 7/7, Hello There 1/1, Posture Check 3/3, Crab Rave 2/2, yippeeee 4/4. A viewer's own count on 2026-04-08 06:37 ("3 push ups") also matches the 3 lines that day.

Pushups per month (viewer lines only): 2026-02 14, 03 25, 04 38, 05 25, 06 14, 07 10, 08 8, 09 1, 10 26. Top redeemers: karebearr_ 24, lvlmarshmello 19, timothyokongo 9, devv0ps 9, zylorocketleague 6 (63 different people).

The 7 broadcaster lines are tests, not viewer spend: 2026-02-25 21:24:55, 2026-03-17 08:31:53/08:32:00/08:32:07/08:32:15 (a sound-setup session, same minutes as 20 other broadcaster test plays of Mimimimi/Hydrate/Crab Rave/cat), 2026-07-29 11:27:44 and 11:28:18 (the day SoundAlerts changed its chat templates). Add them back if Ivan wants every play counted (168).

## Sources searched (what has redeem records)

| source | has redemptions? | used |
|---|---|---|
| `Data/chat_logs/2026/MM/*.txt` (public log sites, 258 day files, 2026-02-15 to 10-30) | YES: the SoundAlerts bot (`soundalerts`) posts one chat line per redeemed sound reward. 2,730 lines | **main source** |
| `Data/chat_logs/live/*.jsonl` (Host recording, 10-18 to 10-30) and `Data/runtime/chat_logs/` (same files) | same SoundAlerts lines, 99 of them | cross-check only: every line is also in the public logs |
| `Data/chat_logs/_original-downloads/10-11..10-17.txt` | 68 SoundAlerts lines | cross-check only: all also in the public logs |
| `Data/chat_logs/sidecar/streamerbot_daily_counts.json` | NO redemptions: counts of chat messages per user per day. Its `soundalerts` row (2,672 lines, 02-04 to 10-19) is the independent completeness check | check |
| `Archive/streamerbot-2026-10-19/logs.zip` (Streamer.bot logs, 294 day files, 2025-12-08 to 2026-10-19) | Only rewards bound to a Streamer.bot action: `Queueing '<action>' (..., TwitchRewardRedemption) ... initiated by <user>`. 407 events, 4 actions | used for Suggestion, Max Volume, Crossbar, Timeout |
| `Archive/streamerbot-2026-10-19/backups-zips/*.zip` (238 backups, 2025-12-08 on) + `raw-data/twitch_rewards.json` | NO events, but every reward **id with title and cost over time** | used for all grouping/rename evidence |
| Host `GET /api/rewards` | current Twitch rewards (40): id, title, cost, enabled, owned. No counts. | read once |
| `Data/runtime/runtime/site_activity.json` | last 100 site events, 78 redemptions (2026-10-28 00:10 to 10-30 01:48) with titles | cross-check, Host-era |
| `Data/runtime/runtime/site_activity_sent.json` | 400 most recent event ids (337 redemption ids), no titles, rolling | not usable for totals |
| `Data/runtime/console/host.jsonl(.1)` (10-19 to 10-30) | `ran 'Spotify: channel point song request' (redeem...)` 143, `skip song` 25, `song request redeem left to Songify` 81 | Song Request / Skip Song, Host era |
| `Data/runtime/console/voice.jsonl` | 509 `redeem by <user>: master_off`, no reward title, 10-19 to 10-29 | not usable (cannot tell which reward) |
| `Data/runtime/automations.json`, `alert_bridge_state.json`, `automation_vars.json`, `Data/economy/*`, `Data/history/*` | no counters, no history of redemptions | nothing to take |
| Twitch itself (Helix `custom_rewards/redemptions`) | only returns the queue of rewards created by the same app id, and every reward here is `owned:false`, so the Host cannot read it | not available |

**There is no redeem counter anywhere in the Host today** (checked `/api/rewards`, `HostRewards.cs`, `HostRedeem.cs`, `HostSiteActivity.cs`, automations, profiles). Section "Seeding" below proposes one.

## Method and double-count risk

1. Parsed every `soundalerts` line from the public text logs (exact duplicate lines inside a file: 0). That is 2,730 lines.
2. Parsed the live jsonl and the `_original-downloads` files the same way, converted live timestamps to UTC, and merged any line with the same text within 5 seconds. Result: all 99 live lines and all 68 original-download lines are already in the public logs, so they add nothing. 2,730 events remain.
3. Classified each line into a reward group by its text template (all 2,730 classified, 0 left over).
4. Counted per UTC month. Lines typed by the broadcaster account are listed separately in each table ("raw" vs "viewer").
5. Checked completeness against the Streamer.bot per-day SoundAlerts counts for 2026-02-15 to 10-19: 2,565 (Streamer.bot) vs 2,617 (public logs). 17 days differ. Days where the public log has FEWER lines than Streamer.bot, so lines may be missing: 02-15 (+12), 07-19 (+3), 07-30 (+2), 08-25 (+10), 08-30 (+1), 09-08 (+2) = at most 30 missing lines across all groups, which is 1 to 3 pushups at the pushup share. Days with 0 on the Streamer.bot side (02-18, 02-19) are days the Streamer.bot log is missing, not the public log.

Double-count risks, all closed or named:
- same event in public log + live + original: closed (merged, shown above).
- SoundAlerts changed templates on 2026-07-29 ~11:00 (`redeemed "Hydrate" for N pinguino points` became `wants everyone to hydrate!`, `redeemed "Crab Rave"` became `is crab ravin'`, and so on). The old and new template for one reward are never both posted for one redemption (checked: the old form ends 2026-07-29 11:23, the new one starts 11:26), so I count both forms as one group without double counting. The pushup template never changed.
- Host feed (10-28 onward) vs chat lines: they are the same redemptions. Never add the Host feed on top of these totals for the same period (see Seeding cut-off).
- `refunded` notices (TTS 51, video 28) are shown as refunds and are NOT counted as redemptions, but the matching redemption line may or may not exist, so Video Share / TTS totals can include a few that were refunded.

## Reward groups (grouping evidence first, then one table per group)

Grouping rule: same Twitch reward id first (Streamer.bot snapshots give id, title and cost back to 2025-12-10); different ids only when the same purpose is shown by the SoundAlerts text AND the old id disappears when the new one appears. Stamps below are the date of the first Streamer.bot backup that showed that title/cost, so a change happened on or shortly before it.

### GROUP 1. PUSHUPS (the answer above)

| field | value |
|---|---|
| canonical title | **Pushups** (Helix id `09c78a1c-767e-4f07-a4ae-2f4a4935fc10`, enabled, 1350 points on `/api/rewards` today) |
| all titles / ids seen | `b618f97f` "Pushups" 250 (12-10), 350 (12-24), 550 (12-30), last seen in the 2025-12-30 backup, gone by 2026-01-12. `5567e401` "Do Pushups Now!" 550, SoundAlerts template, first seen 2026-01-12, still in the Streamer.bot list on 10-19, NOT in the Host's current Twitch list. `09c78a1c` "Pushups" 550 (01-19), 200 (02-05), 175 (02-08), 215 (02-20), 700 (03-15), 900 (06-03), 1350 (06-21). SoundAlerts chat text is always "X says DO PUSHUPS!!!". Chat nicknames: "push ups", "push-ups", "10 pushups", "pushup redeem" (viewer wording, not Twitch titles). |
| grouping evidence | Same title "Pushups" re-created: `b618f97f` disappears between 12-30 and 01-12, `09c78a1c` appears 01-19, `5567e401` is the SoundAlerts "Do Pushups Now!" template created 01-12 alongside the other SoundAlerts templates. One SoundAlerts sound/message ("DO PUSHUPS!!!") from the first log day to the last, so one purpose. NOT included: "Pullups" (`0323a52e`, different reward and cost 1500, no SoundAlerts line). |
| total redemptions on record | **161** (168 raw incl. 7 broadcaster test plays) |
| per month | 2026-02 14, 03 25, 04 38, 05 25, 06 14, 07 10, 08 8, 09 1, 10 26 |
| first / last | 2026-02-16 04:02:09 (AustinMcNeill1234) / 2026-10-30 00:35:52 (deluxeoctopus5) |
| source coverage gaps | No per-event record 2025-12-10 to 2026-02-03 (Streamer.bot logs have no chat lines before 02-04, public logs start 02-15). 2026-02-04 to 02-15 03:53: SoundAlerts posted 134 lines (Streamer.bot count) but their text was never saved, estimate about 10 pushups. Up to ~2 lines possibly missing from the public logs on 07-19/07-30/08-25/08-30/09-08 (see method). Redemptions made while SoundAlerts was paused would leave no line (one "currently paused" notice, 2026-03-03). |
| double-count risk | none after dedupe. Adding the Host feed on top would double count 2026-10-28 to 10-30. |

### GROUP 2. Hydrate

| field | value |
|---|---|
| canonical title | Hydrate (`4ef5ade3-983a-48de-a9e3-c1bd3f6a28bc`, 325 today) |
| titles / ids | `7d9b5951` "Hydrate!" 150, 100, 75 (12-10 to 12-30, gone by 2026-01-12); `4627369b` "Hydrate" 75 (SoundAlerts template, 01-12); `4ef5ade3` "Hydrate" 75 (01-19), 50 (02-08), 175 (02-20), 325 (03-24), 350 (06-03). Chat text: `redeemed "Hydrate" for N pinguino points` (N = 50, 175, 325, 350, matching the price history) until 2026-07-29 11:23, then `wants everyone to hydrate!`. |
| total | **924** viewer (938 raw, 14 broadcaster) |
| per month | 02 107, 03 150, 04 75, 05 129, 06 95, 07 89, 08 70, 09 107, 10 102 |
| first / last | 2026-02-15 / 2026-10-30 |
| gaps | none before 02-15 recorded (Dec-Jan "Hydrate!" redemptions unknown); same 02-04..02-15 and missing-line caveats as Pushups. |

### GROUP 3. Mimimimi

| field | value |
|---|---|
| canonical title | Mimimimi (`9f5b9098-b047-49ff-9f1a-8bf992aba4e8`, 255) |
| titles / ids | `306cb8f8` "Mimimimi - Sound" 100 (template 01-12); `9f5b9098` "Mimimimi" 100 (01-19), 150 (02-04), 175 (02-05), 125 (02-28), 250 (06-03), 255 (07-30). Chat: `redeemed "Mimimimi" for 125/150/250 pinguino points`, then plain `redeemed "Mimimimi"` after 07-29. |
| total | **391** viewer (411 raw, 20 broadcaster) |
| per month | 02 39, 03 91, 04 86, 05 54, 06 22, 07 30, 08 37, 09 23, 10 9 |
| first / last | 2026-02-16 / 2026-10-16 (no line since 10-16 although the reward is still enabled) |
| gaps | same as Hydrate |

### GROUP 4. Hello There (SoundAlerts "says hi!")

| field | value |
|---|---|
| canonical title | Hello There (`fc9d5c74-...`, Host list shows "Hello There " with a trailing space) |
| titles / ids | `fc9d5c74` "Hello There" 100 (01-19), 75 (02-08), 215 (03-15), 150 (03-18), 175 (07-30). Eleven SoundAlerts templates of 2026-01-12 ("Hello There - Sound Alert" x8, "Hello There - Sound", "Hello SoundAlert" x2, 55) are unused duplicates, not counted. Chat text "X says hi!" (never changed). |
| total | **350** viewer (358 raw, 8 broadcaster) |
| per month | 02 12, 03 29, 04 51, 05 72, 06 49, 07 43, 08 37, 09 29, 10 28 |
| first / last | 2026-02-17 / 2026-10-30 |
| gaps | same as Hydrate. Mapping of the text "says hi!" to this reward is by title only (no id on the line). |

### GROUP 5. Crab Rave

| field | value |
|---|---|
| canonical title | Crab Rave (`51774805-...`, 625) |
| titles / ids | `0b6a9b59` "Crab Rave - Sound" 475 (template 01-12); `51774805` "Crab Rave" 475 (01-19), 625 (02-05). Chat: `redeemed "Crab Rave" for 625 pinguino points`, then `is crab ravin'` / `crab ravin'` after 07-29. |
| total | **285** viewer (294 raw, 9 broadcaster) |
| per month | 03 46, 04 98, 05 38, 07 9, 08 33, 09 19, 10 42 (none counted in June) |
| first / last | 2026-03-16 / 2026-10-29 |
| gaps | no line before 2026-03-16 although the reward existed from January (unused or not announced, unknown); none in June. |

### GROUP 6. Posture (Posture Fix! -> Posture Check)

| field | value |
|---|---|
| canonical title | Posture Check (`7843108f-...`, 75) |
| titles / ids | `bcfdab37` "Posture Fix!" 100 (12-10), 50 (12-29), 25 (02-08), 75 (03-15), last seen in the 2026-07-27 backup; `7843108f` "Posture Check" 75 first seen 2026-07-30. Chat: `redeemed "Posture Check"` (4 lines 07-29), then `wants you to check your posture` / `posture check`. |
| grouping evidence | same purpose, same cost 75, old id vanishes the week the new one appears. |
| total | **168** viewer (174 raw, 6 broadcaster) since 2026-07-29 |
| per month | 07 13, 08 58, 09 51, 10 46 |
| gaps | **Posture Fix! redemptions before 2026-07-29 have no record** (no SoundAlerts line existed for that reward). |

### GROUP 7. Lizard

| field | value |
|---|---|
| canonical title | Lizard (`f4aed617-...`, 400, currently disabled) |
| titles / ids | `f4aed617` "Lizard" 400, first seen 2026-07-30. Chat text `LIZARD` (and one `redeemed "Lizard"`). |
| total | **135** viewer (136 raw) |
| per month | 07 16, 08 68, 09 41, 10 10 |
| first / last | 2026-07-29 / 2026-10-17 |

### GROUP 8. yippeeee

| field | value |
|---|---|
| canonical title | yippeeee (`14d7d1dc-...`, 200) |
| titles / ids | `14d7d1dc` "yippeeee" 200 first seen 2026-10-18 |
| total | **44**, all in 2026-10 (10-18 to 10-29) |
| gaps | Host feed overlap 4/4 on 10-28..10-30 |

### GROUP 9. Video Share (Video Share / Long Video Share / Short Video Share)

| field | value |
|---|---|
| canonical title | Short Video Share (last name; no longer on the current Twitch list) |
| titles / ids | `0d3c25b6` "Video Share" 1250 (01-19), 800 (02-05), 500 (02-08) -> "Long Video Share" 500 (02-16) -> "Short Video Share" 500 (04-28 backup), last seen in the 2026-07-27 backup. Five "Video Share" templates of 01-12 (1200/1250) are unused duplicates. |
| chat | `redeemed "Long Video Share" for 500 pinguino points` 28 lines (2026-03-02 to 05-09) and `redeemed "Short Video Share"` 21 lines (05-17 to 07-24). The chat label lags the Twitch title (the SoundAlerts name was not renamed with it), so I treat Long and Short as ONE reward renamed, not two. |
| total | **49** redeemed lines (28 Long + 21 Short), plus 28 "requested video could not be sent, points refunded" notices that are NOT redemptions |
| per month | 03 15, 04 12, 05 3, 06 9, 07 10 |
| gaps | none before 2026-03-02; refunds make the true figure up to 28 lower if every refund matches a counted line |

### GROUP 10. Text-to-Speech

| field | value |
|---|---|
| canonical title | Text-to-Speech (`c4683ea4-...`, 500, currently disabled; eleven more TTS templates of 2025-12-11 are unused) |
| titles / ids | `c4683ea4` 1000 (12-11), 800, 600, 225, 150, 99, 375 (03-15), 550 (05-16), 500 (07-30) |
| total | **36** `redeemed "Text-to-Speech" "<message>"` lines, all 2026-07-14 to 07-24, plus 51 "Channel Points have been refunded (TTS spam/duration/error)" notices from 02-23 on, which are NOT counted |
| gaps | **TTS redemptions before 2026-07-14 have no record** except those 51 refund notices (the bot only started printing the message text on 07-14). The Host voice log has 509 `redeem by` lines but no reward title, so not usable. |

### GROUP 11. "cat" (sound with no reward match)

32 plain lines `cat` by `soundalerts`, 2026-03-16 23:19 to 04-26 01:08 (Mar 15, Apr 17). The chat text carries no user and I found no reward named cat/meow in any Streamer.bot snapshot, so the owner reward is unknown. Not mapped.

### GROUP 12. Eat!

4 lines on 2026-07-29 11:41 to 11:44 (all broadcaster, template test). Reward `c419fc49` "Eat!" 375, first seen 2026-07-30, disabled. 0 viewer redemptions on record.

### GROUPS 13 to 16. Rewards bound to a Streamer.bot action (from the Streamer.bot logs)

| group | reward id and titles | events in logs | per month | first / last | gap |
|---|---|---:|---|---|---|
| Suggestion | `65467951` "Suggestion" 5 points (action "Suggestion Box") | 357 | 02 33, 03 78, 04 118, 05 125, 06 3 | 2026-02-07 / 2026-06-01 | none known; later use went elsewhere |
| Max Volume | `47d16fc5` "Max Volume (10 Seconds)" -> "Max Volume" 300 (action "Vol"); reward gone | 39 | 02 32, 03 7 | 2026-02-04 / 2026-03-09 | before 02-04 |
| Add Crossbar Sound | `96c5e96f` 3500 -> 650 (action "Crossbar"); reward gone | 5 | 03 5 | 2026-03-09 / 03-12 | none |
| Timeout Someone | `2d1e8090` "Timeout Someone" 1500, 3000, 800, 1000, 1600 (action "Timeout 60 sec") | 6 (+3 seen by Host 10-28..10-30) | 04 5, 07 1 | 2026-04-03 / 2026-07-29, then Host era | the 6 are only the Streamer.bot-bound runs; later redemptions are not counted anywhere |

The action-to-reward link comes from the actions.json inside the Streamer.bot backups (action id to reward id). The other bound action, "End Stream" (`ec3709f1` Instantly End Stream, 2,500,000 points), never fired in the logs: 0.

### GROUP 17. Song Request and Skip Song (Host era only)

| reward | evidence |
|---|---|
| Song Request (`e086b229`, 25 points; history 25, 1, 750, 25) | Host console 2026-10-23 to 10-30: 143 `ran 'Spotify: channel point song request'` + 81 `left to Songify` (10-27, 10-28) = 224. Last 100 site events (10-28 00:10 to 10-30 01:48) hold 46 Song Request redemptions. Before 10-23 no machine record. |
| Skip Song (`ba75b1c3`, history 175 to 1000, "Skip Song Poll" in August, back to 75 on 10-12) | Host console: 25 runs 10-24 to 10-28. |

### GROUP 18. No machine record at all

These rewards are handled by hand or by Streamer.bot without logging, and they leave nothing countable: **1v1** (`784e9e67`; titles "1v1 Clash", "1v1 Any other game", "1v1 Any game", "1v1"), Pullups (`0323a52e`), Barbell Overhead Press (`f9aee545`), Lose the glasses (`40abb2e1`), Shot (`1bbfb248`), Double Shot (`f6f4e2fe`), Own Goal, KBM, Rename Steam, Pick My Car (`2c88ff9e`, earlier "Create a Preset"/"Make a Preset"), Randomize Preset, Pick Light's Color (`c19574d6`, earlier "Change Background Lights"/"Change Light Color"), Stretch, Snowball (`0b2f60cd`), Show the Stream, Shirt Toggle, Get a sub, Extend Stream, Instantly End Stream, VIP, Twitch Mod, Add a Command, Time Yourself Out, Play a game. The only traces are viewers' chat remarks ("I redeemed 19 1v1's before", "1 Pull-up, 1 barbell overhead press, 3 push ups, and 1 hydrate redeemed") and pasted notices ("fardio690 redeemed Barbell Overhead Press750"), which are not countable. The Host feed has 2 "1v1" and 3 "Timeout Someone" for 10-28..10-30. Twitch's own queue is the only full record, and it is not readable by the Host (see sources).

## Coverage gaps in one place

- 2025-12-08 to 2026-02-03: Streamer.bot logs exist (22 day files missing) but contain no chat lines; no SoundAlerts text anywhere. Everything redeemed then (Pushups, Hydrate!, Posture Fix!, TTS, 1v1 and so on) is unrecorded.
- 2026-02-04 to 02-15 03:53: SoundAlerts line counts known (134), text not.
- 2026-02-15 to 10-30: public logs complete for every day (258 of 258) with up to 30 lines possibly missing.
- Rewards not announced by SoundAlerts: see Group 18.
- SoundAlerts paused or offline: leaves no line.

## Seeding the Host's redeem counters (proposal only, nothing written)

What exists: nothing. `/api/rewards` returns Twitch's list (id, title, cost, enabled, owned); the site feed keeps 100 rows and 400 ids; automations have no run counts. So "seeding" means adding a small counter store. Suggested design for 15 (Host):

1. **Group map** `Data/runtime/redeem_groups.json`: group key to reward ids and title aliases, so renames fold (for Pushups: ids `b618f97f`, `5567e401`, `09c78a1c`, aliases "Pushups", "Do Pushups Now!"; for Video Share: `0d3c25b6` with Video/Long/Short; Hydrate: `7d9b5951`, `4ef5ade3`, "Hydrate!", and so on). Match on reward id first, normalised title second (trim, case, trailing space).
2. **Counter store** `Data/runtime/redeem_counts.json`: per group `{title, baseline, baselineThrough, perMonth, live, lastRedeemAt}`. Total shown = baseline + live. `live` increments in the same place HostSiteActivity handles `TwitchRedeem` (one increment per redemption id, reuse the id that `site_activity_sent.json` already dedupes on). A read-only `GET /api/redeems` (and a `{redeem.pushups}` style variable for chat commands, using the existing persistent `set_var`) would expose it.
3. **Seed values** (viewer lines, through the cut-off): Pushups 161, Hydrate 924, Mimimimi 391, Hello There 350, Crab Rave 285, Posture Check 168, Lizard 135, yippeeee 44, Video Share 49, Text-to-Speech 36, Suggestion 357, Max Volume 39, Add Crossbar Sound 5, Timeout Someone 6. Per-month splits are in the tables above. Keep a separate optional `estimate` field for Pushups (about 10, Feb 4 to 15) and never fold it into `baseline`.
4. **Cut-off to avoid double counting**: pick C = a quiet moment with the stream offline (right now the newest SoundAlerts line is 2026-10-30 00:56:54 and the newest Host redemption 01:48:44). Re-run the extraction scripts at go time so the baseline includes everything up to C, then make the Host count only redemptions with `at` greater than C. The Host feed since 10-28 is already inside the baseline through the chat lines.
5. **Backup and apply**: dry-run first (print baseline per group), then write `redeem_counts.json` after copying any existing file to `redeem_counts.json.before-seed-YYYYMMDD-HHMMSS.bak` (same naming as the existing `automations.json.before-*.bak` files). The Host file edit and restart stay with 00/15.
6. Scripts to rebuild the baseline are in the shared notes folder: `14-redeems-1-extract.py`, `14-redeems-2-classify.py`, `14-redeems-3-streamerbot-bound.py` (read-only, stdlib only).

Waiting for go (via 100) before anything is written.

## Not verified

- The reward id behind each SoundAlerts chat line (the line has only the sound text), so the line-to-reward mapping is by title and purpose, confirmed 1:1 only for 2026-10-28 to 10-30 against the Host feed.
- Whether `5567e401` "Do Pushups Now!" was ever redeemed or is only a template, and which of the three Pushups ids fired in Dec 2025 and Jan 2026.
- The 10 pushups estimate for Feb 4 to 15 (a ratio, not a count).
- The "cat" owner reward, and why Mimimimi shows no line after 10-16.
- Exact rename dates (backup stamps are the first backup that shows the change).
- Whether the 7 broadcaster lines cost channel points (the broadcaster can redeem their own rewards).
