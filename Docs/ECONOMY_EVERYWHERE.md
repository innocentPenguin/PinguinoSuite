# Economy everywhere: every place points move

Rule: points move ONLY through `Economy.Award(login, amount, source, note, id)` (positive = give, negative = take, refused when the balance is too low). `Economy.Spend/Credit` are thin wrappers over the same door. One ledger line per movement: who, when, source, amount, balance after, a note. Pass a stable `id` (e.g. `quiz:<round>:<login>`) whenever a retry or a restart could repeat the call: the same id applies once.
"Our" points only. Twitch channel points (redeems, predictions, polls) are Twitch's and are not touched here.

Status: **DONE** = goes through the door today, **NEXT** = to wire (owner in brackets), **N/A** = not our points.

| # | Place | Status | Source key | Suggested amounts (all settings, never constants) | Notes |
|---|---|---|---|---|---|
| 1 | PinguinoBot matches: customs / competitive / casual play + win | **DONE** (29dc7df) | `customs_play/_win`, `comp_play/_win`, `cas_play/_win` | CustomsPlay 5 / Win 10, CompPlay 10 / Win 25, CasPlay 5 / Win 15 | Host reads `matches.json`, pays each finished match once (`match:<id>:play|win:<login>`). History before the first run is not paid. `viewers`, `koth`, FN modes count as customs. A winner fixed later (`!matchwin`) does not claw back the earlier payment. |
| 2 | Passive watching (1 point/min, sub/VIP multipliers, activity bonus) | **DONE** (old loop) | `watching` (shown from the earned total) | `PointsPerMinute` etc. | Not one ledger line per minute on purpose (thousands of lines); the page shows it as its own group. |
| 3 | `!gamble` / `!bet` stake and win | **DONE** (ledgered via Spend/Credit) | `gamble` | stake = viewer's choice | Source is derived from the reason text; move to explicit `Award(..., "gamble", ...)` when HostGamble is next touched [02]. |
| 4 | `!slots` | **DONE** (ledgered) | `slots` | - | same |
| 5 | `!duel` (stakes, win, refund) | **DONE** (ledgered) | `duel` | - | same |
| 6 | `!give` between viewers | **DONE** (ledgered) | `gifts` | - | Both sides get a line. Design for real lending: `Docs\ECONOMY_CONTRACT.md` section "Viewer lending (design)" below. |
| 7 | Welcome bonus (first-ever message) | **DONE** | `welcome` | WelcomeBonus 100 | one per login (`welcome:<login>`) |
| 8 | Hidden shop (buy chatty, guess the chatter) | **DONE** | `shop` | site-set prices | ids `shop-<site id>` |
| 9 | Loans: take / repay / interest | **DONE** | `loan`, `loan_repay` | see settings | interest is debt, not a points movement |
| 10 | Depreciation | **DONE** (practice run by default) | `depreciation` | 2.5% over 100,000 | `depr:<stream>:<login>` once per stream |
| 11 | Mod/streamer grants (`!addpoints`, `!removepoints`, Suite grant) | **DONE** (Grant) / `!removepoints` uses Adjust (no ledger line yet) | `grant` | - | NEXT: make `Adjust` write a ledger line too [02] |
| 12 | Song requests (Spotify module) | **N/A for channel points**; NEXT if Ivan wants a points price | `song` | e.g. SongCost 50 | The module answers `/api/chat-command`; to charge points, call `Economy.Award(user, -cost, "song", title, "song:"+msgId)` before queueing and refund on `refund:true` with the same id + `-refund` [02 + Spotify module owner]. |
| 13 | Firsts (first chatter of the stream) | **NEXT** | `first` | FirstBonus 25 | hook where the Firsts feature decides the winner; id `first:<stream>:<login>` [02] |
| 14 | Streaks (watch streaks) | **NEXT** | `streak` | StreakBonus 10 per milestone (3/7/14/30 streams) | id `streak:<login>:<days>` [02] |
| 15 | Polls | **N/A** (Twitch polls spend channel points). NEXT: a participation bonus for our own `!poll` votes | `poll` | PollVote 2 | optional |
| 16 | Predictions | **N/A** (Twitch). Optional: our own `!predict` winners | `prediction` | - | only if Ivan wants it |
| 17 | Wheel (tournament wheel, `!me`) | **NEXT** | `wheel` | WheelEntry 0, WheelWin 50 | pay the picked player; id `wheel:<session>:<login>` [02 Core + 05 site] |
| 18 | Tournaments (finals, placements) | **NEXT** | `tournament` | 1st 500 / 2nd 250 / 3rd 100 (setting) | on the final bracket result [02 + 05] |
| 19 | Quizzes / trivia / guess games | **NEXT** | `quiz` | QuizWin 20 | id `quiz:<round>:<login>` [Chatty/02] |
| 20 | `!8ball` | **N/A** (no stakes). Optional cost 1 | `8ball` | - | skip unless it becomes a sink |
| 21 | Raids (raiders arriving, raid train) | **NEXT** | `raid` | RaidJoin 10 per raider, once per raider per day | id `raid:<raider>:<date>` [02] |
| 22 | Bits (cheers) | **NEXT** | `bits` | BitsPoints 1 per 10 bits | id `bits:<eventId>` [02] |
| 23 | Subs and gift subs (new, resub, gifted, gifter) | **NEXT** | `subs` | Sub 500, Resub 250, GiftSub 300 to the gifter | id `sub:<eventId>` [02] |
| 24 | Follows | **NEXT** | `follow` | FollowBonus 50, once per login | id `follow:<login>` |
| 25 | Stream-end depreciation sink: what happens to the taken points | decided: they vanish (a sink) | - | - | if Ivan wants a prize pool, `Award` a pot account instead |

## Wiring checklist for a new place
1. Add the source key and a label to `Labels` in `HostEconomy2.cs` (the Points page shows the label; unknown keys still show raw).
2. Add the amount to the `Phase2Defaults` list (so it is a setting, listed in `PublicSettings()` if viewers should see it).
3. Call `Economy.Award(login, amount, "source", "human note", "stable-id")`. Check the return value: `null` = done (also when that id was already applied).
4. Add one check to `Tools/test-host-economy2.py` (ledger line with the right source, a replay pays once).

## Viewer lending (design only, nothing built)
- Command: `!lend @user <amount> [for <n> streams]`; the borrower must answer `!accept @lender` within 2 minutes (chat shows one line each way; nobody is charged until the accept).
- Money moves with two `Award` calls (`lend:<id>` from lender, to borrower) so the ledger shows it for both, source `lend` / `lend_repay`. Same hard limits as the bank loan: borrower must have >= LoanMinWatchHours, amount <= lender's balance and <= LendCap (e.g. 2,000), at most 2 open lends per person, no lending to yourself/alts (alias map) or to bots.
- Interest: none by default (lender may add up to LendMaxInterestPct, say 10%, fixed once at the accept). Repay with `!repay @lender [amount]`; the bank `!repay` stays for the bank loan.
- Default: after LendDefaultStreams (e.g. 10) the debt is flagged overdue; no automatic punishment, no clawback; the borrower cannot take a new bank loan or lend until it is repaid. The lender can `!forgive @user` at any time.
- Depreciation interaction: lent points belong to the lender's balance until accepted, then to the borrower's; the debt itself is not a balance, so lending out is a legitimate way to stay under the threshold (intended: "spend, gamble or lend").
- Site: the Points page shows "lent / borrowed" from the same ledger sources; accept/forgive buttons would use the existing request queue (`lend_accept`, `lend_forgive` actions).
