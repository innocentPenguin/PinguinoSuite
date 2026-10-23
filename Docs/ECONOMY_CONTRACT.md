# Economy contract for the site's Points page (Host <-> innocentpenguin.com)

Owner: 02 (Host). Site side: 05. Same bot key as every other bridge (`Authorization: Bearer <BOT_API_KEY>`), never logged. All amounts are whole points; the currency word is `points` (the Host sends `currency`).
The Host never receives a viewer's token: the site decides who the logged-in viewer is and only ever asks for that Twitch login.

## 1. What the Host pushes: `POST /api/bot/economy/users`

Sent about once a minute (and right after a site request was handled), only for people whose view changed, at most 100 users per request. A 404 means "the site has no Points page yet" (the Host just keeps trying quietly).

```json
{ "currency": "points", "at": 1792618843,
  "settings": { "CurrencyName":"points", "ActivityAwards":true, "CustomsPlay":5, "CustomsWin":10, "CompPlay":10, "CompWin":25, "CasPlay":5, "CasWin":15,
                "DepreciationOn":true, "DepreciationDryRun":true, "DepreciationPct":2.5, "DepreciationThreshold":100000, "DepreciationBasis":"total",
                "LoansOn":true, "LoanPerHour":100, "LoanCap":5000, "LoanMinWatchHours":1, "LoanInterestPct":5, "LoanDefaultStreams":10 },
  "users": [ <view>, ... ] }
```

`<view>` (the same object `GET /api/economy/me?login=` returns on the Host, minus `ok`):

| field | meaning |
|---|---|
| `login` | lowercase Twitch login (aliases already folded into the main account) |
| `balance`, `rank`, `of` | whole points; rank among non-bot holders (`of` = how many) |
| `minutes` | watch time in minutes |
| `depreciation` | `{on, dryRun, pct, threshold, basis, amount, applies, when, streamOpen}`. `amount` = what this person would lose at the end of the stream (0 when under the threshold). `when` is `"end of this stream"` while live, else `"end of the next stream"`. While `dryRun` is true NOTHING is taken: show "practice run" on the page. |
| `loans` | `{on, maxLoan, interestPct, defaultAfterStreams, owed, principal, streamsOpen, defaulted, takenAt, canBorrow}` |
| `earnings` | groups by source: `[{source, label, earned, spent, count}]`, biggest first. Sources: `watching` (passive minutes), `imported`, `customs_play`, `customs_win`, `comp_play`, `comp_win`, `cas_play`, `cas_win`, `welcome`, `gamble`, `slots`, `duel`, `gifts`, `shop`, `loan`, `loan_repay`, `depreciation`, `grant`, `other`. New sources may appear: show `label` and fall back to the raw `source`. |
| `ledger` | newest first, at most 30 rows: `{id, at (unix s), source, delta (+/-), balance (after), note, reason}` |

"Playing" on the page = the `*_play` groups, "winning" = the `*_win` groups.

## 2. What the viewer can do: the request queue (same pattern as the shop/join bridge)

The site stores a request, the Host polls it. The Host does not call back into the site except to answer.

`GET /api/bot/economy/requests?status=pending` -> `{ "requests": [ {"id":"abc123", "login":"zed", "action":"loan_take", "amount":300}, ... ] }`
- `id`: `[A-Za-z0-9_-]{1,64}`, unique per request (the Host decides each id exactly once; a retry or a restart never applies a loan twice).
- `action`: `loan_take` (amount > 0) or `loan_repay` (amount > 0 = that much, `0` = repay everything it can).

`POST /api/bot/economy/answers` `{ "id":"abc123", "status":"done"|"rejected", "message":"...", "balance": 340, "owed": 300 }`
- `message` is a short human line ("borrowed 300 points; interest 5% each stream..." / "you need 1 hours of watch time before the bank lends to you ..."); show it as is.
- Answer HTTP 200 once stored. 5xx/429/no answer: the Host retries every poll. If the request still shows as `pending` after an answer, the Host sends the same answer again (up to 20 times); flip it to answered/closed on your side when you get the answer.
- 401 = the key is refused: the Host reports it in `/api/site/status` and stops.

Rules the Host enforces (so the page can just show the reason): loans on, one open loan per person, watch time >= `LoanMinWatchHours`, amount <= `maxLoan` (= min(`LoanCap`, hours watched x `LoanPerHour`)), an overdue loan blocks new loans until repaid. Interest is added once per stream (`LoanInterestPct` of the principal). After `LoanDefaultStreams` streams the loan is `defaulted`: interest stops, new loans stay blocked, nothing else happens to the person.

## 3. Endpoints on the Host itself (Suite app / tests; local only)

- `GET /api/economy/me?login=` -> the view above
- `GET /api/economy/depreciation` -> `{on, dryRun, pct, threshold, basis, people, total, top:[{login,balance,loss}], stream}` (what the next end-of-stream would take; charges nobody)
- `POST /api/economy/loan` `{action:"take"|"repay", login, amount, id?}` (id makes a retry apply once)
- `GET/POST /api/economy` settings: `POST {settings:{DepreciationDryRun:false}}` switches depreciation from practice to real. Settings live in `Data\economy\settings.json`.

