# Streamer.bot parity table (final audit, 2026-10-19)

Read-only walk of `Documents\PinguinoB0t\data` (`actions.json` 44 actions, `commands.json` 36, `twitch_rewards.json`, `settings.json`, `globals.db`, `obs.json`), of the 19 browser sources in OBS, and of `Documents\Stream\*.html`. Companion: `STREAMERBOT_REPLACEMENT.md` (per action). Status words: **DONE** (works in the Host), **OFF** (built, switched off by the Streamer.bot cutover or until reviewed), **MULTI** (03 owns it), **DROPPED** (reason).

## A. Things outside Streamer.bot's action list that depend on it (found by the audit)
| What | Where | Status |
|---|---|---|
| **Credits roll** | OBS browser source "Credits" = `Documents\Stream\creditsnew.html`, which connects to `ws://127.0.0.1:8080` and asks Streamer.bot `GetCredits` | **DONE**. After the cutover the Host listens on `127.0.0.1:8080` and answers `GetCredits` in the same format, so the file works unchanged. Also `GET /api/credits` and a built-in page `http://127.0.0.1:8770/overlay/credits` (look, titles, sections in `credits_settings.json`; `?test=1` shows sample names). History difference: Streamer.bot's all-time/month/week bits and points rankings cannot be imported; the Host starts its own ledger now |
| `newchatter.html` (welcome banner) | `Documents\Stream`, expects a `firstChatter` WebSocket message to `ws://192.168.0.11:8080`; nothing in Streamer.bot sends it and it is not an OBS source | **DROPPED** (unused) |
| `credits.html` (older credits) | same protocol as creditsnew.html | **DONE** (same WebSocket answers it) |
| Stream Deck / external WebSocket clients | Streamer.bot WebSocket server `0.0.0.0:8080` (password on, not enforced) | **DONE** for same-PC clients: `GetActions`, `DoAction` (by id or name), `GetInfo`, `Subscribe`, `GetCredits`. Imported actions keep their Streamer.bot **id**, so existing Stream Deck buttons keep working. Not implemented: event broadcasts to subscribers (no consumer found), remote-PC access (listens on 127.0.0.1 only) |
| OBS "lastest" browser source | third-party widget `vrflad.com/latest` | **DONE** (own overlay `/overlay/latest`, switch the URL when you want; Host never changes it) |
| OBS heartrate, Sound Alerts, StreamElements, Twitch alert box, TikFinity, SynchraChat, vox.bot TTS, teklynk shoutout, Viewer Attack | independent web widgets, not Streamer.bot | unaffected |
| Queue / Players overlays | Host serves them | **DONE** (already) |

## B. Triggers used by your 44 actions
| Streamer.bot trigger | Used by | Host |
|---|---|---|
| Command (401) x37 | BVQ (22), Clip, Whyad, Preroll, titles, shoutouts... | **DONE** (`command` trigger; BVQ in PinguinoB0t). Game/title commands **DROPPED** (Ivan) |
| Follow 101 / Cheer 102 / Sub 103 (x3) / Resub 104 / Gift 105 / Raid 107 | alerts | **OFF until cutover** (`follow`, `cheer`, `sub`, `resub`, `gift`, `raid`) |
| Reward redemption 112 x2 | End Stream, Suggestion Box | **OFF** (`redeem`) |
| First Words 120 x3 | first-time-today sounds / intros | trigger **DONE** (`first_today`); sounds and intros are **MULTI** (03) / intro scheduler |
| Chat message 133 x5 | chat pop sound, chatbot, First, Bell | bots **DONE**; pop sound / Bell **MULTI**; First 5 **OFF until cutover** |
| Ban 137 | Add Ban | **OFF until cutover** (`ban`) |
| Shoutout created 144 | StreamUP buffer | **DROPPED** (our shoutout queue replaces StreamUP) |
| Stream online 154 / offline 155 | status lines | **OFF** (`stream_online`/`stream_offline`; First 5 resets by itself; recap preset added) |
| Raid out 158 / raid end 159 | raid-out lines + stop | **OFF** (`raid_out`; end folded into the same preset) |
| TikTok 701 | top likers | **DROPPED** (disabled, TikTok) |
| 706 (Streamer.bot started) | "i here" test | **DROPPED** |
| YouTube chat 4003 / 35010 | louder pop sound | **MULTI** |

## C. Sub-actions used (38 types, 270 uses)
| Streamer.bot sub-action | Count | Host |
|---|---|---|
| Send chat message (10, 23) | 23 | `say` / `random_say` (as core / chat / helper) **DONE** |
| Delay (1002) | 23 | `delay` (now accepts `{variables}`) **DONE** |
| If / else (120, 99901, 99902) | 29 | `if` + conditions **DONE** |
| OBS show/hide source (30) | 54 | `obs_source` **DONE** |
| OBS browser URL (38) | 1 | `obs_request SetInputSettings` **DONE** |
| OBS stop streaming (33) | 2 | `obs_request StopStream` (OFF presets) |
| OBS replay buffer (321) | 1 | `obs_replay_save` **DONE** |
| Press key (1012) | 24 | `press_key` (media keys, F1-F24, virtual keys) **DONE** |
| Play sound (1) | 6 | `sound` + per-alert `alert_sound` **DONE** |
| Write to file (3) | 1 | `append_file` **DONE** |
| Run action (4) | 15 | `run_action` **DONE** |
| Twitch create clip (18) | 1 | `create_clip` **DONE** |
| Twitch ad schedule (557) | 1 | `ad_schedule` **DONE** |
| Twitch shoutout (29), user info (50), pronouns (15001) | 7 | `shoutout_queue` (card + game + pronouns) **DONE** |
| Set title / game (15, 16, 251, 252, 564) | 26 | **DROPPED** (Ivan will make his own) |
| Get/set global variable (121, 122) | 7 | `set_var`, `inc_var`, `{var:name}`, `/api/vars` **DONE** |
| Set argument (123), break/stop (124) | 8 | variables in templates, `stop` **DONE** |
| Comment (1009) | 15 | `comment` **DONE** |
| Queue / system controls (1003, 1008, 1011, 1026, 1027) | 5 | per-action serialisation + pause/resume (`/api/queues`) **DONE** (different model, same effect) |
| Text-to-speech (601), input prompt (1023) | 2 | only used by the disabled ChatGPT pack: **DROPPED** |
| C# code (99998, 99999) x10 | 10 | the bots (BVQ, chat, First, etc.) run as C# inside the Host **DONE**; arbitrary new C# is **not offered** (use steps) |

