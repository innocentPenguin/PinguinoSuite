# Points rework: rules, settings, ledger contract

Everything below lives in `Data\economy\settings.json` (hot reloaded within ~2 s, no restart). Source: `PinguinoHost\HostPoints.cs`.

## Rules (default values)
| What | Points | Keys |
|---|---|---|
| Watch (only while live) | every full 5 min: viewer 10, sub T1/Prime 15, T2 20, T3 30. Leaving before the next mark earns nothing for the partial stretch. The rate is picked at the moment of payment. | `WatchIntervalMin`, `WatchViewer`, `WatchSubT1..3` |
| Entering the stream | 100, once per stream | `EntryBonus` |
| Cheer (chat cheers only, never Bits in Extensions / Power-ups) | per bit: <500 -> 10, 500-999 -> 11, 1000+ -> 15 | `CheerLow/Mid/High`, `CheerMidFrom`, `CheerHighFrom` |
| Sub / resub | T1 6000, T2 12000, T3 30000 | `SubT1..3` |
| Gift subs | tier value per sub gifted; recipient 1500 | `GiftRecipient` |
| Tip | $1 = 1250, $5 = 7000, $10 = 20000, linear in between and beyond $10, never below 1250 per dollar | `TipCurve`, `TipFloorPerUsd` |
| Follow | 150, once per account ever (refollow = 0) | `FollowBonus` |
| Raid arrival | 150 on top of the entry 100 (inside the window after the raid) | `RaidArrival`, `RaidWindowMin` |
| Raid leader | 1000 when the raid brought 4+ viewers | `RaidLeader`, `RaidLeaderMin` |

`WatchV2: false` (or env `PINGUINO_ECONOMY_V2=0`) brings the old per-minute earning back.
Every award has a unique event id (EventSub message id); the same id never pays twice (replays, reconnects, restarts).

## API
* `GET /api/economy/preview?type=cheer&amount=500[&tier=2]` -> `{ok,type,amount,tier,points,detail,dryRun:true}`. Types: watch, entry, cheer, sub, gift (amount = count), gift_recipient, tip (amount = USD), follow, raid_in, raid_leader (amount = viewers). Nothing is paid.
* `POST /api/economy/event {type, login, amount, tier, id}` -> pays one event (needed for tips, which have no EventSub). `id` is required and unique per event. Same types as above (tip, cheer, sub, resub, gift, gift_recipient, follow, raid_leader).
* `GET /api/economy/streams?login=` -> `{ok,login,streams}`.
* `GET /api/economy/me?login=` and `/api/points?login=` now also carry `streams`.

## `streams` contract (05)
```
streams: [ { id, label, start, end|null, live?:true, total, rows: [ { at, type, label, delta } ] } ]
```
* newest stream first, rows newest first; caps 60 streams x 200 rows per person; `total` is the person's exact total for that stream (rows can be trimmed, the total is not).
* `at` = unix seconds. `type` is one of `watch | cheer | sub | gift | tip | follow | raid_in | raid_out | game | loan | depreciation | other`. The Host writes the finished `label`: "Watched 5 min", "Watched 5 min (sub T2 rate)", "Joined the stream" (type other), "Cheer 500 bits", "Sub T2" / "Resub T2", "Gifted 5 subs T1", "Received a gift sub", "Tip $5", "Follow", "Raid arrival" (raid_in), "Raided with 12 viewers" (raid_out = the raid leader).
* Events outside a stream are filed under the stream `off` ("Between streams", `start` 0, always last).
* Not yet in `streams`: match awards, loans, depreciation and other ledger rows are in `ledger` as before (they are not stream-grouped yet).
