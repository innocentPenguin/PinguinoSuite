# Closing Streamer.bot: what it does today and what replaces it

Source: read-only look at `Documents\PinguinoB0t\data` (`actions.json` 44 actions, `commands.json` 36 commands, `twitch_rewards.json`, `settings.json` timers, `globals.db` name only). Nothing in Streamer.bot was changed. Written by 02 (PinguinoBots/Host), 2026-10-19.

**Status words**
- **REPLACED**: something already in the Suite does it (names who).
- **CAN-IMPORT**: Host *Actions & Events > Import from Streamer.bot* converts it (arrives disabled; review).
- **NEEDS-BUILD**: not covered yet; says what is missing and who owns it.
- **DROP**: dead, disabled or a placeholder; safe to lose.

**Verdict: not safe to close yet.** The game commands, chat AI, helper, welcome and routing are replaced. About ten small things are still only in Streamer.bot (stream title/game + the day counter, clips, ad countdown, ban alert, raid-out, shoutout, suggestion box, "First 5" game, the chat pop sounds, the thank-you alerts) and YouTube/Kick chat reading belongs to Multi. See the checklist at the end.

---

## 1. Game and chat commands

| Streamer.bot item | What it does | Triggers | Status |
|---|---|---|---|
| **BVQ Engine** (C#, 195 KB) | The custom-lobby queue/matchmaker: join, leave, balance teams, MMR, ranks, win reports, stats, koth. | 22 commands: `!register !join !leave !pos !queue !balance !next !reroll !format !kick !mmr !setmmr !lobby !win !mode !pick !stats !rank !top !check !finish !koth` | **REPLACED** by PinguinoB0t (core), same code, runs inside the Host. Data stays in `Data\runtime`. |
| **chatbot** (C#) | The old AI chat bot. | every Twitch chat message | **REPLACED** by ChattyPinguino (with Router). |
| ChatGPT Answers / Random Messaging / _Set-Up_ / Shoutouts + command "ChatGPT Call" | The stock ChatGPT add-on pack. | `@PinguinoB0t` regex, `!gptSetup`, `!gptso` | **DROP** (all four actions disabled; the command "ChatGPT Call" is still enabled and would double-answer if Streamer.bot stays open). |
| **First** (C#, "First 5" game) | In each stream the first 5 chatters win a place; places pay points after a delay (5/10/25 min waits); `!first` = your record, `!firsts` = leaderboard. Stats live in Streamer.bot globals (`firstPlaceStats`...), reset by the "Stream Status (Online)" action. | `!first`, `!firsts`, every chat message | **NEEDS-BUILD (02)**. `PinguinoBotFirsts.cs` exists in the repo but the Host does not load it yet. Needs: load it as a bot module, reset on stream online, migrate the stats out of `globals.db`. Decide first whether the points payout (done through another system) still applies. |
| Commands `!commands`/`!cmds`, `!setgame`, `!shout`, `!clip`, `!whyad`, `!preroll`... | See the rows below. `!commands` is just a list; `!setgame` has **no action** attached (dead). | | `!commands`: **REPLACED** by the Host's command list. `!setgame`: **DROP**. |

## 2. Alerts: follows, subs, cheers, raids

All of these say a thank-you line in chat through the bot account, then run the small action **latest** (shows the "Latest Group" in the Alerts scene for 10 s).

| Action | What it says / does | Trigger | Status |
|---|---|---|---|
| **Followed** | "innoce108Cool Hello %user% just followed! Welcome to the community!" + run `latest` | follow | **NEEDS-BUILD (02, no code)**: create as a Host action (follow trigger, say + OBS). The importer does convert follow triggers, so this one is **CAN-IMPORT** for the text; the OBS part is a manual step. |
| **Normal / Super / Prime** (3 actions) | Thank-you line per sub kind ("Enjoy the stream", "super sub", "Amazon Prime") + `latest` | sub (tier filters 2 / 12 / 1) | **CAN-IMPORT** (text) + OBS step by hand. Host's sub trigger knows tiers 1-3, not Prime: add a Prime condition on `{tier}`. |
| **Resub** | "%user% resubbed with a %tier% sub! Thank you." + `latest` | resub | **CAN-IMPORT** + OBS step. |
| **Gifted** | "%user% gifted a sub to %recipientUserName%!" + `latest` | gift | **CAN-IMPORT** + OBS step. Host has no `{recipient}` variable yet: **NEEDS-BUILD (02, tiny)**. |
| **Cheers** | Under 500 bits one message, over that a different one, + `latest` | cheer | **CAN-IMPORT** + OBS step. |
| **Raided** | Raid-in welcome with emote spam, delays, then a final action | raid in | **DROP-or-IMPORT**: it is **disabled** in Streamer.bot. Import it if you want it back. |
| **Raid Out Start** | "Raid started! Prepare your emotes!..." then 3 s later the Discord invite | you start a raid (trigger 158) | **NEEDS-BUILD (02)**: Host has no raid-out trigger (needs EventSub `channel.raid` from the broadcaster). |
| **Raid Out End** | one OBS sub-action (state 0, looks like Stop Streaming) | raid completes (159) | **NEEDS-BUILD (02)** with the trigger above. |
| **latest** | Shows scene Alerts / "Latest Group" for 10 s | called by the actions above | **NEEDS-BUILD (02, no code)**: Host action `obs_source show, delay 10000, hide`. |
| **Add Ban** | When someone is banned: shows the Among Us "ejected" browser source with their name, plays the eject sound at 90 %, hides it after ~5 s | Twitch ban event (137) | **NEEDS-BUILD (02)**: Host needs a ban trigger (EventSub `channel.ban`) and a browser-source URL setter (OBS request). Sound file: `Documents\amongusban\Sounds\eject_amongus.mp3`. |

## 3. Stream status, title and game

| Action | What it does | Status |
|---|---|---|
| **Stream Status (Online)** | Says "Stream is live! Today we are streaming %game%." and resets the First-5 game (C#). | **NEEDS-BUILD (02, small)**: Host `stream_online` trigger exists (needs the new scope: re-sign the streamer in). Needs the First-5 reset once that is rebuilt. |
| **Stream Status (Offline)** | Says "Stream offline. Goodnight everybody. Thanks for tuning in!", runs another action, one OBS item, and **adds 1 to the persisted `dayCounter`** ("Day 12" in the titles). | **NEEDS-BUILD (02, small)**: Host `stream_offline` + `inc_var dayCounter`. **Copy today's `dayCounter` value from Streamer.bot first** (it is in `globals.db`), or the titles restart at Day 1. |
| **RL Playing w/ Viewers, RL (customs), RL (Cash Tourney 2v2), REPO, MC Community Server** (5) | Change the Twitch title (always with `Day ~dayCounter~`) and the game/category. The MC one sets the "Switching to Minecraft" title, waits 7 min, then sets the Day-N title. The four RL/REPO ones all hang off the **same** command `!setCustoms`; as exported they would all run and the last wins, so check which one Ivan actually uses. `!setMcServer` is the Minecraft one. | **NEEDS-BUILD (02)**: Host has no "set title/game" step (Helix `PATCH /channels`, scope `channel:manage:broadcast`) and no game lookup. Titles can be recreated as presets once the step exists. |
| **Streambot** | Says "i here" on trigger 706 (a start-up test). | **DROP** |
| **Pinguinobot visible in stream chat** | Empty action, no triggers. | **DROP** |

## 4. Chat sounds, welcomes and intros

| Action | What it does | Status |
|---|---|---|
| **chat** | Plays `mixkit-message-pop-alert-2354.mp3` at 50 % on every chat message except PinguinoB0t, StreamElements, Nightbot, SoundAlerts. | **NEEDS-BUILD (02, no code)**: Host `chat` trigger + `sound` step with a user filter; or drop it if Ivan does not want a pop on every line. |
| **chat (yt louder)** | Same pop sound at 76 % for YouTube/Kick chat messages (triggers 4003, 35010). | **NEEDS-BUILD (03 Multi)**: Host does not read YouTube chat. |
| **First TIme System (Bell)** | First message ever seen from a user id: doorbell wav at 24 %, "Welcome to chat %userName%!" and a saved "seen" flag. | Details were sent to 03. **NEEDS-BUILD (03/02)**. Not in the importer list (no double ding). Note the welcome line duplicates ChattyPinguino's. ChattyPinguino only welcomes while live and on Twitch's first-ever-message flag. |
| **chat (first time today) T2** and **T2 (Copy)** | On each chatter's first message of the stream (First Words trigger): new-notification sound at 50 %, except for the bots and for `cyfirl` / `Nerqx_` (they have personal intros). | **NEEDS-BUILD (02)**: Host has no "first message today" trigger; add one with a per-day seen set. |
| **chat (first time today)** (disabled) | Personal intro videos for 5 viewers (`SkyRLTN`, `syddneeyyyy`, `flayir_`, `snowyroses_`, `mashka_rl` and the two T2 exclusions): pauses Spotify, mutes it, plays a `.mov` in the "First Time" scene, restores. | **NEEDS-BUILD (intro scheduler, Chat/Unit 03)**. It is disabled today, so nothing is lost on closing; decide if you want it back. |
| **top tt likers and gifters** | Shows two TikTok leaderboard sources. | **DROP** (disabled, TikTok only). |

## 5. Moderation, ads, clips, shoutouts, rewards

| Item | What it does | Status |
|---|---|---|
| **Clip** (`!clip`) | Says "Clipped", waits 10 s, creates a Twitch clip titled "Clip! cmd" (60 s), waits 15 s, one more step. A 5-second timer "Clips 5 sec checker" exists. | **NEEDS-BUILD (02)**: Host needs a create-clip step (Helix, scope `clips:edit`). |
| **Preroll** (`!preroll`, `!ad`, `!ads`) | Reads the ad schedule (preroll-free time left), formats it, says "M:SS left." Timer "Preroll Checker" refreshes it every 30 s. | **NEEDS-BUILD (02)**: Helix ad-schedule read (scope `channel:read:ads`) + the command. |
| **Whyad** (`!whyad`, `!whyads`) | Static text explaining why ads run mid-stream. | **CAN-IMPORT** |
| **Shoutout group (StreamUP freebies)**: Pronoun Support (`!shout`), Main Action, Manual Shoutout Buffer (trigger 144), Run Shoutout | Mods type `!shout name`; it looks up the user, pronouns, last game and says "Go and Follow..."; a queue spaces shoutouts 130 s apart. The command entry "Quick Shoutout" is disabled. | **NEEDS-BUILD (02, lower priority)**: shoutout step (Helix `POST /chats/shoutouts`) + pronouns + queue. |
| **Reward: Instantly End Stream** (2,500,000 pts) | Redeem triggers one OBS action (state 0: stop streaming). | **NEEDS-BUILD (02, no code)**: Host `redeem` trigger + `obs_request StopStream`. The importer converts the trigger but not the OBS step. Needs the new `channel:read:redemptions` scope (re-sign the streamer in). |
| **Reward: Suggestion** (5 pts) | Appends `<counter> <user> - <text>` to a file. | **NEEDS-BUILD (02, small)**: Host has no "append to file" step. |
| The other ~70 channel point rewards in `twitch_rewards.json` | They live on Twitch, not in Streamer.bot (this file is only a cache). Streamer.bot has no actions for them. | Nothing is lost on closing. |
| **Bans** | See `Add Ban` above. | |

## 6. Settings, timers, data and integrations that disappear with it

- **Timers** (`settings.json`): Preroll Checker (30 s), Clips 5 sec checker (5 s), top tt likers (10 s, disabled). None is bound to an action in the export; keep only the ad and clip needs above.
- **Queues:** Ads, latest, Twitch API, Twitch Clip, StreamUP shoutout, First Time. Streamer.bot internals; **DROP**.
- **Saved data in `globals.db`** (do not edit, copy values out before closing): `dayCounter`, the First-5 stats (`firstPlaceStats` ... `fifthPlaceStats`), `firstChatter*`, per-user `seen<userId>` flags, `shoutoutCount`. Also `firstwords.db`, `pronouns.db`, `quotes.dat`, `users.dat` (there are no quote commands in the export).
- **Connections** Streamer.bot holds: Twitch, **YouTube and Kick chat**, OBS WebSocket, Stream Deck, MIDI, Meld Studio. After closing: YouTube/Kick chat reading goes to **Multi (03)**; OBS is held by the Host; **Stream Deck/MIDI buttons that call Streamer.bot actions will stop working**. Check what is bound (`midi.json`, `streamDeckSettings`) and re-point them to the Host: `POST /api/automations/fire {"hotkey": "..."}`.
- **Other bots still in chat** (StreamElements, Nightbot, SoundAlerts, synchrabot) are independent of Streamer.bot and keep running.

## 7. Cutover checklist (in order)

1. **Back up** `Documents\PinguinoB0t\data` (copy the whole folder) and note today's `dayCounter` value.
2. **Rebuild/restart the Host** with the latest batch (done by 00), then sign the streamer account in again (new scopes: `moderation:read`, `channel:read:redemptions`) and sign in ChattyPinguino and PinguinoHelper.
3. **02 builds** (tell 00 in one batch): title/game step + `!setCustoms`/`!setMcServer` presets with `dayCounter`; `stream_online`/`stream_offline` presets (say lines, day counter +1, First-5 reset); create-clip step + `!clip`; ad-schedule + `!preroll`; ban trigger + Among Us alert; raid-out trigger + presets; append-to-file; shoutout step; "first message today" trigger; load `PinguinoBotFirsts`. Seeded **disabled**, like the Spotify ones.
4. **Import** the safe ones: Actions & Events > Import from Streamer.bot (preview, then merge): Followed, subs, Resub, Gifted, Cheers, Whyad. Review each, add the OBS "latest" step, enable.
5. **Decide with Ivan**: pop sound on every chat message (keep/drop), the old "Welcome to chat" line (ChattyPinguino already welcomes), personal intro videos, First-5 points payout, Raided (disabled today), shoutout queue.
6. **03 builds** YouTube/Kick chat reading and the new-chatter ding.
7. **Test while offline-safe:** run each new Host action with *Test (dry run)*, then once for real in a quiet moment (`!clip`, `!preroll`, a ban alert on a test account, `!setCustoms`).
8. **Disable (do not delete) in Streamer.bot** the actions that are now replaced, one group at a time: BVQ Engine, chatbot, First, First TIme System (Bell), chat, chat (first time today) T2 and (Copy), the alert actions, Stream Status, GameUpdates, Preroll, Clip, Add Ban, Raid Out, shoutouts. Watch one full stream.
9. Only then **close Streamer.bot**. Keep the folder for a month for rollback (re-enable = turn the actions back on).

## 8. What stays off

All ChatGPT* actions and the "ChatGPT Call" command, "Streambot", "Pinguinobot visible in stream chat", `top tt likers and gifters`, `Raided` (unless re-imported on purpose), the old pasted copies of PinguinoBot/Chat inside Streamer.bot, and the song-request actions in the Host (off by default until Ivan turns them on).
