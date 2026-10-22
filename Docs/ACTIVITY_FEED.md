# Activity feed (PinguinoHost)

One persisted list of everything that happens on stream. The Suite shell (Activity page), the "latest" overlay and the website mirror all read it.
Stored in `Data\runtime\latest.json` (last 500, survives restarts, `seq` never goes back).

## Read
`GET http://127.0.0.1:8770/api/activity?since=<seq>&limit=100&type=follow,sub`
```json
{ "ok": true, "seq": 42, "items": [
  { "seq": 41, "ts": 1792425040, "type": "cheer", "user": "eve", "amount": 300, "detail": "300 bits" },
  { "seq": 42, "ts": 1792425061, "type": "sub", "user": "bob", "tier": "2", "detail": "tier 2" } ] }
```
Oldest first; only items with `seq > since`; `type` is an optional comma list. **Live:** poll every 2-3 s with the last `seq` (the Host answers in milliseconds). There is no SSE yet (the Host handles one request at a time).
Types and fields:
| type | meaning | amount | other |
|---|---|---|---|
| follow | new follower | | |
| sub / resub | subscription | | tier 1-3 |
| gift | gift bomb | number of subs | tier |
| cheer | bits | bits | |
| raid | incoming raid | viewers | |
| redeem | channel point reward | cost | detail = reward title, message = what the viewer typed |
| ban | ban or timeout | | message = reason, detail = banned / timed out |
| clip | Twitch clip from !clip | | detail = link |
| replay | OBS replay buffer saved | | detail = file name |
| first5 | First 5 game place taken | place 1-5 | |
| shoutout | shoutout sent | | user = who asked, detail = the streamer |

Events come over Twitch EventSub (a live connection, not polling). `GET /api/summary` shows `eventSubLatency` (median / worst milliseconds between Twitch sending a message and the Host receiving it, measured on every message including the keepalives).

## Other views
- `GET /api/latest`: newest entry of each kind (+ last 20) and the overlay settings.
- OBS overlay `http://127.0.0.1:8770/overlay/latest` (look in `Data\runtime\latest_settings.json`: Types, Color, TextColor, Size, Font, Rotate, Bold, Shadow, ShowDetail, Align, Labels; the URL can override each with `?color=&size=...`; `TextSource` also writes the newest line into an OBS text source).
- Website mirror (off by default): `latest_settings.json` `"ForwardToSite": true`, key = vault name `BOT_API_KEY`. Sends follow, sub, resub, giftsub, cheer and raid (names only) to `POST https://innocentpenguin.com/api/bot/events` in batches every 5 s; event ids are `host-<ts>-<seq>` so retries never duplicate. State in `site_forward.json`; shown in `/api/summary` as `siteForward`.

## Streamer.bot cutover switch
`GET/POST /api/cutover {"on":true}`: the replacement actions that would answer twice while Streamer.bot still runs (alerts, !clip, !preroll, !whyad, ban alert) and the First 5 game stay off until it is switched on. Button "Streamer.bot cutover" on Actions & Events.

## Management endpoints (for the shell)
`GET/POST /api/vars`, `POST /api/vars/delete {name}` · `GET /api/queues`, `POST /api/queues/pause|resume|clear` · `GET /api/automations/triggers` (type, display, fires, lastFiredAgoSec, cooldowns) · `GET /api/automations/hotkeys` · `GET /api/automations/export` · `POST /api/automations/enable {id|group, on}` · `GET /api/endpoints`. Trigger display fields: command = names, redeem = title, hotkey = key, timer = everySec, chat = pattern, sub = tier, cheer/raid/gift = min; `raid_out` and `ban` have none.

`tier` is a string ("1", "2", "3", or "prime" for alerts), the same field the alert engine reads. Compare with `str()`/`String()`.

## Raid prep for raids started on the Twitch website
Twitch only tells the Host about an outgoing raid when it actually goes (EventSub `channel.raid`, then the 20 s delay in `sb-raidout`); the website's "Raid now" click sends no signal. So the Master View **Raid prep** button (`POST /api/raid/prep`, body `{target?}`) is the way to run the raid-start automation early: Ivan presses it when he starts the raid. It runs once per raid (3 min dedupe), so the later automatic detection won't repeat it. Raids started from the Suite app fire it by themselves.

## Recap test
`GET /api/recap/preview` returns the text, `POST /api/recap/test {post:true}` says it in chat once (duplicate-guarded). Both use the last stream's window and end with its best clip.