## 4. Depreciation, in one paragraph (for the page's explanation text)

Once per stream, when the stream ends, anyone holding more than `DepreciationThreshold` (100,000) loses `DepreciationPct` (2.5%) of their balance (`basis:"total"`) or of the part above the threshold (`basis:"excess"`, never taking them below the threshold). Bots, the streamer and listed accounts are exempt. A viewer over the threshold gets one personal reminder line in chat per stream (not when they opted out of being named). It starts as a **practice run** (`dryRun:true`): the Host logs what it would take in `Data\economy\depreciation.log` and the Master View backend feed, and takes nothing, until Ivan switches `DepreciationDryRun` off.

## 5. Where points come from now (one door)

Everything moves through `Economy.Award(login, amount, source, note, id)`: one ledger line per movement with the balance after. Finished PinguinoBot matches pay the roster for playing and the winners for winning (`customs`, `comp`, `cas` amounts above). See `Docs\ECONOMY_EVERYWHERE.md` for the rest of the places that must use the same door.

## 6. Points-page shape (05's `GET /api/points`, `POST /api/points/loan`)

The pushed `<view>` (section 1) and the Host's `GET /api/economy/me` / `GET /api/points?login=` now ALSO carry the page's shape, so the site can serve a view as is. Old fields are unchanged; these are additions:

| page field | where in the view |
|---|---|
| `balance`, `rank` | same |
| `players` | = `of` (how many non-bot holders) |
| `depreciation` | `{threshold, ratePct, nextAmount, nextAt}` added next to the old keys (`pct`, `amount`, ...). `nextAmount` = what this person would lose at the next stream end. `nextAt` is `null` (the Host does not know the end time of a stream); `nextAtKind` is `"end_of_stream"` while a stream is open, else `"next_stream_start"`: show "at the end of this stream" / "after the next stream". `dryRun:true` = practice run, nothing is taken. |
| `loans` | `{maxLoan, ratePct, items:[{id, principal, owed, at}]}` added (at most one open loan: `id` = `loan-<login>`, `at` = unix seconds taken) |
| `earned` | `[{source, label, points, wins, games}]`, biggest first. Customs / competitive / casual play+win are folded into one row each (`source` `customs`, `comp`, `cas`; `games` = matches played, `wins` = matches won, `points` = earned from both); every other source is its own row (`wins` 0, `games` = number of ledger lines). |
| `ledger` | `[{at, source, label, delta, balance, note, id}]`, newest first (`label` added) |

`POST /api/points/loan {action:'take'|'repay', amount}` on the Host (local) = `POST /api/economy/loan` (`login` is needed there because the Host never sees a viewer's token). From the site the loan still travels through the request queue of section 2 (`loan_take` / `loan_repay`).

**Depreciation basis (confirmed):** 2.5% of the WHOLE balance (`basis:"total"`) for anyone above 100,000; `basis:"excess"` (only the part above 100,000) is a setting but not the default.

## Who speaks: PinguinoB0t = utility, ChattyPinguino = personality (decided 2026-10-23)
- **PinguinoB0t** = utility only: queue/customs, song requests, `!rank`, `!points`, mod tools, raids/alerts, info, vote skip.
- **ChattyPinguino** = all personality: gambling and games results, fun, banter.
- The **economy engine stays in the Host** (`HostGamble.cs`, Economy): bets, Spend/Credit, cooldowns, validation, duel state. It is the source of truth.

### `PgGame` event (Host -> Chatty)
One event per finished game action, forwarded like the other Twitch events (event type `PgGame` in the Host's forward list). Chatty turns it into ONE short line (no AI call). Args:

| arg | meaning |
|---|---|
| `kind` | `gamble`, `slots`, `duel`, `give` |
| `outcome` | `win`, `lose`, `jackpot`, `challenge` (duel offered), `declined`, `expired`, `broke` (balance 0), `invalid` (needs `reason`) |
| `user`, `display` | the player (login, display name). For a duel result `user` = the winner, `opponent` = the loser; for a challenge `user` = challenger, `opponent` = challenged |
| `amount`, `payout`, `balance` | stake, total paid out (stake included, as the Host credits it), balance after |
| `reel` | slots only: the three symbols as real Unicode emoji, e.g. `🍒 🍋 🔔` (UTF-8, no text codes) |
| `reason` | for `invalid` / `expired`: the Host's own plain sentence, shown after the name |
| `currency`, `timeoutSec` | currency name; duel accept window |
| `optout` | `1` for a viewer who opted out: plain result, no banter |
| `gameId` | unique per action; Chatty drops a repeated id (dedupe) |

**One reply guarantee:** the Host decides who posts, before sending. It sends `PgGame` only when Chatty can post (`chat_settings.json`: `Enabled` and `ChatReplies` and `GameVoice`); otherwise it says its own plain line as before. It never does both. Chatty also gives a plain result only (no banter) in a heated chat, and the shared 30 s duplicate guard stays on every send path. Chatty does not check IsLive for `PgGame` (the Host already decided).

Slots symbols (`slotsSymbols` in `Data\economy\gambling.json`) should be real emoji, e.g. 🍒 🍋 🔔 ⭐ 7️⃣ 💎 🐧, with 🐧 as `slotsJackpotSymbol`.