## D. Features of Streamer.bot itself
| Feature | Host |
|---|---|
| Actions, groups, enable/disable (single or whole group) | **DONE** (`/automations`, `POST /api/automations/enable`) |
| Queues (blocking/non-blocking, pause) | **DONE** as above |
| Variables (global, persisted) | **DONE** (`/api/vars`, editor in the Suite) |
| Test run / dry run, action history | **DONE** (Test, Recent runs, `GET /api/automations/log`) |
| Import / export | **DONE** (import from Streamer.bot keeps ids; `GET /api/automations/export`) |
| Hotkeys / Stream Deck / websocket server | **DONE** (hotkey triggers, `/api/automations/fire`, `/api/automations/hotkeys`, compat WebSocket, `/api/endpoints`) |
| HTTP server (off), UDP (off), MIDI (no devices), Stream Deck server (off) | not used: **DROPPED** |
| Timers (Preroll Checker 30 s, Clips checker 5 s, TikTok 10 s) | replaced by on-demand reads / **DROPPED**; Host has a `timer` trigger |
| Twitch present-viewers list, emote handlers (BTTV/7TV), Twitch viewer tracking | Streamer.bot UI only: **DROPPED** |
| First Words database | `first_today` trigger (per local day) **DONE**; sounds/intros **MULTI** |
| Credits | **DONE** (section A) |
| Sub-actions for streaming tools you do not use (Voicemod, VTube Studio, Pulsoid, SpeakerBot, Elgato, Meld, Lumia, HypeRate, PolyPop, Throwing System, TipeeeStream...) | no action uses them. HypeRate "F204" and Lumia are connected but unused by any action; your OBS heartrate widget talks to HypeRate directly. **DROPPED**; tell us if you rely on one |
| YouTube chat / events, Kick | **MULTI** (03) |
| Streamer.bot chat commands database (`commands.json`, 36) | BVQ ones **DONE** in PinguinoB0t; `!commands`/`!cmds` **DONE**; `!first`/`!firsts` **OFF until cutover**; `!clip`, `!whyad`, `!preroll` **OFF until cutover**; `!shout` **DONE** (new queue); `!setCustoms`, `!setMcServer`, `!setgame`, GPT commands **DROPPED** |
| 70+ channel point rewards | live on Twitch, unaffected |

## E. New in the Host (not in Streamer.bot)
Session numbers and goals (`!session`, `!goal`, `/overlay/goal`, `session_settings.json`), activity feed (`/api/activity`) with optional website mirror, latest overlay with `!latest`, `!pg` mod control, cutover switch, Pre-stream checks (permissions, event delay, replay buffer), alert popup and per-alert sounds (`alerts_settings.json`), shoutout queue with pronouns, credits look settings.

## F. Cutover checklist (in this order)
1. Back up `Documents\PinguinoB0t\data`. Copy the 5 First 5 stats out of Streamer.bot (Globals) into `Data\runtime\host_globals.json` (see `STREAMERBOT_REPLACEMENT.md` section 9).
2. Host rebuilt and running (00). Streamer signed in again (new permissions); ChattyPinguino and PinguinoHelper signed in. Pre-stream list green (Streamer permissions, OBS, replay buffer).
3. OBS: enable and start the **Replay Buffer** (Settings > Output > Replay Buffer; press Start before streaming). Optional: point the "lastest" browser source at `http://127.0.0.1:8770/overlay/latest`, the "Credits" source needs nothing (or use `/overlay/credits`).
4. In the Suite open Actions & Events and review the Streamer.bot replacement group (texts, sounds in `alerts_settings.json`, goals in `session_settings.json`).
5. Test while Streamer.bot is still open and the cutover is OFF: `!shout`, `!latest`, `!session`, `!goal`, `!pg status`, Test buttons.
6. **Close Streamer.bot.** Press **Streamer.bot cutover** (turns the alerts, `!clip`, `!preroll`, `!whyad`, ban alert, First 5 game and the 8080 compatibility server on). Check the Console line "compat-ws ... listening".
7. First stream: watch the Activity feed and the Console; `!clip` once; `!preroll` once.
8. Keep Streamer.bot's data folder for a month for rollback (press the cutover button off, reopen Streamer.bot).

**What stays off:** ChatGPT pack, title/game commands, TikTok, Streamer.bot's own bots/pop sounds (03 decides), raid-out, End Stream reward, Suggestion Box, stream on/off lines (until reviewed).
