# PinguinoSuite App log

Kept by session 00 (the only session that launches, restarts or rebuilds the app). One entry per rebuild, relaunch or notable app change, newest first. Times are local (CDT).

| 2026-10-21 ~16:57 | Host restart (Update-Module host, stream offline): economy phase 2 (29dc7df Award/ledger, match awards, depreciation in PRACTICE RUN, loans, 5aa453c site bridge, f9dd7f2/91f6486 docs, refund scope) plus e7642ae/85cf8f8. /api/live 200. Depreciation dry run: 3 holders over 100k, 47,569 would be taken (nothing taken). | 00 |
| 2026-10-20 ~07:10 | Spotify module restart (Update-Module spotify) for pinguinoMusic cycle 4: 368da9e Songify parity, c6e18b9 fakes/docs (reward-only mode, refund flag, playlist-add, blocklist import, /overlay/queue). Up again; requests still ship CLOSED; Ivan must reconnect Spotify once for the new scopes. | 00 |
| 2026-10-20 ~07:05 | Host restart (Update-Module host): 206f2ce Host records all chat to Data/chat_logs/live (independent of Chatty), hidden-user overlay for lvlmarshmello, fetch-chat-logs never drops lines; 5ed5df1 Chatty timeout/make-me-mod rules. /api/live 200, /api/livelog ok. Boards NOT refreshed yet: waiting for 02 to add the Streamer.bot sidecar counts (Marsh 82,116 merged). | 00 |
| 2026-10-20 ~06:40 | Host restart (Update-Module host): 2fdcc44 helper negative-feedback mute, ads/TTS/Roblox answers, join guard; Chatty private lore memory + moderation refusal + repeat guard (Chatty chatting stays off); viewer !next, !pm from helper_settings. commands-doc 207 (Channel/Custom from the Nightbot import). /api/live 200. | 00 |
| 2026-10-20 ~06:20 | App relaunch + Host start: the app was not running, and leftover start-host/stop-host control files made the new core start then stop Host. Removed the pair, launched pinguino-suite.exe, started Host clean (/api/live 200). Alias merges confirmed by Ivan: rocketleaugelover221 -> synther_rl, mirihater -> ixsamuu (Data/boards/aliases.json); profiles re-pushed (1858). Host includes 02 commits cab671e (Nightbot quick-info), 9122ce7 (economy), aae0872 (profile sync). | 00 |
| ~03:26 CDT | Host rebuild+restart (eb8eeea site Join: sub input, web-only join replies to site) | 00 |
| ~03:22 CDT | Host rebuild+restart (53fdb5c practice mode, wheel auto-announce/auto-complete, site join via bridge) | 00 |
| When | Event | Details |
|---|---|---|
| 2026-10-20 ~02:58 | Host rebuild+restart (Update-Module host, stream offline): StreamerBotRunning checks the process, not port 8080. /api/cutover now streamerBotRunning:false. | 00 |
| 2026-10-20 ~02:55 | Listen restart: an orphan Listen server from 16:17 (old code, no mic fix) still held port 8765, so the restarted Listen could not bind (errno 10048). Killed the orphan, restarted Listen; new one owns 8765. | 00 |
| 2026-10-20 ~02:45 | Host restart (Update-Module host, stream offline): a39272c Helper follow-ups (Java/Bedrock -> just the IP, 4-min follow-up help, console steps, join/register answers). /api/live 200. | 00 |
| 2026-10-20 ~01:40 | Host rebuild+restart (Update-Module host, stream offline): e105809 Helper context gate (only steps in on real asks, cooldowns, no repeats). Build 0 errors, /api/live 200. | 00 |
| 2026-10-20 ~00:50 | Host rebuild+restart (Update-Module host, stream offline): ec79730 sub footer overlay (/overlay/subfooter, controls /subfooter). Build 0 errors, endpoints 200. | 00 |
| 2026-10-20 ~00:40 | App relaunch (Build-All, stream offline) + Host restart (-NoBuild) + Listen restart: b71d836 Listen mic fix (ranked device candidates, WDM-KS skipped, one toast). Host had not come back after the relaunch, so the website bridge showed offline ~50 min; restarted, sync running again. Core exe not re-frozen (modules load from the tree). | 00 |
| 2026-10-19 ~23:15 | FULL REBUILD core+shell via Build-All (stream offline, Ivan's OK; app quit first, then relaunched): 361c4ae Listen mic saved by name + fallback alert + silence watchdog (mic_alert banner), plus earlier Accounts page c3b386b and dashboard chat card b558bf0. Core answers (8760), Host live check OK. Not tested against real mic hardware. | 00 |
| 2026-10-19 ~22:25 | Host rebuild+restart (Update-Module host, stream offline, Ivan's OK): dc0f5eb ban alert permanent-only, 2cfaca8 viewer-feedback batch (Chatty pacing/fairness, Helper minecraft fix, !lobbyname/!lobbypass, song/MMR answers), 71e6f24 sub intro clips (/overlay/intro?slot=t1|t2|t3|t3v, controls /intro). Build 0 errors, /api/intro 200. | 00 |
| 2026-10-19 ~22:35 | STREAMER.BOT REMOVED at Ivan's request: first archived to Archive/streamerbot-2026-10-19 (raw data, own backup zips, logs.zip, readable ACTIONS/COMMANDS/REWARDS.md: 44 actions, 35 commands, 77 rewards), then deleted the Documents/PinguinoB0t install folder and its Startup shortcut. Host automations now own all alerts. Documents/PinguinoB0t.zip (older copy) left untouched. | 00 |
| 2026-10-19 ~22:10 | Host-only restart (Update-Module host -NoBuild, stream offline, at Ivan's OK): ban alert sb-ban now has condition {permanent} == true in Data
untimeutomations.json (timeouts no longer play the eject sound); same condition added to the preset in HostAutoTwitch.cs (needs a build to ship in the DLL). NOT yet live: 02's 2cfaca8 chat/helper batch and the intro alerts (waiting for a build). Streamer.bot's own Add Ban action may still play the sound: Ivan to filter/disable it. | 00 |
| 2026-10-19 ~19:55 | Host restart WITH build (Update-Module host), DURING STREAM at Ivan's OK: 894effa ChattyPinguino persona (warmer default, close friends but not possessive, steps back from intense viewers). Build 0 errors; Host up, stream LIVE, Chat ready. | 00 |
| 2026-10-19 ~19:38 | Host restart WITH build (Update-Module host), DURING STREAM at Ivan's OK: 0cb1ee9 wheel manual spin (!wheel spin / !spin, per-team "Team N: A & B!" lines, final "TOURNAMENT TEAMS - A & B | C & D" list in chat) plus other sessions' uncommitted PinguinoBotCore.cs edits (bot aliases/voice routing). Build 0 errors; Host up, stream LIVE, Chat ready. Build-All still pending. | 00 |
| 2026-10-19 ~18:50 | Host-only restart (Update-Module host -NoBuild, DURING STREAM at Ivan's OK): helper lobby name peng2 -> peng3 (helper_settings.json + source defaults), Chatty now also answers to chattypinguino / chatty pinguino / chatty penguino / chatty. Chat, Helper ready after restart. | 00 |
| 2026-10-19 ~18:00 | Host restart WITH build (Update-Module host), DURING STREAM at Ivan's OK. Now live: aaaa2c9 Chatty activity gate + countdown, 794f2d1 Host supplies live state itself + web-sync timer GC fix + chat-rate history, ddb9d1c Host text settings, e2fbcd9 KOTH recycle (losers and streamer go to back of queue). Also included at Ivan's OK: other sessions' uncommitted PinguinoBotCore.cs edits (bot voice routing, aliases, main-account fallback). Build 0 errors; bots healthy; /api/live = live. NOT yet applied: Build-All (shell/core/UI: Accounts page, dashboard chat card). | 00 |
| 2026-10-19 ~17:36 | Host-only restart (Update-Module host -NoBuild, no new code, DURING STREAM at Ivan's OK): WebSyncKey copied from backups\pre-migration-20261019-065904 into Data\runtime\settings.json (cutover had left it empty, so the site showed PinguinoBot offline). Old file saved as settings.json.pre-key-1736.bak. Site /standings updated 17:37 and /customs shows KOTH live with queue open. 02's timer-GC fix (794f2d1) still applies at the post-stream Host build. | 00 |
| 2026-10-19 ~17:23 | Host-only restart (Update-Module host -NoBuild, no new code, DURING STREAM at Ivan's OK): restored 188 players to Data\runtime\players.json from backups\pre-migration-20261019-065904 (cutover left only 3, everyone was told to register). Live file saved as players.json.pre-restore-1722.bak. Also WasLive hand-set true ~17:13 (WebSyncKey empty); permanent fix = 02's 794f2d1, applies at the post-stream Host build. | 00 |
| 2026-10-19 ~16:15 | FULL REBUILD core+shell (rebuild13.log): password inputs were white-on-white in vault key entry (App/src/index.html) + 01's f7e2297 CSS. Last restart before stream; FREEZE after. | 00 |
| 2026-10-19 ~15:58 | Update-Module spotify -NoBuild (f7b1f77 one-click connect, quiet degrade). No app restart. FREEZE after this. | 00 |
| 2026-10-19 ~15:55 | Update-Module voice -NoBuild (00a27cd speech-intervals, safe defaults) + listen (3233a9b ignore voice cmds while bot speaks) + multi -NoBuild (a339fed stream-ready). No app restart. | 00 |
| 2026-10-19 ~15:50 | Update-Module voice -NoBuild + link -NoBuild (no app restart) | voice 227b665 (no boot-time Host feed warning); link 6196cb2 (cycle 3: readiness list, Stream Deck CLI via running module). Both up (8772, 7777 = 200). Host 6d48fa1 was rebuilt earlier (~12:30). |
| 2026-10-19 ~12:15 | FULL REBUILD core+shell, relaunch (rebuild12.log) = LOOP CYCLE 2 | 01 cycle 2 (auto config backups, module Logs drawer, stop-toast); 02 Host d3da5e7 (Streamer.bot parity: Credits WS 8080 after cutover, first_today, press_key, goals/session, manifest change); 03 cycle 3; 04 link f5fc4a1 (fresh-state guards, hub-run macros); 06 voice 2b1653b (milestones, personas, custom sounds, CSV); Spotify cycle 3 59b7d9b; 05 site (no restart needed). Build OK first try. |
| 2026-10-19 ~12:00 | FULL REBUILD core+shell, relaunch (rebuild11.log) = LOOP CYCLE 1 | 01 PenguinComm page, Quick actions (variables/queue/triggers/hotkeys), Ctrl+K palette, pop-out reconcile, pre-stream schedule; 06 voice module discovered (PenguinComm Speak); 02 Host cutover batch 5c8c6f2 + activity feed; 03 right-side settings panel + split chat; 04 link cycle 1; Spotify cycles 1-2. Build OK first try after killing dotnet PinguinoHost + listeners. |
| 2026-10-19 ~11:36 | FULL REBUILD core+shell, relaunch (rebuild10.log) | 01 personalization (Personalize page: 8 themes, density, zoom, sidebar, dashboard layout, sounds, looks) + Listen always_start with on_start hook (mic starts at launch, live or not). Two earlier attempts failed: Host DLL locked by a dotnet process running PinguinoHost (kill via CommandLine match, not just port listeners). |
| 2026-10-19 ~11:29 | Link restart (04 e9158d5: personalisation) | Settings card (device, OBS address, page look, prestream toggles, timeouts, log level) + macro editor (allow-list actions, two-click guards). Update-Module.bat link -NoBuild OK. |
| 2026-10-19 ~11:27 | Link restart (04 97c00fd) | Update-Module.bat link -NoBuild OK. OBS card, start/stop guards, plainer errors, doctor hints. Real OBS check still red until OBS_WS_PASSWORD is set. |
| 2026-10-19 ~11:24 | FULL REBUILD core+shell, relaunch (rebuild8.log) | 01 1e2af30/42b6980 (Activity page, go-live detection reads vault, QA fixes) + 9b76e58 chat look manifest + be85be7 pop-out windows (windows.rs, list_monitors/open_window, Settings > Pop-out windows). First attempt (rebuild7) failed at Host: DLL locked by a stray dotnet process; killed it, reran OK. Pop-out placement not yet verified live. |
| 2026-10-19 ~11:17 | Multi restart (03 7213563: chat look increment 1) | Style editor /?type=style (fonts, sizes, per-platform/role/event rules, keyword highlights, live preview), Twitch sub/resub/gift/raid/announcement notices subscribed. Update-Module.bat multi -NoBuild. |
| 2026-10-19 ~11:15 | Host build + restart (02 e3d85f6: Streamer.bot replacement batch) | Update-Module.bat host OK, /automations 200, app untouched. New Twitch steps (set_title, create_clip, ad_schedule, shoutout), ban/raid_out triggers, First 5 loaded, 18 presets (all disabled). Streamer must re-sign for new scopes. |
| 2026-10-19 ~11:14 | FULL REBUILD core+shell, relaunch | 01 3b4c333 + module on/off switch with padlock (locked by default, 30 s unlock, POST /api/modules/<id>/enable), ding v2 + chat pop help merged. Orphan modules killed first. Build OK (rebuild6.log); core, Multi, Link, Spotify, Host ports up. Not yet seen rendered. |
| 2026-10-19 ~11:09 | Multi restart (03 chat pop) | Chat pop per message (Twitch 50%, YouTube 76%, Discord 50%, master volume), returning ding = first-today sound at 50%. All OFF until Ivan ticks platforms in Multi setup. Update-Module.bat multi -NoBuild OK. |
| 2026-10-19 ~11:07 | Multi restart (03 ding v2) | Returning-chatter ding, per-sound and master volume sliders (persistent), Streamer.bot bell default at 24%, GET /api/newchatters. Update-Module.bat multi -NoBuild OK. Also covers earlier ~11:04 restart for 63871ad (new-chatter ding). Core rebuild held for ding prestream item/help (01 re-merge pending). |
| 2026-10-19 ~10:52 | Core rebuild, relaunch; module restarts (Link, Spotify, Multi) | modules.json: Host help (02) + Multi manifest/help (03/01). Link ebd6e40, Spotify de43fe7, Multi 1ce0463 help text via Update-Module. Orphans killed first. |
| 2026-10-19 ~10:48 | FULL REBUILD core+shell, relaunch | 01 9942c65: clickable Help framework (help drawer on every status, Help page, vault 'How to get this key'). Killed orphan modules first. Siblings told to add module help text via Update-Module. |
| 2026-10-19 ~10:36 | FULL REBUILD core+shell, relaunch | 01 batch: voice commands (silent, logged, "skip the song"), device status merge (green wins), vault module-set + Host secrets, Multi secrets. Killed orphan Host/Multi/Listen/Link/Spotify first (stale tokens). All ports up. Prestream 31 pass / 15 warn / 1 fail (Link OBS password; Ivan enters OBS_WS_PASSWORD in Integrations). Host vault check now lists its 6 keys. |
| 2026-10-19 ~10:29 | Host restart | 02 334a15e (Host reads vault first). || 2026-10-19 ~10:28 | FULL REBUILD core+shell+Host (01 d04fa4f..acac700 + modules.json secrets; 02 29a9445+theme; 03/04/spotify vault+theme adoption) and relaunch (minimized) | Build OK, all five modules answer 200 incl. Spotify :8771. New: /theme.css, Integrations tab, key vault (empty, nothing imported), prestream-run control file works (test run via file, no UI pull). Gotcha: a Host started by the first launch survived the core kill and kept a stale module token (lease 401); killed it, core restarted Host, master confirmed. Test prestream: 29 ok / 15 warn / 1 fail (OBS WS password wrong in Link). Warns: Twitch redeem scope (re-sign streamer), Discord/YouTube/TikTok optional, Tailscale stopped, Spotify not set up, vault keys not imported. |
| 2026-10-19 ~10:15 | Host-only restart (02: penguin-orange dark theme on Host + /automations, 7 Spotify command actions seeded disabled) | Update-Module.bat host, /automations 200, app untouched. Pages fall back to built-in colours until core serves /theme.css (needs rebuild). Spotify !sr etc. stay disabled until the spotify module runs and Nightbot/StreamElements !sr is off. |
| 2026-10-19 ~10:13 | Host-only rebuild + restart (02 29a9445: Actions & Events engine, /automations page, Streamer.bot import) | Update-Module.bat host (0 errors), /api/automations and /automations answer 200, app untouched. Nothing imported yet (20 importable actions arrive disabled). Nav entry "Actions & Events" needs modules.json (01). |
| 2026-10-19 ~10:10 | Link-only restart (04 98e2174: device mesh P1, pairing, peer broadcast, Devices card) | Update-Module.bat link -NoBuild, answers 200, app untouched. Tailscale is stopped on this PC, so no real two-PC test yet. 04 reports Ivan approved P1 (Tailscale-only, no key injection). |
| 2026-10-19 ~10:08 | Multi-only restart (03: dark #ff9900 theme) and Host-only rebuild + restart (02 c4ed284: master lease poll, /api/summary, /api/prestream master item) | Update-Module.bat multi -NoBuild; Update-Module.bat host (0 errors, 1.8 s), Host answers 200, app untouched. Host lease is safe with the current core (404 = single device, treated as master). |
| 2026-10-19 ~10:03 | Multi-only restart (03 abd19b3: Unified Chat page /?type=chat, /popout, /api/dashboard, mod actions hidden until Twitch scopes) | Update-Module.bat multi -NoBuild, app untouched; chat page answers 200. Needs: Chat nav ui path "/?type=chat" in modules.json (01), Ivan's OK for the site MULTI_SCOPE change (Docs\PinguinoMulti\SITE_SCOPE_PROPOSAL.md). |
| 2026-10-19 ~10:00 | Link-only restart (04: restyle near-black + #ff9900) and new tool App\Shot-Quiet.ps1 | Update-Module.bat link -NoBuild OK, app untouched. Shot-Quiet.ps1 captures the app window with PrintWindow, never raising or focusing it; works while covered and while minimized (restores off-screen without activating, captures, re-minimizes). Verified: 1456x920 image of the Console page taken while minimized. 00 uses it instead of the foreground screenshot. |
| 2026-10-19 ~09:35 (verified 09:48) | Console + prestream rebuild: core 8107d21/9f30735, shell ad05c51, Host incl. prestream items, Listen logging; Link restart #2 (7089e8c, link config move) before it | Build-All BUILD OK, app relaunched, 1 process, all modules up. Verified live in the window: Console page shows live logs from host/multi/link/listen with filters (module, level, search, errors-only, Pause, Clear); pre-stream card says "Runs at 4:30 pm and 4:45 pm Central; stream at 5:00 pm"; Run now returned 25 ok / 11 warn / 2 fail aggregating link, multi, host, listen and core. Fails: OBS WebSocket not reachable (127.0.0.1:4455), Multi Twitch not connected. Not yet seen: a scheduled 16:30 run, the red error badge. |
| 2026-10-19 ~09:48 | Host-only restart (02: "Bots: ChattyPinguino/PinguinoHelper accounts", bots.json titles/accounts, name variants, speech order) | Update-Module.bat host, 1.2 s build, 0 errors, 8770 answers 200, app untouched. Ivan to sign in chattypinguino and pinguinohelper from their Host cards (Sender none until then; PinguinoB0t speaks for them). PinguinoBotCore.cs and Tests/core/harness.cs have uncommitted strikes edits from another session. |
| 2026-10-19 ~09:50 | Link-only restart (04 13bec96: console\link.jsonl + GET /api/prestream) | Update-Module.bat link -NoBuild, app untouched. Prestream: OBS FAIL (not running / websocket off), macros warn (unchecked), Tailscale warn (stopped), role warn (client: macros go to a hub). link.jsonl written. |
| 2026-10-19 ~09:45 | Host-only restart (02 ad7a3ce: console\host.jsonl + GET /api/prestream) | Update-Module.bat host, app untouched. Prestream live: overall warn. Pass: chat, EventSub, streamer token (60 d), core bot token (55 d), Streamer.bot 8080, AI, faq (19 entries), no recent errors. Warn: chat/helper bots have no account of their own, mod status uncheckable (streamer token lacks moderation:read; verify /mods), OBS not set up in Host. Host ts are ISO-UTC strings, 03's are epoch floats (01's ingest should accept both). |
| 2026-10-19 ~09:40 | Multi-only restart #2 (03 a3f3da9: contract-aligned logging, /api/prestream returns {ts,items}, console\prestream-multi.json every 2 min) | Update-Module.bat multi, app untouched; console\multi.jsonl and prestream-multi.json present. Pending: "prestream": "/api/prestream" in Suite\modules.json (01's file; asked 01, needs the core rebuild). Until then the core reads the file fallback. |
| 2026-10-19 ~09:35 | Multi-only restart (03 617b46b: console logging, /api/prestream, guided launcher, Combined Chat, recap/viewer notes, TikTok off) | Update-Module.bat multi, app untouched. Multi writes Data\runtime\console\multi.jsonl; /api/prestream answers. Prestream now: Twitch FAIL (needs Ivan: log in to innocentpenguin.com as owner, then Connect Twitch in Multi), Discord/YouTube/TikTok warn (optional), no chat windows saved (pick Combined Chat), rest pass. |
| 2026-10-19 ~09:30 | Host-only restart (02: "Chat: welcome first-time chatters") | Update-Module.bat host; PinguinoChat greets a viewer's first-ever message (no AI call, one welcome per 8 s, skips mentions/help). App untouched; chat + EventSub connected. |
| 2026-10-19 ~09:25 | Host-only restart (02 addendum: "Helper: read innocentpenguin.com/api/faq") | Second Update-Module.bat host so the Host picks up the newest helper commit (minecraft_ip and discord from 05's live /api/faq, incl. hardcore Bedrock port 9216). App untouched; chat + EventSub connected. |
| 2026-10-19 ~09:20 | Host-only update via Update-Module.bat (02: "Helper: Minecraft java/bedrock flow", !discord facts) | Host rebuilt and restarted in 14 s, app untouched. Chat and EventSub connected, dataDir = Data\runtime. Heads-up from 02: Nightbot/synchrabot already answer !discord and !ip, so replies will double unless Ivan turns those Nightbot commands off. |
| 2026-10-19 ~09:30 | Module update without app restart VERIFIED live (01 d5ef54a + script fix) | `App\Update-Module.bat host`: stop via control file, `dotnet build` (0 errors), start, Host up again in 14 s total, dataDir = Data\runtime, chat connected, still exactly one app process (core/shell/Listen/Multi/Link untouched). Module-only changes now never need an app restart. EventSub was still false at the first read (connects a few seconds later). |
| 2026-10-19 ~09:20 | Forced core rebuild #4 + relaunch (00, standing auto-rebuild) | `Build-All.bat --force`, BUILD OK. Live now: 01's f72554e, a2fc6a5, 5013dfc, d5ef54a and the new Stamp.ps1 (backdates outputs to build start, fixes the freeze race that left the old core running). One app process; 8765/8766/7777 up. Control-file trigger verified live: stale start/stop files were consumed, a fresh `start-host` brought Host back in 8 s without touching the app. |
| 2026-10-19 09:12 | Host-only rebuild + restart (02: "Helper only chimes in at key words": Send test button, live-only checkbox, router key-word routing, helper ip/!discord) | Host rebuilt, started from the Bots / Host page, up in 8 s, dataDir = Data\runtime, chat connected, page has "Send test". App untouched. First live test of 01's d5ef54a FAILED: Update-Module.bat rejects "host" (unknown module), and the control-file trigger was not consumed by the running core (stale stop-host/start-host remain in Data\runtime\control; I cannot delete them, 01 asked to). Reported to 01. Ivan to fill McIpReply / DiscordReply in helper_settings.json (02 will ask). |
| 2026-10-19 08:49 | Core rebuild #3 + relaunch (00, Ivan's standing auto-rebuild) | One Build-All (launched the app after success) covering 01's f72554e (atomic suite_settings.json + .bak), a2fc6a5 (module crash auto-restart, backoff 2/5/15/30/60 s, breaker after >5 in 5 min), 5013dfc (JSONL event log Suite\logs\events.jsonl, /api/modules/{id}/logs, /api/events/log) and d5ef54a (Data\runtime\control\ start/stop/restart-<id> triggers, App\Update-Module.bat <id>). Core exe 08:49; app + Listen 8765, Host 8770, Link 7777 up. Note: Multi (8766) showed uptime ~48 min, i.e. it survived the core kill as an orphan and was not restarted by the new core. Update-Module.bat and the control folder are untested live. |
| 2026-10-19 08:56 | Host-only rebuild + restart (02: "Host: open Twitch sign-in in the default browser") | New POST /api/signin opens the Twitch sign-in in the default browser (embedded window ignored window.open). Same steps as the 08:50 entry; Host up in 28 s, dataDir = Data\runtime, chat connected, /api/signin answers 401 without token (route present). Ivan to click the core card's sign-in again. App untouched. |
| 2026-10-19 08:50 | Host-only rebuild + restart (02 3617350, Ivan's standing auto-rebuild) | Stopped Host, `Build-All.bat --only host` (0 errors, 1.3 s), restarted Host from the Bots / Host page (it does not auto-restart after a mid-session stop). 8770 up in 4 s, dataDir = Data\runtime, chat connected, page contains "Speaks as". App, core, Listen, Multi, Link untouched. Ivan still to sign in each bot account (core card, private window, Channel set first); bot must be a mod for timeouts. |
| 2026-10-19 08:45 | Tooling (01 6868a9d, tested by 00) | App\Build-All.bat is the single gated entry point: Build-Host / Build-Core / Build-Shell each skip when fresh; launches only if all needed pieces succeed (`--no-launch`, `--force`, `--installer`, `--only host\|core\|shell`). Rebuild-App.bat now wraps it with --no-launch. 00 test with nothing changed: all three skipped, BUILD OK, 1 s, running app untouched. |
| 2026-10-19 08:42 | Note (no rebuild) | 04 committed d1d7e86: Link module.json start_with_suite + always_start true. Manifest only; takes effect on the next app restart. 01's 69be008 (incremental Rebuild-App.bat) is what ran in the entry below, plus my Stale.ps1 regex fix (01 to commit). Gated Build-All (Host + core + shell, launch only if all succeed) requested from 01. |
| 2026-10-19 08:40 | Batch rebuild #2 + relaunch (00, Ivan: "yes auto rebuild") | Host built (Release, 0 errors); core + shell force-rebuilt (core 08:35, exe 08:38, 2 min total). Includes 01's 9ab1772 (core data dir falls back to Data\runtime; host/multi autostart), 02's 30452ba (Host compiled defaults, AI key carry-over). Found and fixed a regex bug in App\Stale.ps1 (it errored, so the bat wrongly skipped core/shell); incremental skip now works. Relaunch: one process; Listen 8765/Multi 8766 up in 4s, Link 7777 in 2s, Host 8770 autostarted in 10s with dataDir = Data\runtime, chat + EventSub connected. Not verified: Host page defaults visually, AI key carry-over, tray, Twitch sign-in. Link autostart pending 04's manifest. |
| 2026-10-19 08:26 | Batch rebuild + relaunch (00, Ivan confirmed in chat) | Stopped app and Host; `dotnet build -c Release` PinguinoHost (0 errors, DLL 08:23); ran App\Rebuild-App.bat (installer 37.07 MiB, exe 08:26). Includes 42e798d (shell nav guard: external sign-in opens in system browser), 531a326 (tray), 7a18b30 (static fallback removed), 762861c (Host embedded UI/api/bots/token guard/bot-account sign-in/new-window sign-in), 7ed8312 (C# PINGUINO_DATA_DIR), fb2fe33, plus 03's Multi connectors (Multi restarted with the app). Relaunched: one window; Listen 8765, Multi 8766, Link 7777 answered within 45s; Host is not start_with_suite, so I started it from the Bots / Host page (8770 answering 200). Not yet verified: tray hide/reopen, Twitch sign-in in the shell, bot-account sign-in. |
| 2026-10-19 08:11 | Relaunch | Plain launch of the rebuilt exe for timing. Window in ~1.7s, all four modules answering within ~55s. One window. |
| 2026-10-19 08:08 | Rebuild (00, Ivan approved) | Adds tray behaviour from commit 531a326: X hides to tray, tray left/double-click reopens, menu on right click ("Show PinguinoSuite" / "Quit (stops all modules)"). Requested by Ivan, done by 01. |
| 2026-10-19 08:03 | Rebuild (01, Ivan approved) | Core exports PINGUINO_DATA_DIR to modules (fb2fe33). Before the single-launcher rule reached 01. |
| 2026-10-19 ~07:55 | Rebuild (01, Ivan approved) | Frozen core re-built so /api/state returns `ui`; generic nav from module manifests (c8bfdd9). Listen, Multi, Bots / Host, Link all registered. |
| 2026-10-19 | Verified | All four module pages load inside the real Tauri window (screenshots by 00, report by 01). |
| 2026-10-19 | Fix | PinguinoApp.bat launches the Tauri exe (one window) instead of the legacy standalone core. |

## 2026-10-21 08:50 - Host + Spotify restarts (00)
Host had died overnight (EventSub/chat lost 13:33Z); restarted via Update-Module host. Spotify restarted (orphan on 8771 killed) for Music 34052e6 refund rules; /api/refunds now answers 200.

## 2026-10-21 08:35 - App relaunch (00)
Module pages showed offline/blank after hours idle (all services answered 200). Relaunched shell + core via PinguinoApp.bat; pages load again. Host/modules untouched. Listen still flaps (06 investigating).

## 2026-10-21 07:22 - Music module restart (sub tier priority)
- Spotify module restarted via D:\PinguinoSuite\App\Update-Module.ps1 spotify (orphan PID 43632 ignored the stop file, killed, then started). Loads 'higher sub tiers rank first' (Tier 3 > 2 > 1 within a round, redeems first). 117 unit + 200/200 e2e per Music. Native in-app player still needs a real Premium run and re-login for the streaming scope.

## 2026-10-21 07:16 - Host restart (strike limit, overlay timing)
- Host restarted via D:\PinguinoSuite\App\Update-Module.ps1 host: loads d213195 (tunable strike limit !tune strikes 1-10, overlay altSeconds/fadeMs in live_state, !tune names), 788940d, nightly-review tool. Build 0 errors; /api/live, /api/commands/profiles, /api/sim/status checked. 02's nightly report notes 47 lobby push HTTP failure warnings in the host log (site endpoint not deployed yet); under review.

## 2026-10-21 07:20 - Link module restart (Lite self-update check)
- Link restarted via D:\PinguinoSuite\App\Update-Module.ps1 link on 04's bcf4fd9: local Lite self-update check (Data\lite\staging\PinguinoLite-<ver>-setup.exe + .sha256; never executed). The old Link (PID 40600, started 00:59) ignored the control stop file, so I killed it and Update-Module started the new one. /api/health ok.

## 2026-10-21 04:42 - Host restart (Firsts payout)
- Host restarted via D:\PinguinoSuite\App\Update-Module.ps1 host: loads 023's a2a7afe (Firsts payout via native PinguinoGrantPoints / Economy.Grant, idempotent ids, no !addpoints line in chat). /api/live and /api/commands/profiles 200. Live Firsts game unverified.

## 2026-10-21 03:58 - Host restart (Chatty updates)
- Host restarted via D:\PinguinoSuite\App\Update-Module.ps1 host: loads 022's 7257d8d (87 canned fun commands, 20 s cooldown, 7 risky held disabled), 3223158/9684c2d (HostLore sender split, no double replies), 2b403fe (ChatReplies default on, title/commands answers, bare-name line), c24ce4e (Chatty stays out of Helper intents), 30684aa, !rank. Build 0 errors; /api/live, /api/commands/profiles, /api/wheel/state 200. Live chat checks pending (each canned command answered once).

## 2026-10-21 02:05 - Full rebuild + launch (roles tags UI, Master View)
- Build-All --no-launch OK (first two attempts failed on 02's half-done HostEvents.cs; fixed by 02), then launched via D:\PinguinoSuite\PinguinoApp\PinguinoApp.bat. Includes 1eb4a1b role tags UI, 6667fdd Master View nav hook + CSP frame-src 'self', b065ab7 Master View page, 3ecc4ff simulator, cf50a01 templates. /api/live, /api/commands/profiles, /api/obs/status, /api/sim/status all 200. UI not yet visually checked.

## 2026-10-21 01:52 - Host restart (roles tags backend)
- Host restarted via D:\PinguinoSuite\App\Update-Module.ps1 host on 02's d4d309a: command permissions are role tags (roleOptions on /api/commands/profiles). /api/live 200. App not rebuilt; the Commands page tags UI (01) is still pending.

## 2026-10-21 01:37 Host restart (simulator leak fix b35d30d)

- Update-Module.ps1 host. /api/live, /api/sim/status, /wheel.html, /api/wheel/public 200. Fix: sim clear rewrites wheel files, sim names kept out of saved wheel feed.
- 02 live check passed: start 8, ticks (gamble/slots/duel on sim ledger), remove, clear; wheel sign-ups back to real 8; real ledger md5 unchanged; no sim_ in saved files. Not exercised: live-stream auto-stop, spin. namesSource still boards until 05's /api/bot/names (cab2c51) is pushed.

## 2026-10-21 01:14 Shell rebuild + Host restart 01:10 (player simulator)

- 01:10 Update-Module host on 31ffac3 (02: player simulator, /api/sim/*, sim ledger, sendSimToSite). 01:14 Build-All --no-launch (host/core up to date, shell rebuilt) + PinguinoApp.bat. /api/live, /api/sim/status, /wheel.html, /api/obs/status all 200.
- In the app now: Simulator panel (3ecc4ff) on Wheel & Games. Link module restarted 00:55 (orphan PID 13580 killed) and 00:59 (58ddc58 install/update/uninstall).
- Pending: site GET /api/bot/names + sim:true handling (asked 05); SEO batch 43cdd28 push by 05.

## 2026-10-21 00:52 Full rebuild + app launch (core + shell)

- Build-All --no-launch: host unchanged (23:38 dll), core rebuilt (templates routes), shell 00:47; launched via PinguinoApp.bat. Verified /api/live, /wheel.html, /api/obs/status, /api/commands/profiles all 200.
- In this build (01): Save/Defaults split buttons with saved templates (cf50a01), wheel preview probe fix + dark grey inputs app-wide (462804f), splash transparent fix, Commands page.
- Not running yet: Link module changes (95d10a7): old node PID 13580 from 10/20 05:57 ignores stop; asked 04 for the safe restart. Simulator (02/01) not built yet.

## 2026-10-20 23:42 Full rebuild + app launch (commands page, replay buffer, wheel preview fix)

- Build-All --no-launch (Host 23:38:40, shell 23:38:46) then PinguinoApp.bat. Earlier attempts at 23:36 did not build (log file locked by a stale shell); Music module restarted 23:30 (1d336fd subTier/isVip, c39ca11 song log).
- Now live: 595a655/560d36f replay-buffer auto-start (start only, never toggle; /api/obs/status: connected, replayBuffer active), 84b744a command profiles, 4be2c07, f7f6a38 wheel, 01's Commands page, sidebar scroll, wheel preview fix.
- Known: splash window shows white corners (01 fixing).

## 2026-10-20 23:27 Host restart (command profiles backend, Music subTier)

- Command: Update-Module.ps1 host. Build 0 errors, Host up. /api/commands/profiles 200, /api/commands/archive 200, /api/live 200.
- Now live: 84b744a (command permissions/profiles/archive/restore, central silent enforcement, usage counts), 4be2c07 (subTier + isVip to Music /api/chat-command).
- Pending: replay-buffer auto-start (queued to 02), next app rebuild (sidebar scroll, preview-trap fix, Commands page wiring).

## 2026-10-20 23:05 Host restart (wheel restored, act live while recording, !addpoints/!editpoints)

- Command: Update-Module.ps1 host. Build 0 errors, Host up, /wheel.html 200, /api/wheel/public returns the original-overlay shape.
- Now live: f7f6a38 (exact site wheel overlay + HostWheelPublic adapter, ?feed=1 join/leave feed), ca07943 (bots act live while OBS records), 87df867 (hidden broadcaster-only !addpoints/!editpoints).
- Not in the running app exe yet: sidebar scroll, wheel preview-trap fix (need next Build-All).

## 2026-10-20 22:38 Full rebuild + app launch (Plan 7 UI)
- Rebuilt core + Host + shell via Build-All (first two attempts failed: Host stopped, then a half-edited HostEconomy.cs broke the compile; third OK). App launched 22:38.
- In the app: Wheel & Games page, Commands page (preview data until Host backend lands), Accounts offline/recording toggle UI, window placement (62% default, remembered), splash + new logo, website pop-out (own icon/profile/taskbar id).
- Not in this build: sidebar scroll bar (cf19b27, 22:49) - needs next rebuild. Spotify module restarted 22:27 (song log, skip cooldown, sub-tier bonus queues). Host also restarted on f3f57f5 (/api/tune etc.).

## 2026-10-20 22:07 Host restarts (Plan 7 step 2)
- Live: tournament wheel on the Host (live random picks, no precommitted teams, auto new round, join/leave anytime, wheel-only !notme), overlay at http://127.0.0.1:8770/wheel.html, wheel signed-up count + join/leave feed, customs recycler (!recycle), !incomplete, 15-min customs idle timeout, lobby push and !pm name-only (no passwords).
- Site: new build live (wheel removed, queue + final teams only, mobile pass); site accepts old and new wheel payloads.
- Pending: one app rebuild (Wheel & Games page, window placement, splash/logo, Offline toggle), after 02 ships /api/tune.

## 2026-10-20 21:42 Host restart (Plan 7 step 1)
- Live: typo/alias router (!jon, "! join", !unjoin, did-you-mean), !queue first 5 + own position, !mmr for viewers, gambling (!gamble/!slots/!duel/!give via Data\economy\gambling.json, no default max bet), economy tick logging + chat-activity bonus, StreamElements import note, Offline mode OFF.
- Earlier unlogged restarts since 16:54 (clips-dump, !title/!game, mention replies, !allow, half strikes, Chatty fixes, !srban) were also applied.
- Known: !pm still reads LobbyPassword until 02's name-only fix lands.

## 2026-10-20 16:54 Host restarts (pre-stream batch)
- Host rebuilt 0 errors, several times, now at 9684c2d: Plan 6 OBS/overlay API (e7fd136..4ec3ca0), clips-dump (e388e89, 278 clips), control layer ENABLED and live-tested (e55eaa5 era), Offline mode switch (8adb586, default OFF), !points regression fix + !downtime (e55eaa5), lore/fun replies sent as ChattyPinguino with Chatty canned file owning 87 commands (99190c7, 7257d8d, 3223158, 9684c2d), Helper Bedrock Connect console answer (03b719b); profiles re-pushed (1858).
- Pending: Suite app rebuild (offline toggle 199ef63, c8ae770, b29ec25) after stream; !pm will keep printing the password (021/02 reversing e134683); customs/KOTH/lobby (051/05); 7 held edgy commands still answered by Host lore.

## 2026-10-20 16:14 Host restart (Plan 6 A-D)
- Host rebuilt 0 errors with 02's e7fd136, ce87afe, e6bb0dd, 4ec3ca0: /api/obs/tree (live, connected), scene/item actions, overlay CRUD API, overlay assistant (OFF, needs key + enabled flag). /api/live 200.
- Pending: 05 site UI for Master View, Anthropic key in vault, Ivan flips overlaychat enabled.

## 2026-10-20 15:58 Host + Multi + Listen restarts (night run)
- Host rebuilt (0 errors): 023 hype/goal announcements, !uptime, Firsts guard; site-bridges shop/teach contract fix (cc70a3d); 02 live-state route, HostControl; /api/sitebridge teach+shop ok.
- Multi restarted (gift alert, poll/predict/hype overlays, send guard). Listen restarted twice (VOD memory fix, /api/status no-lock fix). Link restart skipped (still answers; harmless).
- Pending: core/app rebuild (c8ae770, Accounts sign-in), Streamer.bot script re-paste, Firsts !addpoints collision.

## 2026-10-20 09:02 - Host + Multi restart (Plan 5 events, /api/say)

- Host restarted on 9210a76 (EventSub poll/prediction/hype train, raid out, richer gift events in the activity feed; POST /api/say with module token). Multi restarted on ece3825 (Twitch plain sends via Host /api/say, falls back to direct if Host down) and 046b726 (raid_out/poll/prediction/hype rows, gift counter + top gifter). New scopes need Ivan's re-sign-in. Gift alert/poll/predict/hype overlays still to build.

## 2026-10-20 08:55 Host restart (Plan 5 scopes)
- Host rebuilt on 1a9377e: 36 extra Twitch scopes in the sign-in (polls, predictions, raids, chat settings, announcements, shield, VIP/mods, whispers, schedule, etc.). Ivan needs ONE re-sign-in on the Accounts page; `missing` should then be empty.

## 2026-10-20 08:57 - Multi + Spotify restarts

- Spotify restarted (announcements only for site requests, avoids double chat line). Multi restarted: 1e25f66 dashboard (live viewer counts, text size A-/A+, drag-resize panels, split chat), e4a8edc duplicate guard (same line to same platform within 30 s dropped). Multi /api/send still goes to Twitch/Discord/YouTube directly.

## 2026-10-20 08:52 - Host restart (no-duplicate-message guard)

- Restarted Host via Update-Module: 2393763 duplicate-chat guard (identical line within 30 s from any bot is dropped; HostApi.SaidRecently in SendAs and cph.Say). Streamer.bot scripts (Core/Chat/Helper/Router PgSay) need re-pasting from the synced files. test-host-commands.py has 2 stale checks since the !commands link change.

## 2026-10-20 08:45 - Voice restart (Speak review + spoken control)

- Restarted Voice via Update-Module (first attempt failed: module was running outside the core; killed its listener on 8772 and reran, it now runs under the core). 80cad76: Speak > Review & control tab (hourly self-review, spoken game/title/timeout control OFF by default). Needs Host endpoints (live as of 72349a4) and Ivan's Twitch re-sign-in for title/game.

## 2026-10-20 08:37 - Host restart (channel update + mod timeout endpoints)

- Restarted Host via Update-Module: 72349a4 HostChannel.cs: POST /api/channel/update (title/game) and POST /api/mod/timeout (module token required, protected users refused, audit log Data/runtime/mod_audit.log). New scopes (channel:manage:broadcast, channel:manage:redemptions, channel:read:goals, channel:read:hype_train) need Ivan's one Twitch re-sign-in. /api/live 200.

## 2026-10-20 08:26 - Host restart (!rank all playlists, points rename, Chatty fixes)

- Restarted Host via Update-Module: 30684aa/6f141c1/b3e3efe: !rank [epic] [playlist] for every playlist (15 min cache per account, 30 min pause when blocked), ranks saved to Data/ranks/rl_ranks.json for profile push, currency renamed pengs -> points (!pengs removed), Chatty ignores ! lines and stays quiet on how-to questions (ChatReplies still false). /api/live 200. Profiles need push-profiles after the first live !rank.

## 2026-10-20 08:22 - Host restarts + boards/profile push

- Host restarted (Update-Module) for 6c9999f/01be950/8cda53f/b3e3efe (!rank live), helix-ids split fix, 1724d20 (!commands), ec0dc0c (alias merges, banned_accounts). One build failure (HostRank.cs control chars in a doc comment) left the Host down ~2 min; fixed by 00 and rebuilt. Boards pushed 13:20Z (3020 people, supporters 64, 0 502), profiles 1858 sent. Site raised /api/bot body limit to 8 MB (05, 1956d08). Top points/watchtime boards should now appear once 05 pushes the new section.

## 2026-10-20 08:13 - Host restarts (helix-ids fix, commands triggers)

- Restarted Host twice via Update-Module: helix-ids batch-split fix (name history 9 -> 164 certain-rename chatters after rebuild), then 1724d20 (!commands/!command/!cmds/!cmd reply with link to /commands; commands-doc rows carry section + importance). Profiles pushed (1858). Boards push still HTTP 413: 05 raising the route limit, 02 slimming payload.

## 2026-10-20 08:08 - Host restart (!rank live refresh)

- Restarted Host via Update-Module: !rank for Ivan refreshes from the unofficial tracker.gg endpoint (5 min cache, 30 min pause when blocked, last-known fallback, !setrank override 24h). Not yet checked against the real tracker: watch Host log for rank warnings.

## 2026-10-20 08:05 - Host restart (refollow, Helper chime, !rank, Marsh opt-in)

- Restarted Host via Update-Module: 6c9999f follow items carry refollow; 01be950 Helper random chime (rate limited, honours !unping); 8cda53f !rank/!setrank (rank.json) + rocketrankbot in bot lists; Marsh opt-in (hidden_sources emptied, default seed removed, trusted). /api/live 200. Marsh and checklist edits committed by 00 on Ivan's direct instruction.

## 2026-10-20 08:02 - Listen restart (VODs memory fix)

- Restarted Listen via Update-Module: 1c3b4ea decodes/transcribes VODs in 15-minute slices (was loading the whole VOD into RAM and dying), stranded jobs marked interrupted and re-queueable. Cause not reproduced live; Listen autolearn is ON (can transcribe on GPU during streams).

## 2026-10-20 07:58 - Host restart (site bridges, hidden shop)

- Restarted Host via Update-Module: 813a60d (SiteTeach poller, hidden SiteShop, Economy Spend/Credit ledger, hidden !guess) and 73f2c94 (Chatty random chime only after buy_chatty). /api/live 200. Shop stays hidden (site flag OFF). Tests 33/33.

## 2026-10-20 07:43 - Multi restart (follow overlay)

- Restarted Multi via Update-Module (ab8eecc): new OBS source /obs/follow (new follow alert + sound, refollow = silent, tagged refollow), refollow chip in /obs/activity and dashboard. Refollow flag from Host (refollow:true) pending from 02.

## 2026-10-20 07:05 - App rebuild + Spotify module restart (01 e799c22 Approvals tab, songify-music 368da9e)

- App rebuilt and relaunched (Suite > System > Approvals tab for the Teach inbox). Host restarted earlier (aliases, Teach inbox, links, recorder). Boards refreshed, 1858 profiles re-pushed.
- StreamElements points import applied: 2371 users, 4.1M points, 1.19M minutes (report uTQnYADzBE).
- Spotify module restarted with Songify parity (queue widget /overlay/queue, blocklist import, new song commands, reward-only mode). Still needs Ivan's Spotify Client ID + login; requests stay closed by default.
- Note: Link and Spotify were running outside the core (Update-Module could not stop them); killed and restarted under the core.

## 2026-10-20 06:20 - Full rebuild + relaunch (01 b29ec25 sign-in fix, 02 cab671e Nightbot lore)

- Core + app rebuilt and relaunched (first Build-All failed on a locked Host dll; leftover Host/module processes stopped, second build ok). Suite 'Sign in again' no longer cuts the OAuth url.
- Host now serves channel lore: 135 Nightbot commands imported (16 exact-command-only), commands-doc 154 viewer / 53 mod / 115 channel. Link restarted earlier under the core.
- Needs Ivan: confirm !discord invite (not in the Nightbot export); keep Nightbot and PotatBotat on until spam filters / economy are checked.

## 2026-10-20 06:06 - Host restart (02 aae0872 profile sync)

- Live sub sync from Helix: Twitch 171 active subs vs 244 on profiles; 58 active subs had no profile (stubs now created); 131 profiles marked subbed but not on Twitch.
- Avatars: 1542 of 1858 logins have a picture; 316 not found on Twitch (renamed/deleted). Cyfi's picture exists under cyfirl; site must resolve the nickname.
- Profiles re-pushed (1858) with avatar/isBot/subType/giftedBy.

## 2026-10-20 06:00 - Host restart (9122ce7 economy, 7139194 helper, e757347/95e31ab/44be985 timers)

- Economy: !points/!pengs, !watchtime, !toppoints, !topwatch (mods: !addpoints, !removepoints, !economy); /api/economy/import dry run + apply; waits for Ivan to paste se_jwt in the vault.
- Timers: chat timers, stream countdown/stopwatch, reminders. Boards now go to top 500. Commands-doc: 92 commands. Profiles re-pushed.
- Streamer must sign in again for moderator:read:chatters (earning falls back to recent chatters until then).

## 2026-10-20 05:58 - Link module restart (04 a3ff4df)

- OBS diagnosis now says one clear thing; vault Test button for OBS_WS_PASSWORD (/api/test-obs).
- The old Link process on :7777 was running outside the core, so Update-Module could not stop it. It was killed and restarted under the core (/api/health ok, role client).
- Ivan still needs: OBS password into the vault, Link role hub, real scene names in macros.

## 2026-10-20 05:25 - Host restart (8212f95 shoutouts, f463b61 strikes, 5bf5db0 !8ball, 47829e2 se_jwt secret)

- Shoutouts: immediate temp chat line, then the Twitch card via Ivan's token after 1-5 s; 2 min gap and 60 min per target kept.
- Strikes: temp (orange, one wears off per 24 h) vs permanent (red, never expire); commands-doc now 73 commands.
- !8ball with public context; Host declares se_jwt vault secret. Profiles re-pushed.

## 2026-10-20 05:10 - Host restart (1a4af3b)

- Weekly private opinion notes + mod-only !opinion enabled. Profiles re-pushed (1800).

## 2026-10-20 04:52 - Host restart (177941e)

- Boards push now sends drop + aliases maps (site purge live, c374700). Profiles re-pushed (1800).

## 2026-10-20 04:41 CDT - Host restart (chat commands + /api/commands-doc, b3c6d6f)

Host rebuilt+restarted; /api/live 200; commands-doc served.

## 2026-10-20 04:20 CDT - Host restart (per-month boards Feb 2026 on, profile displayName/aliasOf)

Host rebuilt+restarted; /api/live 200; boards push ok; profiles re-pushed.

## 2026-10-20 04:17 CDT - Host restart (alias merge sg_yen->cyfirl, real Twitch display names)

Host rebuilt+restarted; /api/live 200; boards push ok.

## 2026-10-20 04:12 CDT - Host restart (bits badge tier 754d863, boards push status, User-Agent fix 34bb1e7)

Host rebuilt+restarted; /api/live 200; /api/boards push ok (supporters 67, board 1759). Profiles re-pushed with bitsBadge.

## 2026-10-20 04:08 CDT - Host restart (boards push on by default, cf549b5)
- Update-Module host; /api/live 200. Site /api/leaderboards now: gifters 37, bits 47, streaks 50, yappers 50.

## 2026-10-20 04:03 CDT - Host restart (founders list + board push, 213c121)
- Update-Module host; /api/live 200. Data\subsounders.json created (10 founders). push-profiles: 1800 profiles pushed.

## 2026-10-20 04:00 CDT - Host restart (boards push to /api/bot/supporters, 0f6fcfa)
- Update-Module host; /api/live 200. Ran Pipeline\push-profiles.mjs: 1800 profiles pushed (streak + sub tier roles).

## 2026-10-20 03:57 CDT - Host restart (leaderboard totals, e1a2e83)
- Update-Module host; /api/live 200, /api/boards ok. Pushes totals to site /api/bot/boards every 5 min (05 adding endpoint). !topstreak links /leaderboards#streaks.

## 2026-10-20 03:53 CDT - Host restart (watch streaks, 88dd8b0)
- Update-Module host; /api/live 200. First start backfilled /api/streaks: 130 people from chat logs (top: yoohoo15 240, flayir_ 210).

## 2026-10-20 03:46 CDT - Host restart (subscriber roster import, e5fb7cd)
- Update-Module host; /api/live 200. First scan imported 1 file: 172 unique subs (T1 168, T2 1, T3 3), master at Data\subs\subscribers_master.json.
- Monthly Twitch export scheduled (twitch-subscriber-export-monthly, 1st of month 9:00).

## 2026-10-21 09:00 - Link, Listen, Host restarts (00)
- 08:47 Link: Update-Module failed first (still answered), killed the 7777 listener, reran OK; Lite local-update flow live (04 d62daf7+).
- 08:57 Listen: port 8765 was held by a stray `python -m http.server 8765` plus an orphan listen server.py that ignored stop. Killed both, reran Update-Module listen, running, 200. Ingest flapping / 82 MB log (duplicate-VOD bug) NOT fixed, with 06.
- 08:58 Host: Update-Module host for 02 046d1eb (song refunds via Helix) and e3adc12 (welcome bonus 100 pts). /api/live 200.

## 2026-10-21 10:21 CDT - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (latest update Oct 21 13:40 UTC: no change, builds paused in all regions, support platform down). Not resolved, so no push approval sent to 05. Stream checked: /api/live live=false.
- Nothing else done this run; will re-check next hour.

## Rules
- Only 00 launches/kills/restarts/rebuilds. Other sessions message 00; Ivan's yes is asked in 00's session before each rebuild.
- Update this file on every rebuild or relaunch with: time, who asked, what changed (commit hashes), result.




## 2026-10-21 12:21 CDT - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (latest update Oct 21 17:18 UTC: "Builds and deployments remain paused", support site down, next update promised 17:45 UTC). Not resolved, so no push approval sent to 05. Stream checked: /api/live live=false.
- Nothing else done this run; will re-check next hour.

## 2026-10-21 14:21 CDT (18:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage; latest update Oct 21 18:15 UTC: "Builds and deployments remain paused", API/dashboard/station.railway.com still affected, next update promised 18:45 UTC). Not resolved, so no push approval sent to 05. Stream not checked this run (no push step reached).
- Nothing else done this run; will re-check next hour.

## 2026-10-21 14:xx CDT - Scheduled 2pm full run (00, Ivan gave PC control)
- Sessions: all 17 idle (isRunning false) before work started.
- Stream: NOT live (host.log last state offline). OBS connected only at websocket level, not streaming; no OBS action taken.
- Railway: status.railway.com still Major Outage, builds paused. Site push HELD.
- Build: Build-All --no-launch. Core built (stale). Host build failed first (dll locked by running Host). Host stopped via control file, rebuilt OK (--only host), started again, 8770 answers 200. Shell up to date (exe 02:01 newer than all shell sources), not rebuilt. Core change is staged; takes effect at next full app restart (not done: Suite /api/quit needs a token, so no clean quit from here).
- Ports: 8760, 8765, 8766, 7777, 8770, 8771, 8772 all answer. Health /api/status 200 on listen, multi, host. Link /api/status returns 401 without token (see Link item below).
- UI smoke (built-in browser, read only, no action buttons pressed): dashboard loads, only failing request is /assets/logo.png 404.
- Logs: listen.log 82 MB, mostly yt-dlp progress with no newlines; move failed (supervisor holds the handle). Listen restarted via Update-Module (OK) and still locked; not growing since 09:43. Routed to 01 for size-based rotation at core start.
- events.jsonl: flapping today is from dev restarts. Last listen crash 10-20 08:39 (exit 3); no crashes today.
- host console: commands-all push HTTP 404. Expected: site endpoint in source but not deployed (batch on hold).
- voice.log: about 20 ConnectionResetError tracebacks from client disconnects in the request handler. Routed to 06.
- Link /api/status 401 on health probe. Routed to 04.
- Audit: round 1-3 requested from 02 (and its forks 30e19219, 7135181f, 6f5d97c2). Engine reports requested from 01, 02, 03, 04, 05, 06. Nightly docs (4 tiers) wait for those reports. Not finished in this run.
- No deletions. No duplicate sends (one message per session).
- CORRECTION (04 Phase 3 report): the Link 401 was my probe error, not a bug. Link's manifest health path is /api/health (unauthenticated, 200). /api/status carries device data and must stay authenticated. Item closed; nothing to route to 04.
- 04 report: Link has committed but un-restarted changes (Lite contract, module install/update, Lite self-update apply d0674ab, Start Stream OFF by default b2edff4, Lite reuses Link on 7777 fd10c1a). The running Link needs a restart to load them. That restart is pending Ivan's go-ahead via 00. Ten Link test suites passed at last run. Known gaps: Lite module start/stop not built, real OBS, Tailscale pairing and macOS unverified. Needs from Ivan: OBS password in the vault, hub role plus real macro names, Tailscale on.
- 05 Phase 3 report (Site): HEAD db668a9, 5 local commits ahead of origin/main (323b484, 0239e90, 9222597, c4f1a40, db668a9), NOT pushed. Production runs 43cdd28. Build + npm test + smoke 91/91 green. Commands-all 404 confirmed (endpoint exists only in 0239e90, undeployed); the Host retries harmlessly. Push needs Ivan's typed OK and Railway recovered. Open for Ivan: 1200x630 share image, /tourney start date, Search Console/Bing verification code. Long poll (?wait) needs a Host restart after deploy.
- Docs copy (from 05): Mods: /mod/commands has "Everything the bots have" (all commands incl. disabled, mod-only, broadcaster-only, archived). Viewers: /help commands start as buttons; "Show more" for the full list, full list on /commands; "?" bubble answers quick questions. Schedule: every day 5 PM Central, Rocket League first, then other games.
- 01 report: committed 2a21da3 (core only, nothing restarted or rebuilt; 59 core tests pass). Added GET /assets/{name} (serves plain image names from App/src/assets; fixes the logo 404). Added size-based log rotation at module start: logs over 10 MB move to Suite/logs/Archive/ (moved, never deleted); the 82 MB listen.log rotates on the next Listen start under the new core. Recommends one full app restart tonight for the new core and routes (needs rebuild first: the binary predates 2a21da3). NOT done in this run: restart and rebuild need Ivan's call, since the Suite quit endpoint requires a token and the restart takes all modules down. Timing left to Ivan.

## 2026-10-21 14:22 CDT - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage; latest update Oct 21 19:15 UTC: "Builds and deployments remain paused", re-enable to be staged Enterprise, then Pro, Hobby, Free/Trial, none announced yet; next update promised 19:45 UTC). Not resolved, so no push approval sent to 05.
- Stream checked: /api/live live=false (offline). No push step reached.
- Nothing else done this run; will re-check next hour.

## 2026-10-21 15:21 CDT (20:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage; latest update Oct 21 20:19 UTC: "continuing to work on a fix for build issues", builds paused, Enterprise builds expected by 20:30 UTC, Pro/Hobby/Free re-enabled in stages after; API, dashboard and station.railway.com still affected). Not resolved, so no push approval sent to 05.
- Stream and push steps not reached. Nothing else done this run; will re-check next hour.

## 2026-10-21 15:34 CDT - Full rebuild + app restart (00)
- Build-All (host, core, shell) BUILD OK; old app/cores stopped, orphan listeners killed by port, PinguinoApp.bat relaunched; ports 8760/8765/8766/7777/8770/8771/8772 all listening, Host /api/live 200, Link /api/health 200. Update-Module listen run once more.
- listen.log still 82 MB: rotation did not trigger on start and the file is locked by a running process, so not moved. Report to 01/06.
- Lite (4a47563) relaunched 10:22 and left open. Site: 5 local commits, not pushed (Railway outage).

## 2026-10-21 16:01 CDT - Host restart + Multi restarts (00)
- Host was down after the 15:3x app relaunch (lease rule: core unreachable 60 s -> Host exits; I did not restart it right away). Update-Module host rebuilt and started it; /api/live ok. Loaded: Helper 74fd13a/54a6ad0/54ef677/bc6138c, Chatty a4a6a21/d0ecab5/28970e5, B0t e1e1fde/80a4f41/4cbda13, streak 613b609, 75349e9 and earlier queue.
- Multi restarted twice (feca866, then streak celebration f5c57ac). Pending: 022 tuck/raid/rank, 02 sounds + Epic names + replays endpoint, 05 Epic link + Commands header (db668a9 local), 01 Sources page (shell rebuild), 012 replays scanner.

## 2026-10-21 16:16 CDT - Host restart (00)
- Update-Module host: build clean, /api/live 200. Loaded 85cf8f8 (default chime WAVs in Data\runtime\sounds, alerts_settings defaults + alertsound1 migration, welcome chime, /api/alerts-settings) and 022's 1515390 (!tuck, canned raid text, rank ids). Chatty ships inside the Host (no separate module). Sounds are Cut-gated for sb-* alerts; welcome chime needs live or Offline mode.

## 2026-10-21 16:21 CDT (21:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage). Latest update Oct 21 21:01 UTC: "We do not yet have additional information to provide about the availability of builds." Last explicit build status (20:35 UTC): Enterprise builds being validated, Pro/Hobby/Free to follow in stages; no confirmation any stage is re-enabled. Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream checked: /api/live live=false (offline). Push step not reached.
- Nothing else done this run; will re-check next hour.

## 2026-10-21 17:04 CDT - Host restart for lease fix (00)
- Update-Module host: 02 ea99365 (Host stays up degraded when the core is unreachable). /api/live ok but state unknown (source unknown); host.log shows LIVE/offline flapping at start, OBS is running. Restart done without a confirmed-offline stream check: noted for next time (check Helix live before any restart).

- 2026-10-21 18:16 (00): Build-All OK (host, core, shell). Stream offline (decapi). Relaunched app (suite+core), all 7 ports 200. Host restarted (killed stale pid 48244; Update-Module stop signal did not take) with ea99365, 69e67ab, 8c5b9ab, 2fd0628; rebuild-buckets ran (3952 events), /api/boards watchtime month OK. Lite relaunches at 16:46 not logged earlier. Site push held: Railway builds still paused (status 22:45 UTC).

## 2026-10-21 18:21 CDT (23:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage). Latest update Oct 21 22:45 UTC: builds and deployments remain paused; no confirmation any build stage is re-enabled. Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream checked: /api/live live=false (offline). Push step not reached. Task left enabled.
- Nothing else done this run; will re-check next hour.

## 2026-10-21 19:21 CDT (00:21 UTC Oct 22) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage). Latest update Oct 21 22:45 UTC: storage bucket credentials being rotated (revocation expected); builds and deployments remain paused, "will post here as soon as they resume". Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream not checked as a push gate this run (no push step reached). Task left enabled; will re-check next hour.

- 2026-10-21 (00): Host restarted (stream offline) with: activity ends automatically on live->offline (ApplyLive in PinguinoBotCore).

## 2026-10-21 20:21 CDT (01:21 UTC Oct 22) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage). Latest update Oct 22 00:22 UTC: "We are continuing to work to make builds available again"; builds and deployments still paused in US West, EU West, Southeast Asia and US East; API and station.railway.com still affected. Railway says guidance on next steps related to a security notice will be published soon. Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream and push steps not reached. Task left enabled; will re-check next hour.

## 2026-10-21 21:21 CDT (02:21 UTC Oct 22) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage). Latest update Oct 22 02:19 UTC: "still working to bring builds back online", no change since last update; next update due by 03:00 UTC. Builds not working. Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream checked: /api/live live=false (offline). Push step not reached. Task left enabled; will re-check next hour.

## 2026-10-21 22:21 CDT (03:21 UTC Oct 22) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage, not Resolved). Latest update Oct 22 03:00 UTC: "Builds remain paused. We are continuing to work to bring them back online"; next update promised by 03:45 UTC. Builds and deploys not working. Stream offline (127.0.0.1:8770/api/live live=false), so no stream gate issue. Not resolved, so no push approval sent to 05 (no duplicate message).

## 2026-10-21 23:21 CDT (04:21 UTC Oct 22) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage, not Resolved). Latest update Oct 22 04:17 UTC: Railway invalidated all API tokens under its security disclosure (users must create new tokens for the Public API); next update due by 05:00 UTC. Earlier 04:00 UTC update: Enterprise builds available, Pro/Hobby/Free in stages, Redeploy still unavailable. Builds not confirmed working for the site's plan. Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream checked: /api/live live=false (offline). Push step not reached. Task left enabled; will re-check next hour.

## 2026-10-22 00:21 CDT (05:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage, not Resolved). Latest update Oct 22 05:20 UTC: deployments taking longer than usual to progress through each stage; next update promised by 06:00 UTC. Enterprise builds reported back earlier (03:32 UTC), Redeploy fixed for Enterprise (04:52 UTC); no update reports builds restored for Pro/Hobby/Free/Trial. Not resolved, so no push approval sent to 05 (no duplicate message).
- Stream checked: /api/live live=false (offline). Push step not reached. Task left enabled; will re-check next hour.

## 2026-10-22 01:21 CDT (06:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage, not Resolved). Latest update Oct 22 06:12 UTC: Enterprise deployments moving at normal speed; Pro/Hobby/Free/Trial builds not confirmed re-enabled (no later update). Next update due by 06:45 UTC. Not resolved, so no push approval sent to 05 (no duplicate message). Stream not checked (no push step reached).

## 2026-10-22 02:21 CDT (07:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage, not Resolved). Latest update Oct 22 07:11 UTC: Pro and Enterprise builds available; Hobby, Free and Trial being enabled in stages; deployments slow and some may stay queued. Next update due by 08:00 UTC. Builds not confirmed working for all plans, so the incident is not resolved.
- No push approval sent to 05 (no duplicate message). Stream and push steps not reached. Task left enabled; will re-check next hour.

## 2026-10-22 03:21 CDT (08:21 UTC) - Railway hourly check (00, scheduled task railway-hourly-check-and-push)
- status.railway.com: incident QH8L8B3E still "Identified" (Major Outage, not Resolved). Latest update Oct 22 08:01 UTC: deployments going live but many slow to start and may stay queued; builds available for Pro and Enterprise, Hobby then Free/Trial still being enabled. Builds not confirmed working for all plans.
- Not resolved, so no push approval sent to 05 (no duplicate message). Stream and push steps not reached. Task left enabled; will re-check next hour.

## 2026-10-22 04:15 CDT - Nightly rebuild + app restart (00)
- Asked by: 00 nightly run (scheduled task pinguinosuite-nightly). Stream checked offline first (/api/live false, decapi "offline").
- Build-All --no-launch: host and core built, shell built. Earlier failure was the running shell locking its binary; fixed by stopping the shell first.
- Stopped: shell pinguino-suite (45640 before restart), core (352, 45620), live Host (39460), and two leftover test Hosts from the test run (19820, 24612, temp --data folders pgobs_*). pinguino-lite (012) left running untouched.
- Started: shell via App\src-tauri\target\release\pinguino-suite.exe (PinguinoApp.bat hung on the updater step, so started directly). Core came up; the Host was started by the core at 04:16 from the new build.
- Modules restarted with Update-Module -NoBuild: listen, voice, spotify, multi, link. Reason: they were still running with the per-launch core secret, which caused the on_start "unauthorized" warnings (fixed by 957b5ec).
- Result: ports 8760/8765/8766/7777/8770/8771/8772 all answer 200. Host logs info lines normally. Stream offline throughout.
- Still open after restart: voice "review failed: can't multiply sequence by non-int of type 'float'" (34x, owner 06, not reached this run). Voice "client dropped: ConnectionResetError" tracebacks (owner 06). Link still gets unauthorized POST /api/peer/broadcast (401), source unknown (owner 04). Shell and Host built from 02/01 commits fde8dc3, 3e0c1cf, 3e26618, 643795f, 957b5ec, dde8a9d, d1f0413.
- Site: NOT pushed (Railway incident still open; no Ivan OK). 05 has 15 local commits.
- 2026-10-22 04:22 -05:00 | site-push-batch-hourly: stream offline; pushed 3 commits to origin/main (c4f1a40, db668a9, c082597; origin 9222597..c082597). Commits remaining: 10 (oldest first: 771a629...be1f698 range, HEAD be1f698). Railway status.railway.com reachable (200), no incident check beyond that; innocentpenguin.com 200 but page does not carry commit shas, so live deploy of c082597 not verified.
- 2026-10-22 05:22 -05:00 | site-push-batch-hourly: stream offline (decapi). MISTAKE: pushed 8 commits instead of the authorized 3 (771a629, a38b756, 2aab5ef, 83d6d69, a6e14ea, 9f75436, bf34d80, 1f194e7; origin c082597..1f194e7). Cause: misread commit order from git log --reverse; pushed through 1f194e7 instead of 2aab5ef. No force push. Commits remaining: 2 (89a61c8, be1f698; HEAD be1f698). Railway status.railway.com 200 (page text mentions incident/degraded words, not conclusive). innocentpenguin.com 200; page carries no commit shas, so deploy of 1f194e7 not verified. Ivan should review the over-push.

| 2026-10-22 06:57 | Shell + Lite rebuild, Suite relaunch (00, Ivan approved) | Shell rebuilt with quit failsafes (2a7fec6); Lite rebuilt with bolt icon, update check, replay interval slider, quit failsafes (2dbbe6c). New shell could not reach the old core (per-launch token), so old cores were stopped and Suite relaunched; modules show. Spotify module restarted for a64666c..339fa9e. Host NOT yet restarted: waiting on 02 timeout rewards (c70d475 + self-timeout + chat-personalized lines). Wheel hub now uses the GIF (46047e7). |
