# Closing Streamer.bot: what it does today and what replaces it

Source: read-only look at `Documents\PinguinoB0t\data` (`actions.json` 44 actions, `commands.json` 36 commands, `twitch_rewards.json`, `settings.json` timers, `globals.db` name only). Nothing in Streamer.bot was changed. Written by 02 (PinguinoBots/Host), 2026-10-19.

**Status words**
- **REPLACED**: something already in the Suite does it (names who).
- **CAN-IMPORT**: Host *Actions & Events > Import from Streamer.bot* converts it (arrives disabled; review).
- **NEEDS-BUILD**: not covered yet; says what is missing and who owns it.
- **DROP**: dead, disabled or a placeholder; safe to lose.

**Update (batch built, awaiting Host rebuild):** 02 has built the Host side (section 9). After the Host restarts and the streamer signs in again, the remaining blockers are the data copy-over, your review of the presets, and 03's YouTube/Kick chat. Original verdict kept below.

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

## 9. Status per item after Ivan's decisions (02 batch, committed; goes live with the next Host build)

Ivan's cutover decisions: game/title changes are dropped (he will make his own), no day counter. Chat pop sounds, first-today and first-time dings and YouTube/Kick chat belong to 03 (Multi). "ON" = created enabled; the presets are the group "Streamer.bot replacement" on `/automations`. Sign the streamer in again once after the rebuild (new permissions: `clips:edit`, `channel:read:ads`, `moderator:manage:shoutouts`, `channel:moderate`).

| Item | Status | How |
|---|---|---|
| BVQ Engine (22 commands), chatbot, `!commands` | **DONE** | PinguinoB0t / ChattyPinguino in the Host |
| First 5 game (`!first`, `!firsts`) | **DONE, ON** | `PinguinoBotFirsts.cs` is loaded by the Host: claim on every chat line, reset when the stream goes online, payouts on a background timer (lost if the Host restarts before they finish). Tested in sim. Old stats must be copied by hand (below) |
| Followed, Normal/Super/Prime, Resub, Gifted, Cheers | **DONE, ON** | actions "Alert: ..." (chat thank-you as PinguinoB0t + the Latest Group popup in OBS). Prime cannot be told from tier 1; gifts fire once per gift bomb |
| Raided (was OFF in Streamer.bot) | **DONE, ON** | "Alert: incoming raid": thanks, emotes, welcome, popup, then a queued shoutout for the raider |
| `latest` (show Latest Group 10 s) | **DONE, ON** | "Alerts: show Latest Group" (OBS scene Alerts / group Latest Group). Tested against the real OBS: shown, then hidden again |
| Latest feed (what the Latest Group displays) | **DONE** | The old group showed a third-party widget (`vrflad.com/latest`). Ours: every follow/sub/resub/gift/cheer/raid/redeem is stored (`latest.json`); OBS browser source `http://127.0.0.1:8770/overlay/latest?types=follow,sub,cheer,raid` (same orange; `color=`, `size=`, `font=`, `rotate=` options), `!latest` in chat, optional OBS text source via `latest_settings.json {"TextSource":"name"}`. **Your OBS still points at the old widget: change the URL of the browser source "lastest" to the address above when you want to switch.** The Host does not touch that source |
| Add Ban + ban alert | **DONE, ON** | trigger `ban` (needs `channel:moderate`) sets the URL of the browser source "Ban Alert - Among Us Ejected" (user name in the page), shows it, plays eject_amongus.mp3 at 90 %, hides it after 5 s. Tested against the real OBS (quiet sound) |
| **Clip** | **DONE, ON** | same order as the old action: says "Clipped"; 10 s later makes a Twitch clip (title "Clip! cmd", 60 s); 15 s later saves the **OBS replay buffer** (SaveReplayBuffer, file name read back from OBS). The old action did nothing after that; we add an Activity entry and a Console line. **The replay buffer must be running: when tested it was OFF in your OBS.** The Host reports that in Pre-stream ("OBS replay buffer running") and in the log instead of failing silently. End to end with the buffer started: saved `D:/Recordings/... replay.mov` (the test file was deleted again, the buffer stopped again). The Twitch-clip half needs a live stream and `clips:edit`, so it was not testable offline |
| Preroll (`!preroll`, `!ad`, `!ads`) | **DONE, ON** | PinguinoHelper answers with the preroll-free time left (same format `M:SS left.`) plus when the next ad starts; reads Twitch directly every time instead of the 30 s timer. Needs `channel:read:ads`; not testable offline |
| Whyad (`!whyad`, `!whyads`) | **DONE, ON** | PinguinoHelper, same text (ends with "Use !preroll to check ad status") |
| Shoutouts | **DONE, ON** | our own queue (not StreamUP): `!shout name` / `!so name` (mods) or `POST /api/shoutouts {"user":"name"}`; Twitch's own shoutout card (one per 2 min), then a chat line with their last game and pronouns (alejo.io, they/them if unknown); repeats within 2 min ignored (raids: 60 min); queue at `GET /api/shoutouts`; lines editable in `shout_settings.json` |
| Activity feed (new, for the shell) | **DONE** | `GET /api/activity?since=<seq>&limit=&type=` (see ACTIONS.md), declared in the manifest |
| Stream Status online / offline | seeded OFF | lines only; the First 5 reset happens by itself. No day counter, no title change |
| Raid out, End Stream reward, Suggestion Box | seeded OFF | review first; raid-out and End Stream end the stream, so they stay off |
| Game / title commands (`!setCustoms`, `!setMcServer`, `!setgame`) and `dayCounter` | **DROPPED** | Ivan will make his own |
| Chat pop sound, first-time-today sound, new-chatter ding, YouTube/Kick chat | **03 (Multi)** | |
| Personal intro videos, TikTok, ChatGPT pack, Streambot, empty "visible in stream chat" | **DROP / later** | |

Other differences: Twitch's event for a sub does not say Prime. Gifted subs arrive once per gift bomb (`{total}`). Clip has a 25 s cooldown (the old one had none).

**Copying your First 5 stats over (with the Host stopped, before the first stream on the new setup):** `dayCounter` is no longer needed. The First 5 stats (`firstPlaceStats` ... `fifthPlaceStats`) are stored by Streamer.bot in a form `Tools\import-streamerbot-globals.py` cannot read: open Streamer.bot > Settings > Globals (or Variables), copy each value and save it into `Data\runtime\host_globals.json` under the same name (a JSON text like `{"name":3,...}`). Without this the leaderboard starts empty.

## 10. Stream Deck, MIDI and other things that call Streamer.bot

From `settings.json`: MIDI has no devices; Streamer.bot's Stream Deck server is **off**; its WebSocket server is **on** (`0.0.0.0:8080`, auth on, no connections listed) and its HTTP server is off. So nothing in the export proves a button depends on it, but anything that connects to `ws://<this PC>:8080` (a Stream Deck plugin, a phone app, SoundAlerts-style tools) will stop working when Streamer.bot closes.
Re-point instructions:
1. For a Stream Deck button, use *System > Website > GET/POST in background* (or the "API Ninja" plugin) on `POST http://127.0.0.1:8770/api/automations/fire` with body `{"hotkey":"brb"}`; the action must have a trigger of type **Hotkey** with key `brb`.
2. For a button that used to run a Streamer.bot action by name, make a Host action with a Hotkey trigger and the same steps, then call the URL above. If a call is refused, send the app/module token (Authorization: Bearer ...) or call from the same PC (same-origin rules in ACTIONS.md).
3. Open Streamer.bot > Servers/Clients and Stream Deck once and write down who is connected before closing it; point those clients at the Host URL above.
