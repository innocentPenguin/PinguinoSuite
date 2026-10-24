# 10 - Bots (supervisor) - backlog and state

Session local_9171fff1-01ec-4f70-a82a-15af3c6dcb3e. Started 2026-10-23 05:30. Reports to 100 - Coordinator (local_32405a3a-974d-494b-8007-01272497ad35). Area: PinguinoHost, PinguinoB0t (overlays, scene editor), ChattyPinguino, PinguinoHelper, economy, wheel, shoutouts/clips, lore, nightly review.

Rules: only the coordinator builds/restarts/pushes (Host restart = App\Update-Module.ps1 host). Never go live in OBS. Every chat send goes through HostApi.SendAs / PgSay (no duplicates). No secrets in commits or messages. Two writers never edit the same file. No idle worker.

## Already done by old 02 (committed, waiting for a Host restart; the 05:xx coordinator queue was stale)
reply threading 3a7c46e, give limit per stream 739d2e5, strike check-in d551e2b, wheel ease-out/??? box/vertical 37d214b, gifted-sub tags + mod activity feed push a0b6e05, Get a sub d1bc642, intro storage + GET /api/intro (HostIntro.cs), watch-streak -> Multi /api/alerts/fire (HostAlertBridge.cs), back-pay 40% endpoint POST /api/economy/backpay (dry run / apply, test-host-backpay.py), raid "prepare your emotes" now fires on raid_start (scheduled), firsts 5/3/3/1/1, scenes phase 1-3 (HUD widgets 5ecd623).

