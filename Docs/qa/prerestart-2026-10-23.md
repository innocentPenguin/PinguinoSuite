# Pre-restart regression, 2026-10-23

HEAD 693043e, built into %TEMP%\pg11build (not bin\Release), tests run from a clean git archive copy. Run by 11.

Suites: helper 262/262 PASS; chat 348/348 PASS; sync-shared up to date (4 files); pack tests PASS (real-pack scan skipped, no Data folder in snapshot).

Host tests: 98 files. First pass ran 4 lanes in parallel and gave about 25 false reds (load); every red and missing test was re-run serially.

| Test | Result | Cause | Owner |
|---|---|---|---|
| test-host-economy2.py | RED | !bank line text no longer matches the test (known) | 15 |
| test-host-lore.py | RED | env: PinguinoB0t/channel_lore_seed.json is gitignored, absent in a HEAD snapshot (not a code bug) | 12 |
| test-host-loreowned.py | RED | lore-only term answered by CHATTY-A plus LORE-FREE; probably needs the gitignored seed, re-check on the real tree | 12 |
| test-host-obs.py | RED | env: needs Data/runtime/host_secrets.json, not in a HEAD snapshot | env |
| test-host-sbreplace.py | RED | shoutout dedupe: second call returns cooldown (f0e85f9 cooldown vs test expectation) | 15 |
| test-host-sim.py | RED | sim/site-off assertions fail (saved-file diff); needs a look | unknown |
| test-host-streaks.py | RED | env: port 8941 held by a stray `python -m http.server 8941` (pid 30480), Host cannot bind; re-run after it is stopped | env |
| test-host-subtickets.py | RED | no chat reply to "!shop sub"; after 6abc2b3 Chatty voices shop purchases, test likely stale (reproduced serially) | 12/15 |
| test-host-teach.py | RED | mod thank-you line, {link:discord} update and /api/links flag fail (lore link checks, maybe seed related) | 12 |
| test-host-timeoutreward.py | RED | TIMEOUT 240s | unknown |
| test-host-trial.py | RED | same shoutout cooldown, "cooldown then cooldown" | 15 |
| other 87 host tests | PASS | | |

Tests marked env need the live Data folder, the gitignored lore seed or a free port; they say nothing about the code.

## Update (later run on newer HEAD, then stopped by 10 at wrap-up)

- Fixed by later commits, no longer red: economy2, loreowned, sim (pass on ee0fad9); sbreplace/trial shoutout and subtickets were test-only and fixed by 99967ba and 1e4d196.
- Not re-checked on the newest HEAD (run was stopped): teach ({link:discord} update, /api/links flag; owner 12) and timeoutreward (timeout 240 s; owner 14/15, cause not found).
- Env, not code: lore (gitignored seed), obs, streaks (stray http.server on 8941).
- Tests that start a NON-sim Host: lease (no PINGUINO_COMPAT_WS_PORT, so the default compat WS port 8080 is used), obs (reads the REAL Data/runtime host_secrets.json and drives the REAL OBS), obstree (mock OBS, safe). No fixes to these were made. Suggested: add --sim or a compat port to lease, and make obs refuse unless an explicit test env var is set. Owner 15.

## Final run on HEAD 197d993 (11, 2026-10-24 00:30)

Clean `git archive` of 197d993 (the restart set: 1605013 raid goodnight hold, 8c55fb0 canned $(link:discord), 6e40f22 Chatty raid lines, 278e9d3 !vanish, ebdb27c Helper !vanish test, a68ead3 Firsts bot fix), Host built to %TEMP%, 116 host test files run serially (obs and lease skipped: they use the real OBS / default WS port). Later commits (up to 75e98a9: overlay parts, Chatty docs) not covered.

| Suite | Result |
|---|---|
| bots routing | 108/108 PASS |
| helper | 267/267 PASS |
| chat | 2 FAILED / 392 passed |
| helper pack (real) | PASS |
| host tests | 114 PASS, 2 RED, 2 skipped |

Reds (re-run serially, reproduce):

| Test | Cause | Kind | Owner |
|---|---|---|---|
| test-host-alerttest.py | "raid_out: the held goodnight runs after the raid" fails every time; all other 8 raid checks pass. Touched by 1605013 (held_offline.json recovery) | real or stale test, unverified | 15 |
| test-host-sitebridge.py | every !shop guess line check ("takes the stake and shows the chat line once", "second round refused", "right guess pays 2x", cooldown): the Host now answers through Chatty (12ed7ea Games voice), the test still expects the plain Host line | stale test | 15/12 |
| chat: "!onlyfans points to the Discord" | answer is the luck line "You got 27% luck ..." instead of the Discord pointer | unverified, likely real | 12 |
| chat: "anniversary: two years to the day gets its line even when plain hellos are off" | no line said | unverified | 12 |

The earlier partial run on ebdb27c (stopped at 55/100) showed cmdfix, economy2, firstsbots, gamble, givedep red; they all pass on 197d993. vanish, botsflag, canned, spamfirst, rewards, raidflow, firstsbots pass.
