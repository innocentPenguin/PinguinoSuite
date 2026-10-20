# Site bridges (Host side)

Code: `PinguinoHost/HostSiteBridge.cs` (index in Docs/INDEX.md). Contract with the site: [SHOP_BRIDGE.md](SHOP_BRIDGE.md) (owner 05). The Host only calls out; auth is the bot key (`Boards.SiteKey()`), never logged, always with `User-Agent: PinguinoHost/1.0`.

| Bridge | Poll | Push | Notes |
|---|---|---|---|
| Teach | `GET /api/bot/teach?status=pending` every 30 s | `POST /api/bot/teach/status` | Items go to the Teach inbox deduped by `siteId`; the Host re-checks the author's role (`Roster.RoleOf`) and re-cleans the text. Strangers are rejected on the site. Ivan's approval decides; edited counts as approved. Outbox in `Data/runtime/site_teach.json` (401/5xx retried; 404/400/409 go to `dropped`). |
| Shop | `GET /api/bot/shop?status=pending` | `POST /api/bot/shop/status`, `POST /api/bot/shop/config` | `guess_chatter` (stake, 2x payout) and `buy_chatty`. Pengs move only through `Economy.Spend/Credit` (idempotent by request id, so a restart never double-charges). State in `site_shop.json`; unlock in `chatty_unlock.json`. |

Switches (settings): `SiteTeachBridge`, `SiteShop`. Tuning: `Data/runtime/site_shop_settings.json` (BuyChattyPrice 5000 is an assumption, MinStake/MaxStake, cooldowns, GuessSeconds, MaxGuesses). Status: `GET /api/sitebridge`.
Hidden `!guess <answer>` (not in help or the command list) answers the staker's private round. Lines come from `Data/chat_logs/live`, skipping opted-out and hidden-source users, links, @mentions and sensitive words.
Chatty: random chime only after `buy_chatty` unlocks it (PinguinoChat reads `chatty_unlock.json`).
Tests: `python -I Tools/test-host-sitebridge.py <PinguinoHost.dll>` (fake site, 33 checks).
