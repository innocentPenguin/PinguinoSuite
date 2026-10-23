# 02 - PinguinoBots / PinguinoHost: hand-over (written 2026-10-23 ~05:55)

Session: "UNIT 02: PINGUINOBOTS", id 16a10e69-83ee-43bd-b018-f8ce4c9f734c.
Transcript: C:\Users\ivanm\.claude\projects\D--\16a10e69-83ee-43bd-b018-f8ce4c9f734c.jsonl (grep for: `strike check-in`, `giveLimit`, `ReplyCtx`, `site_activity`, `ViewerIntro`, `FireShoutout`, `ClipPick`).
Forks: 021 Helper local_6f5d97c2-3914-477d-b04a-e7e5bec9c3af, 022 Chatty local_7135181f-2c8d-4cec-8cda-1c0d6edae3ff, 023 Overlays local_30e19219-6bb0-4db8-ac65-ae0800f6ee15. Their own notes: Docs\sessions\021-helper.md, 022-chatty.md, 023-overlays.md.

I own: PinguinoB0t core (compiled into the Host), Chatty / Helper / Router, PinguinoHost (.NET 8, port 8770).
Status: I stopped coding. Everything I wrote is committed (see list). Nothing is pushed. No restart was done by me.

## 1. What was built (commits, all 2026-10-23, nothing pushed) and why

| Hash | What | Needs Host restart |
|---|---|---|
| d551e2b + 02fede1 | Quiet strike check-in: a viewer who has watched 15 continuous minutes loses one temporary strike per local day. Host (HostStrikeCheckIn.cs) decides and writes runtime\strike_checkin_queue.json; Core `ApplyStrikeCheckIns()` (runs in ApplyLive, ~30 s) applies it. Silent: no chat, no site text. Each removal goes to mod audit as actor "system". Settings (Suite > Queue): checkinOn / checkinMinutes (15) / checkinPerDay (1). 02fede1 puts Program.cs back to LF. | yes (Core + Host) |
| 739d2e5 | Give limit = % of the giver's balance, counted per stream (giveDailyPct 10, giveDailyMin 0, giveDailyMax 0 = no cap). New stream id resets it; offline carries over. Page fields: giveToday, giveLimit, givenThisStream, givePct. 05 must know. | yes |
| 3a7c46e | Bot replies are native Twitch replies (reply_parent_message_id). Host senders use an AsyncLocal ReplyCtx (HostReply.cs, begun in Program.Dispatch); the shared bot block uses PgReplyParts. Falls back to the old "@name text" line when there is no real message id or the context is older than 90 s. | yes (Host, Core, Chatty, Helper, Router) |
| 848ec8b | Activity feed now PUSHES each event once, oldest first, in batches of 50, to the site's POST /api/bot/events with the site's type names (follow, sub, resub, giftsub, cheer, raid, raid_out, hype, redemption). Sent ids persisted (runtime\site_activity_sent.json). tip and boost are not sent (no Twitch event for them). Refollow is only known from the day this started. | yes |
| f541a6a | Viewer intros (HostViewerIntro.cs): per viewer text + sound, profanity/link filter, mod approval queue, mod audit. GET /api/intro?platform=&user_id= -> {text,sound_id,status:"approved"} or 404 (for Multi). GET/POST /api/intros (list, submit, remove, approve, reject, settings). Site queue actions: intro_submit / intro_remove / intro_approve / intro_reject. Data: Data\viewer_intros.json. Default: approval required, max 80 chars. | yes |
| earlier today | 37d214b wheel ease-out + ??? placeholder, d1bc642 Get a sub (shipped OFF; price suggestion 35,000), a0b6e05 gifted-sub tags + mod activity push, 8cc1987 economy activity ledger / P2P loans / public pages / hide flag / depreciation dry run / mod audit, b1d8c42 + f88f5eb Chatty voices gambling, a19e71e rank/skip-vote fixes | already in the 05:01 build except what is newer |

Watch-streak alert needs nothing new: HostStreaks calls AlertBridge.OnStreak on every streak notification; Multi decides which counts show (3, 5, 10, 25, 50, 100).

Ivan's words that led here (paraphrased from the queue 00 relayed): "quiet strike check-in, no chat", "give limit as a share of what they have, per stream", "replies should be real Twitch replies", "activity to the site", "viewers set their own intro, mods approve".

## 2. Decisions and failures
- Core is the sole writer of players.json, so Host to Core handoffs go through files (strike check-in). Do not make the Host write players.json.
- Reply threading is done twice on purpose (Host senders and shared bot block), both with the plain-line fallback so a missing id never drops a message.
- Intro filter is deliberately simple (leet-normalised word list + links + leading "!" command); the mod approval queue is the real gate. Short words use word boundaries so "document", "cocktail", "Skyscraper" pass.
- Failures I hit: C# escapes written through Python heredocs got corrupted (use chr(92), verify output); I once swept other sessions' files into a commit (stage explicit paths only, never `git add -A`); Program.cs got committed CRLF (fixed, it is LF in the index). test-host-gamble.py and test-host-tune.py fail on the OLD build too (not caused by me; test-host-givedep also fails on "then nothing more today" because the new per-stream limit is 100% in that test; update that test's expectation).
- SendMessage was paused many times ("looks like sessions messaging each other"); reports then go in the reply text.