## Backlog (numbered; owner in brackets)
1. [DONE Host: f0e85f9, d0424d2; test-host-shoutout.py green 10-23; progress bar/800x600 playback is Multi side] [15 Host] Shoutout rework per Ivan: clip of the target (featured first, then most viewed, all-time), clip only (no Twitch card), 10 s delay, mods only, 60 s cooldown, auto on raids of 3+ viewers, progress bar, plays in the 800x600 alerts source via Multi POST /api/alerts/fire. Files: HostLatest.cs (Shout), HostAlertBridge.cs, HostClips.cs, Tools/test-host-shoutout.py.
2. [DONE: f0e85f9 shared clips_recent.json no-repeat-3, 58d4531 atomic pick+mark; test-host-clips.py + shoutout green 10-23] [15 Host] Clip rules for bot-posted clips: featured clips from the last 2 weeks, never repeat the last 3 sent, one shared recent list across all three bots (Data\runtime\clips_recent.json). Files: HostClips.cs, HostLore.cs clip entries, HostTimeoutReward/Self if they post clips.
3. [DONE as graceful: 9c06716 source chain with backoff/stale cache/custom sources, a13fc18 clear Cloudflare wording, manual !setrank stays; test-host-rank.py + ranktest green 10-23; no free working source found, tracker.gg still blocked unless Ivan adds Dataank_sources.json] [15 Host] !rank source: tracker.gg blocked by Cloudflare; find a working source or a graceful manual-only mode (!setrank). HostRank.cs.
4. [13 Overlays] setgame fallback: when the Twitch category changes (HostObs/HostChannel sees twitchGame) call Scenes.SetGameAll, Master View stays primary. HostObs.cs, HostScenes.cs.
5. [13 Overlays] ?part= modes (wheel only, team cards only, queue list only) in wheel.html / players.html / customs.html / queue.html now that 37d214b landed; register them as scene widgets.
6. [13 Overlays] Test pass of scenes phase 3 + wheel 37d214b in the sim Host; fix what breaks. Held: !layout chat command (Ivan).
7. [DONE 12ed7ea games voice incl. guess refusals; kind=shop confirmations untouched on purpose (Ivan decides)] [12 Chatty] PgGame kind=guess and kind=shop events (HostGamble.cs / HostSubTickets.cs emit, Chatty voices), exactly one line per action.
8. [DONE: Docs/LIVE_VERIFY_AFTER_RESTART.md, all offline suites green, RxHeat tuned (episodes 19->9); needs Host restart, nothing run live] [12 Chatty] Live-verify checklist doc for after the restart (!tuck, !raid, raid/hype reactions, welcome-back, called-out, PgGame lines, !games, /api/canned) and run all offline tests; tune RxHeat if tests show over-eager heat detection.
9. [11 Helper] Host router re-dispatch of typo'd Host-owned info commands (!poinst -> !points etc.) so they run instead of only being suggested: CmdFix.cs Targets list + Helper side. Files: HostCmdFix.cs (11 owns), HelperPinguino/PinguinoHelper.cs.
10. [11 Helper] Spanish pack entries draft (for Ivan's OK), mod pass of Docs/HELPER_DRAFTS.md into the pack docs, run helper tests + pack tests.
11. [14 Lore] People graph into timeout lines (HostTimeoutReward.cs uses Data\lore\people_graph.json: who-knows-who flavour), respecting opt-outs; private data never quoted verbatim. **DONE (a82bf19, test-host-timeoutgraph.py PASS: opt-out anon, !forgetme, bots, unknown pairs get the normal line; excerpts never used)**.
12. [14 Lore] Back-pay 40%: run the sim dry run, write Docs\nightly\reports\backpay-dryrun.md (totals, top 20, anomalies) for Ivan; the apply is a coordinator action. **DONE: the back-pay was already applied 10-22 (248 cheers, 118,164 pts); dry run on a copy gives 0 left. Report: Docs/nightly/reports/backpay-dryrun.md. Nothing to apply.**
13. [14 Lore] Apply the [APPLY] items of Data\lore\proposals_for_bots.md that are lore data (channel_lore.json guidance, "never recount who said it"), and the nightly Phase 1 chat-log learning for 10-22/10-23 logs. **DONE for lore data; per-item status in Docs/nightly/reports/proposals-for-bots-status.md (bot-code items belong to 10/11/12). Phase 1 for 10-22/10-23 is in reports, proposals only, held for Ivan.**
14. [VERIFIED 10-23, no change: viewer 28 play / 42 win, sub T1 42/63, T3 win 126 (7 min x watch rate/min x2|x3); paid end-to-end once per match id by test-host-points.py + economy2; HostPointsTest] Match awards into the ledger: play = 7 min viewer rate x2, win = x3 (IDEAS #3) - confirm numbers back to Ivan. HostEconomy2.cs / HostPoints.cs.
15. [VERIFIED 10-23, no change: chat bonus max 12 pts/h (1 per 5 lines, cap 2 per 10 min) vs watch 120/h viewer, 180/h sub T1, sub 6000, 100 bits 1000; new checks in pointstest] ActivityBonus check: gifts + watch time must stay ahead of chat-line points (Ivan 10-22).
16. [open] Points settings page with preview (Suite side = 20; Host provides /api/economy/preview, exists).
17. [held] !speak TTS (Voice module 26afe27, off until Ivan names/prices it) - 50 Tools owns the module; Host alias only.
18. [held] 3x audit + 4-tier docs (only when Ivan says done).

## Questions for Ivan (with my default)
Q1. Shoutout clip when the target has no clips at all: fall back to the Twitch shoutout card + line (default yes).
Q2. !rank: if no free source works, keep manual !setrank only (default yes).
Q3. Match awards: play = 7 min x viewer rate x2, win = x3 - confirm (default yes, as decided 10-22).
Q4. Back-pay: apply after the dry-run report, or review first (default: review the report first).

## Workers
11 Helper, 12 Chatty, 13 Overlays, 14 Lore, 15 Host (ids in SESSIONS_STRUCTURE once started). File ownership is listed per item above; HostGamble.cs and HostSubTickets.cs belong to 12 this round; HostCmdFix.cs to 11; HostLatest/HostClips/HostAlertBridge/HostRank to 15; HostObs/HostScenes/overlays to 13; HostTimeoutReward/HostLore/Data\lore to 14. Nobody edits Program.cs, HostApi.cs, HostSiteBridge.cs without asking 10.
