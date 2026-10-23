# Back-pay dry run (40% of the current cheer curve) - 2026-10-23

Run by worker 14 (Lore) in the sim Host (`--sim --no-sync`, temp copy of Data\boards + Data\economy; nothing live touched, nothing applied).

## Headline
**The back-pay has already been applied to the live ledger.** All 248 cheers carry a `backfill:bits:cheer:...` ledger entry timestamped **2026-10-22 10:42**. A fresh dry run on a copy of the live data therefore reports `people 0, points 0, already_paid_events 248`. The apply is idempotent per cheer, so re-applying would pay nothing. Backups from that run exist in Data\economy (`points.json.before-backpay-20261022-154251.bak` / `...154254.bak`).

Nothing is left for the coordinator to apply. Q4 ("apply after the report or review first") is moot unless Ivan wants the 10-22 payout reversed or changed.

## What was paid (recomputed independently from Data\boards\events.json + economy\settings.json, matches the ledger to the point)
| | |
|---|---|
| Cheers in the logs | 248 (2026-02-19 to 2026-10-19) |
| Bits | 24,906 (same total in metric_events.jsonl) |
| Distinct logins (before alias merge) | 47 |
| Points paid (40%) | **118,164** |
| Mismatches ledger vs recompute | 0 |

Curve in settings: under 500 bits x10, 500-999 x11, 1000+ x15; back-pay = 40% of that. The curve is applied per cheer, not per person total, so 100x 1-bit cheers pays less than one 100-bit cheer rounding-wise (a 1-bit cheer pays round(10*0.4)=4).

## Top 20 by points paid (alias merges applied: sg_yen -> cyfirl, shown merged)
| # | login | bits | points |
|--|--|--|--|
| 1 | cyfirl (+sg_yen) | 6,500 | 39,000 (30,000 + 9,000) |
| 2 | zylorocketleague | 3,725 | 15,500 |
| 3 | shadowrlttv | 2,893 | 12,012 |
| 4 | speedyy2435 | 1,845 | 9,580 |
| 5 | alpha_fire_rl | 1,100 | 6,400 |
| 6 | shinobisninja1 | 920 | 3,680 |
| 7 | ash_wagawaga | 860 | 3,440 |
| 8 | creamysnip3s | 750 | 3,300 |
| 9 | the_viper_333 | 600 | 2,400 |
| 10 | wristymarlin | 550 | 2,200 |
| 11-13 | rozieriot, atrueomni, cosmicryozen | 500 each | 2,000 each |
| 14 | yoohoo15 | 385 | 1,540 |
| 15 | kaiyoreal | 280 | 1,120 |
| 16-17 | hebunga, blizzyfvv | 250 each | 1,000 each |
| 18 | mirihater | 245 | 980 |
| 19 | zylo_road2gc_ | 227 | 908 |
| 20 | next is below 900 | | |

Top 10 people hold ~87% of the payout; cyfirl alone is 33%.

## Anomalies
1. **`twitch` was paid** (2 cheers, 25 bits, 100 pts). It is a system/anonymous-cheer pseudo-login, not a person; those points are stranded. BackPay now skips pseudo users (commit 8deb5a3, applies to future runs only); the 100 pts already paid on 10-22 can be reversed by hand if wanted.
2. **Alias split**: sg_yen is an alias of cyfirl, and the ledger paid it under the canonical login, but adday_rl / addayofficial are two separate paid logins (80 + 40 pts) and may be one person; not in the alias map.
3. **ixsamux** (3 cheers, 145 bits) got nothing: it is an alias of ixsamuu (merged 10-21) and the streamer is skipped by design.
4. **Tiny cheers**: 73 of 248 cheers are under 10 bits; 52 are exactly 1 bit (4 pts each). cups0ftea alone has 12 one-bit cheers. Fine, just low value.
5. **No double counting**: no duplicate (user, timestamp) cheers; none paid twice; no stray backfill ids.
6. **Spam in raw chat text**: logs contain "cheerNNNN" text from chatters (one ~10^13 bits). These are not real cheers; they are NOT in the ledger (it comes from tagged events), so no inflation. Worth keeping, never parse bits from message text.
7. Coverage: only 5 cheers in October, 2 in February (logs start 2026-02-15); the ledger covers the whole log range.

## Sane?
Yes. 118k points is small next to the economy (admin adjust balances alone sum ~223k, yoohoo15 holds 42k of it), the distribution matches who actually cheered, and totals reconcile three ways (ledger, events.json, metric_events). Only action worth doing: optionally reverse the 100 pts paid to `twitch`, and decide the adday alias.
