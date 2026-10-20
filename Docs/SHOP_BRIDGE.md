# Item Shop bridge (site <-> Host) — FINAL contract

Owner: 05 (PinguinoSite). Code: `PinguinoSite/worker/shop.js`, defaults `content/shop.json`, page `pages/shop.html`.
The site is **outbound-only**: it never calls the Host. The Host pulls requests and pushes results/config with the bot key
(`Authorization: Bearer <BOT_API_KEY>`). The site is advisory only; **the Host is authoritative** (re-check balance, cooldowns and limits, take/pay pengs).

Site login = Twitch login = Host login (lowercase).

## The `shopOpen` flag
`/shop` and `/api/shop/*` are HIDDEN: no nav/sitemap/robots/help link, `noindex,nofollow`. They return the normal 404 unless `shopOpen` is on
(owner sets it via `POST /api/site-config {shopOpen:true}`; **default OFF**; never in the public config). Owner can preview while closed but cannot buy.

## 1. Balance source (either works)
Preferred: no extra push. Balance = the viewer's `points` from the points board the Host already pushes via `POST /api/bot/boards`: `boards.users[login].points`, `boards.aliases[alias] -> main` resolved.
Optional: `POST /api/bot/balances {"balances":{"viewer1":1234},"replace":false}` -> `{"ok":true,"count":N}` (logins `[a-z0-9_]{2,25}`, ints 0..1e12, max 5000/push, merges unless `replace:true`). A pushed value wins over the points board.
Display only; "You have N pengs" is shown only when a balance is known.

## 2. Site request record (what the Host receives)
```json
{ "id": "ab12cd34", "login": "viewer1", "item": "guess-the-chatter", "title": "Guess the Chatter",
  "stake": 200, "at": "2026-10-20T20:00:00.000Z", "status": "pending" }
```
`item` is the site item id (`guess-the-chatter`, `buy-chatty`); config accepts either those ids or the short keys `guess` / `chatty`. `stake` is 0 for buy items. One active (pending|accepted) request per user.

## 3. `GET /api/bot/shop?status=pending`
`status` = `pending` | `accepted` | `rejected` | `won` | `lost` | `all` (default pending). Oldest first, max 100.
```json
{ "requests": [ { "id":"ab12cd34","login":"viewer1","item":"guess-the-chatter","title":"Guess the Chatter","stake":200,"at":"…","status":"pending" } ] }
```

## 4. `POST /api/bot/shop/status`
```json
{ "id": "ab12cd34", "status": "accepted|rejected|won|lost", "payout": 400, "note": "It was Bob" }
```
-> `{"ok":true}`. 404 unknown id, 400 bad status, 409 `Already <status>.` on a bad transition, `{"ok":true,"unchanged":true}` if the same status repeats.
Transitions: `pending -> accepted|rejected|won|lost`; `accepted -> won|lost|rejected`; `rejected|won|lost` are terminal. `payout` int 0..1e12, `note` max 200 chars; both are shown as text only.
Economics (Host's job): a 2x win pays net +stake, a wrong guess loses the stake.

## 5. `POST /api/bot/shop/config`
```json
{ "currency": "pengs",
  "items": { "guess": { "min":100, "max":2000, "payoutMultiplier":2, "cooldownUser":1800, "cooldownGlobal":600 },
             "chatty": { "price": 5000 } } }
```
Aliases accepted: `payoutX` = `payoutMultiplier`, `cost` = `price`. -> `{"ok":true,"count":2}`. Full replace. Keys `[a-z0-9-]{1,40}`; numbers are non-negative; `payoutMultiplier` max 1000. `currency` is letters/digits/spaces, max 20.
Used for the UI (price, stake limits, "pengs") and the advisory checks. Fallback defaults when nothing was pushed: `content/shop.json` (min 100, max 2000, 2x, user cooldown 30 min, global 10 min, buy-chatty 5000 once).

## Browser routes (session cookie, same-site JSON)
`GET /api/shop/mine` -> `{open,owner,currency,balance,active,items,requests}`; `POST /api/shop/buy {item,stake}` (409 not enough points / active request / closed, 429 cooldown, 400 stake bounds).
