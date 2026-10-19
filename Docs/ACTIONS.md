# Actions & Events (PinguinoHost)

Streamer.bot-style automation inside the Host. Page: `http://127.0.0.1:8770/automations` (link on the Host page). Data: `Data\runtime\automations.json`, variables in `automation_vars.json`. Only the **master** Host runs them (see HOST.md "Single instance").

## Model
```json
{ "version": 1, "actions": [ {
  "id": "a1b2c3", "name": "Lurk", "group": "Chat", "enabled": true,
  "triggers":   [ { "type": "command", "names": ["!lurk"], "permission": "everyone", "cooldownSec": 30, "userCooldownSec": 0, "consume": true } ],
  "conditions": [ { "left": "{viewers}", "op": ">=", "right": "10" } ],
  "steps":      [ { "type": "say", "as": "core", "text": "Enjoy the lurk {user}!" } ] } ] }
```
An action starts when **any** trigger matches and **all** conditions hold, then runs its steps in order (one run per action at a time).

**Triggers:** `command` (names, permission everyone|sub|vip|mod|broadcaster, cooldownSec, userCooldownSec, consume = the bots do not also answer), `chat` (regex), `first_message`, `follow`, `sub` (tier any|1|2|3), `resub`, `gift` (min), `cheer` (min, max bits), `raid` (min viewers), `redeem` (reward title, `*` = any; needs the `channel:read:redemptions` scope: sign the streamer account in again), `timer` (everySec, minChatMessages), `stream_online`, `stream_offline`, `hotkey` (key; fire it with `POST /api/automations/fire {"hotkey":"brb"}` from Link, Stream Deck or a script), `manual`.

**Steps:** `say` / `random_say` (as core|chat|helper = which bot account speaks), `delay` (ms), `obs_scene`, `obs_source` (show/hide/toggle), `obs_request` (any OBS WebSocket request), `sound` (mp3/wav path, plays on the Host PC), `http` (GET/POST; saves `{http.status}`, `{http.text}` and each JSON field as `{http.field}`; with `say:true` says the answer's `say`), `module_command`, `bot_command` (runs e.g. `!next` as the streamer), `timeout`, `set_var`, `inc_var` (sets `{count}`), `log`, `run_action`, `if` (then/else), `stop`, `comment`.

**Text variables:** `{user} {userName} {message} {args} {arg1}..{arg9} {command} {channel} {isMod} {isSub} {viewers} {bits} {tier} {title} {raider} {var:name} {random:1-100} {now:HH:mm} {count}`.

**Conditions:** `== != > >= < <= contains startswith matches empty notempty true false` (numbers compare as numbers).

## Safety
- `http` / `module_command` only reach this PC, the LAN (10.x, 192.168.x, 172.16-31.x), the tailnet (100.64/10, `*.ts.net`) and `innocentpenguin.com`. The module token is only sent to loopback.
- **Test (dry run)** never sends chat, changes OBS, plays sounds or calls APIs; it shows what would happen. **Run for real** asks first.
- Every run is logged to the Console (module `host`, source `automation`) and shown under "Recent runs".
- 300 steps per run, nesting depth 8.

## Module command contract (Spotify and other modules)
`module_command` does `POST <url>` with `{command, args, user, display, role, isMod, isSub, msgId}` and says the answer's `say`. Reply `{"ok":true,"say":"..."}` (empty `say` = silence). Host owns permissions, cooldowns and the command list; the module owns its logic. Example: a `!sr` command with trigger `command` names `["!sr","!songrequest"]` and a single `module_command` step to `http://127.0.0.1:<port>/api/chat-command`.

## Import from Streamer.bot
Button "Import from Streamer.bot" reads `actions.json`, `commands.json`, `twitch_rewards.json` from the Streamer.bot data folder (found automatically in `Documents\PinguinoB0t\data` or `%AppData%\Streamer.bot\data`, or give `path`). It converts commands (not the ones the bots own), follow/cheer/sub/resub/gift/raid/redeem/stream online-offline triggers and the sub-actions send message, delay, play sound, run action, set argument. Everything arrives **disabled** with a note; C# actions (the Pinguino bots), shoutouts, tags/title/game updates, OBS items etc. are listed as skipped or left as "not converted" comment steps. No keys or prompts are read.

## API (all on the Host port; POST needs the module/app token or same origin)
`GET /api/automations` · `POST /api/automations {doc}` · `POST /api/automations/test {id, dry}` · `POST /api/automations/fire {hotkey}` · `GET /api/automations/log?n=` · `POST /api/automations/import {mode: preview|merge, path?}`. Tests: `python Tools/test-host-auto.py`.

## Twitch steps and new triggers (Streamer.bot replacement)
Sign the streamer in again for the permissions `clips:edit`, `channel:read:ads`, `moderator:manage:shoutouts`, `channel:moderate`.
Steps: `create_clip` {title, duration} (sets `{clip.url}`) · `obs_replay_save` (saves the OBS replay buffer; sets `{replay.path}`; says so honestly if the buffer is not running) · `ad_schedule` (sets `{adIn}`, `{adPrerollFree}`, `{adPrerollSec}`, `{adLengthSec}`, `{adSnoozes}`) · `channel_info` (sets `{game}`, `{title}`) · `shoutout_queue` {user, by, auto} (queue with Twitch card + pronouns, see `shout_settings.json`) · `latest_say` (sets `{latest.line}`) · `append_file` {file, text} (only inside `Data\runtime\files`).
Triggers: `raid_out` (`{target}`, `{viewers}`), `ban` (`{user}` = banned viewer, `{moderator}`, `{reason}`, `{permanent}`). Gift events carry `{total}`.
Presets: group "Streamer.bot replacement", 13 ON and 5 OFF; see `STREAMERBOT_REPLACEMENT.md` section 9.

## Activity and latest feeds (Host)
- `GET /api/activity?since=<seq>&limit=100&type=follow,sub` -> `{ok, seq, items:[{seq, ts (unix s), type, user, amount?, tier?, message?, detail}]}`, oldest first, only items with seq > since. Types: `follow sub resub gift cheer raid redeem ban clip replay shoutout`. Poll with `since=<last seq>`. Kept in `latest.json` (last 500).
- `GET /api/latest` -> newest entry of each kind (+ last 20); OBS overlay `http://127.0.0.1:8770/overlay/latest?types=follow,sub,cheer,raid&color=ff9900&size=64&font=bahnschrift&rotate=5`; `latest_settings.json {"TextSource": "<OBS text source>"}` also writes the newest line there.
- `GET /api/shoutouts` (queue + recent) · `POST /api/shoutouts {"user":"name","by":"who"}`.
Tests: `python Tools/test-host-sbreplace.py` (sim), `python Tools/test-host-obs.py [--start-replay]` (real OBS: popup, ban alert, replay buffer).
