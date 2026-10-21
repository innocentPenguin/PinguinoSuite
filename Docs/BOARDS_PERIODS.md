# Period leaderboards (day / week / month / year / all time)

Owner: 02 (Host). Code: `PinguinoHost/HostPeriods.cs`. Test: `Tools/test-host-periods.py`. Backfill: `Tools/rebuild-buckets.py`.

## Source of truth and derived buckets
- **Event log** (append only, never edited or reset): `Data\boards\metric_events.jsonl`, one line `{ts, user, metric, amount, id?, grain?}`. (The older `Data\boards\events.json` stays the gifts/bits ledger the existing boards use; its events are copied into the new log with the same id.)
- `id` makes an event count once (retries, restarts and a second backfill never double count). `grain:"month"` = an old monthly total (counts for that month, its year and all time, never a day or week).
- **Buckets** are derived in memory (metric > key > user > sum) and can be rebuilt any time: `POST /api/boards/reload` (or restart). High-frequency events (watched minutes, chat messages, commands) update the buckets at once and reach the file as one coalesced line per person/metric/day every 5 minutes (`PINGUINO_BOARD_FLUSH_SEC`).
- **One timezone** for every key: `Periods.Tz` = `America/Chicago` (`HostPeriods.cs`; `DayShiftHours` = 0 keeps local midnight; set 4 to keep a stream that runs past midnight on the day it started). Keys: day `YYYY-MM-DD`, ISO week `YYYY-Www`, month `YYYY-MM`, year `YYYY`, `all`. (Week 53 of 2026 holds 28 Dec 2026 to 3 Jan 2027.)

## Metrics
`watchtime` (minutes), `points` (earned; loans, repayments and depreciation are not income), `points_spent`, `messages`, `xp` (1 per watched minute + 2 per chat message), `gifts`, `bits`, `follows`, `refollows`, `commands` (chat messages starting with `!`), `wins` (PinguinoBot match wins). API metric `level` ranks by xp gained in the period; `value` = level reached by the end of that period (level = 1 + floor(sqrt(xp/50))), `pct` = % to the next level. Bots, the opted-out ("anon") and alias duplicates are folded/left out like on the other boards.

## API
`GET /api/boards?metric=&period=day|week|month|year|all&key=&login=&top=10`
```json
{"ok":true,"metric":"watchtime","period":"week","key":"2026-W43","keys":["2026-W43","2026-W42"],"updatedAt":"2026-10-21T20:00:00Z","total":58,
 "rows":[{"rank":1,"login":"penguinfan","name":"PenguinFan","value":1620}], "me":{"rank":15,"value":540}}
```
Empty `key` = the current period; `me` only when `login` is given and ranked; `level` rows also carry `pct`. `GET /api/boards` without `metric` is the old snapshot. `POST /api/boards/event` (test hook only) and `POST /api/boards/reload`.
The site push `POST /api/bot/boards` now also carries `periods`: `{metric:{period:{current, keys:[...], boards:{key:{total, rows:[top 100]}}}}}` for watchtime, points, messages, level, gifts, bits (last 14 days, 12 weeks, every month and year, all time).

## Chat
`!top` / `!leaders <watchtime|points|messages|level|gifts|bits> [day|week|month|year|all]` (default week); `!watchtime` and `!points` add "today X, this week Y, this month Z" (points = earned). LOTD / LOTW / LOTM read the same thing: `Periods.Query(metric, "day"|"week"|"month", "")` row 1.

## Backfill
`python Tools/rebuild-buckets.py [--data D:\PinguinoSuite\Data] [--dry-run] [--reload http://127.0.0.1:8770]` recovers gifts and bits (exact), the economy ledger (exact), and watch minutes, watching points and messages per month (month grain). No history exists for follows, commands and wins: they count from the Host update on.
