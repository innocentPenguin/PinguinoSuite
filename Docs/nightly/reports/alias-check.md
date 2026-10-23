# Alias check: adday_rl / addayofficial (/ addayc7) - 2026-10-23, worker 14 Lore

Read only. No ledger, alias or points change was made. 100 decides.

## Where alias merges live
- `Data\boards\aliases.json` (`aliases`: alias login -> main login; Ivan-approved merges, e.g. ixsamux -> ixsamuu 10-21). `Boards.AliasMap()` / `Boards.CanonLogin()` apply it for boards, bits/gifts/messages/watch streak, BackPay and the points `Canon` calls. The lore mining (people_graph, person cards) reads the same file at build time.
- `Data\namehistory\names.json` (+ `helix_ids.json`) is the detector output (tier CERTAIN / POSSIBLE), not applied by itself.
- Neither adday login is in aliases.json today, so every system treats them as different people.

## Evidence it is one person (a chain of logins)
| login | first seen (UTC) | last seen (UTC) | msgs | notes |
|---|---|---|---|---|
| addayc7 | 2026-07-13 22:34 | 2026-07-14 02:32 | 140 | detector pair addayc7 -> adday_rl, tier POSSIBLE (name similarity 0.71, gap 0.9 days) |
| adday_rl | 2026-07-14 23:13 | 2026-09-21 02:28 | 2,108 (logs count; people graph says 1,054) | |
| addayofficial | 2026-09-21 22:02 | 2026-10-18 02:22 | 396 | Twitch id 1340378967 (the other two have no id on file) |
- Each hand-over is under one day, with no overlap in activity (adday_rl's last message and addayofficial's first are ~20 h apart), three similar "adday" names, same channel, same regular-chatter pattern. A rename or a new account of the same person is by far the likeliest reading.
- The first addayofficial messages on 09-21 mention having changed something about their account/look, right after the switch. I am not quoting the chat; read the 09-21 logs if you want to confirm.
- Not proven: there is no Twitch id for the older logins, and a person can have two accounts. Confidence: high for adday_rl -> addayofficial, medium for addayc7 -> adday_rl (only 140 messages, 1 day).

## What is split today
| thing | adday_rl | addayofficial |
|---|---|---|
| back-pay (10-22) | 80 pts (2 cheers, 20 bits each) | 40 pts (1 cheer) |
| points adjust | 80 | 40 |
| StreamElements import snapshot (10-20 dry run) | not seen | listed in the import dry run (values of roughly 2,000 to 9,500 in three boards; I did not check which board is which) |
| messages | 1,054 (people graph; names.json counts 2,108, probably both sides of a log format) | 198 (graph) / 396 (names.json) |
| people graph / person cards | node with 1,054 msgs, group 1, no edges listed | node with 198 msgs, group 1, no edges listed |
| firsts / wins / bits boards | small entries in totals.json (two boards, values 38 and 3); not checked board by board | none found |
So the money in dispute is only 120 back-pay points; the bigger effect is the board and history split (lifetime messages, watch time, firsts) and the imported StreamElements balance sitting on addayofficial only.

## Proposed entry (not applied)
In `Data\boards\aliases.json`, `aliases`:
```
"adday_rl": "addayofficial",
"addayc7": "addayofficial"
```
and in `why`: `"Ivan approved <date>: same person, renamed twice (addayc7 -> adday_rl -> addayofficial)"` (the file keeps an approval note per alias).
Main = addayofficial (newest login and the only one with a Twitch id). Effects after the next boards refresh: their messages, watch time, gifts/bits and streak combine under addayofficial; points: any adjust/balance stored under adday_rl (80) is a separate ledger key, so a one-time move of 80 points adj from adday_rl to addayofficial is a ledger action for 100, not done here. After approval the lore mining will fold them into one node on the next rebuild (it reads aliases.json), and the timeout people-graph code already canonicalises logins through `Boards.CanonLogin`.