## 3. Gotchas and how to test
- Any Core or Host change needs a Host restart (Core is compiled into the Host). Only 100 restarts.
- Build a test DLL, never the live one: `dotnet build PinguinoHost -c Release -o "$SCRATCH/bNN"`, then `python Tools/test-host-<name>.py <path-to-dll>` (tests spawn the DLL with `--sim --no-sync --data <tmp>`). Tests to run for my work: test-host-strikechecktest, test-host-strikecheckin-core (waits ~38 s), test-host-givelimittest, test-host-replytest, test-host-activity, test-host-viewerintro, test-host-subtickets. Bot suites: Tests\core, Tests\chat, Tests\helper (run-*.ps1 via `powershell -NoProfile -ExecutionPolicy Bypass -File`), Tests\bots\run-bots-tests.ps1 (99 checks).
- Shared bot block: edit Shared\PinguinoBots.cs.txt, then `node Shared/sync-shared.mjs` (use `--check`). Never hand-edit the four synced copies.
- Line endings are mixed (Program.cs LF, many files CRLF). Edit with byte-level Python that preserves BOM and CRLF.
- Sim self-test lines in Program.cs: pointstest, strikechecktest, givelimittest, replytest.
- Env switches for site tests: PINGUINO_SITE_BASE, BOT_API_KEY, PINGUINO_ACTIVITY_PUSH_SEC, PINGUINO_ACTIVITY_SIM.
- After the restart 100 should run the dry firsts rebuild (POST /api/firsts/rebuild {}) and apply only on Ivan/00's go.

## 4. Open queue state (what is NOT finished)
- **Uncommitted in the Host tree that is NOT mine (do not commit blindly):** PinguinoB0t\overlays\live_state.js (023's), and these Host files had edits I did not make after the compaction: HostClips.cs (ClipPick: featured clips, never repeat last 3, shared list Data\runtime\clips_recent.json), HostAlertBridge.cs (`FireShoutout` to Multi /api/alerts/fire), HostLatest.cs, HostObs.cs, HostScenes.cs, HostWheelPublic.cs, HostTimeoutReward.cs, HostTimeoutSelf.cs, HostGamble.cs, HostSubTickets.cs, PinguinoChat.cs. HostClips/FireShoutout look like clip-rule and shoutout work somebody started (it may be a pre-compaction piece of mine; I could not confirm). They need a test run and a commit by whoever owns them. 10 - Bots should find the owner via `git diff` and the forks.
- Clip rules (pool = featured, last 2 weeks; fallback most viewed; never repeat the last 3; cache Helix list ~10 min): code exists uncommitted (above), not wired into every bot path, not tested by me.
- Shoutouts (`!so` mods only, 60 s per-streamer cooldown, auto-shoutout a raider with >=3 viewers after 10 s, clip from the TARGET channel, fire to Multi type "shoutout"): only FireShoutout exists, uncommitted. The command, settings and Suite UI are not built.
- Alert-for-everything (raid_out, hype levels, goals, polls, first chatter, tips, gambling wins, shop, loans, milestones through the Multi alert path): not started.
- !speak TTS: held until 00/Ivan approves the design.
- !rank source, setgame on Twitch category change, lore people-graph into timeout lines, back-pay 40% applied live: not done by me (back-pay test exists from earlier).
- Not verified live: team names on overlays, `!format NvN`.
- Held until Ivan says done: 3x code audit and 4-tier docs.
- Live entryCooldownSec should be 600 (100 sets it). DepreciationDryRun flip only on Ivan's decision. Songify off before enabling spotify automations.

## 5. Contracts to pass on
- Site P2P: site reads market[] and per-user p2p{...}; settings.p2p limits {minAmount, maxAmount, maxInterestPct, maxDays} (defaults 10/100000/50/30). loan_cancel: Host reads `targetId` first and falls back to `id`.
- Batch-1 items 05 may not have been told: loan_cancel targetId, giveToday/giveLimit/hidden/depreciation fields, give and page_hide queue actions, GET /api/economy/public, mod-audit design (GET /api/modaudit).
- Multi: 03 gets the intro via GET /api/intro (module token as Bearer or Origin http://127.0.0.1:8766). 05 gets sounds from Multi GET /api/intro/options {sounds:[{id,label}], max_len} and submits intros through the queue actions above.

## 6. Future plans (priority order)
1. Commit/finish the clip rules and shoutout pipeline (pieces exist uncommitted), then the `!so` command, raid auto-shoutout and Suite settings.
2. Alert-for-everything through Multi.
3. Update the stale tests (givedep expectation, gamble, tune).
4. p2p chat commands; guess/shop events via Chatty if 022 wants them.
5. !speak TTS after design approval.
6. Run the held audit and docs when Ivan says done.

## 7. Things Ivan may be forgetting
- Get a sub is OFF and the Suite page and site mod view are not built.
- Intro approvals need a mod UI (Suite page or site) - only the API exists.
- tip and boost activity events never come from the Host; the site needs another source.
- Live entryCooldownSec is not yet 600; firsts rebuild has never been applied.
- Several Host files are edited but uncommitted by other sessions; a restart before they are committed would ship untested code.
- The GitHub plugin is broken; push with plain git, and only with Ivan's typed OK.
