# Master View (in the app) - 2026-10-21, session 013

The website's staff Master View (`/mod/master`) as a native Suite page that talks **straight to the Host on 127.0.0.1:8770**: no website, no core hop, no round trip through Cloudflare. Penguino orange/dark only.

## Files (all new, nothing of the shell is edited)
| File | What |
|---|---|
| `App/src/master/master.html` | page fragment (own document, links `../theme.css`) |
| `App/src/master/master.css` | compact 25 px OBS-style rows, dark inputs, no white boxes |
| `App/src/master/master-core.js` | pure logic + transport (store, optimistic, row builders, SSE parser, poller, API client, keyed DOM reconcile). UMD: tested in node |
| `App/src/master/master.js` | UI wiring |
| `Tests/master/run.mjs`, `mock-host.mjs`, `fixtures/*.json` | node harness, mock Host (serves recorded real answers from 2026-10-21, mutable OBS state, SSE), `node Tests/master/run.mjs` |

## Integration hook (agreed with 01; see the notes below for the final state)
Nav entry `Master View` (route `master`) = a full-size `<iframe src="master/master.html">`; pop-out = `PGWin.open({label:'master', url:'master/master.html?popout=1'})`. The page reads the core token itself (`window.__TAURI__.core.invoke('core_config')`, also tried on `window.parent`) and sends it as `Authorization: Bearer` on writes. CSP already allows `connect-src http://127.0.0.1:*`. `?host=http://127.0.0.1:PORT` points it at another Host (used with the mock).

## Responsiveness design
- **Click feedback is synchronous** (measured 2-3 ms in the browser pane): an optimistic override (`createOptimistic`, 2.5 s ttl) flips the scene / eye / command switch before the request leaves. The override is dropped when the Host's own data agrees, when the request fails (rollback + toast with the Host's error) or when it times out.
- **Diffed DOM**: every list is rendered through `reconcile()` (keyed, reuses nodes, patches only rows whose data changed; 500 rows with one toggle costs <2 ms). Event delegation, one listener per list. Poll-driven renders coalesce into one per tick; polls whose data is unchanged do nothing (`store.set` deep-compares).
- **Transport**: SSE `GET /api/events` (fetch stream, so abort + Last-Event-ID work, backoff 1 s...30 s) *plus* polling that is fast without SSE (OBS tree 450 ms, customs 1 s, wheel/activity 1.5 s, chat 0.8 s, status/obs-status/live 2 s) and slows to 4-6 s as a safety net while SSE is connected. One request in flight per poller, never overlapping; paused when the window is hidden, kicked on focus. Commands/Overlays tabs only poll while open.
- **Cache**: last tree + customs state are kept in localStorage and painted before the first request returns; when OBS or the Host is away the last scenes stay (greyed) under an offline banner.
- **Scene switch** also fetches the new scene's sources in parallel with the switch and remembers the last items of every scene (no empty flash).
- The header pill shows the link: `push 6 ms` (SSE) or `poll 3 ms` plus the average round trip.
- Never sends a chat line twice: the same command text within 1.2 s is dropped; risky buttons (clear queue, end match, wheel reset, delete overlay) need a second click.

## What the page shows / does
| Area | Source | Notes |
|---|---|---|
| Scenes (folders, LIVE highlight, collapse, search) | `GET /api/obs/tree`, `POST /api/obs/scene {scene}` | click = go live; Ctrl+click = view only |
| Sources (nested groups, eye toggle, search) | `GET /api/obs/tree?scene=`, `POST /api/obs/item {scene,itemId,enabled}` | right-click / chevron folds a group; children of a hidden group are dimmed |
| Header pills: live, OBS, recording, replay buffer, chat/EventSub, link | `/api/live`, `/api/obs/status`, `/api/status` | |
| Customs buttons (open/close/clear, next, balance, reroll, fill, end match, wins, KOTH, mode/size/game mode/casual, kick) | `POST /api/run {text:"!queue open", user:"broadcaster"}` | exactly the chat commands the website's `MOD_ACTIONS` allows, allow-listed in `customsText()` |
| Customs queue list / match / mode | `GET /api/customs/state` | **missing in the Host** (asked 02); shows a note, buttons still work |
| Wheel spin / new round / reset | `POST /api/wheel/spin\|new\|reset`, `GET /api/wheel/public` | |
| Feed: activity events | `GET /api/activity?since=` | |
| Feed: live chat | `GET /api/chat/recent?since=` or SSE `chat` | **missing in the Host** (asked 02) |
| Commands on/off | `GET /api/commands/profiles`, `POST /api/commands/profile {id,enabled,by}` | optimistic switch |
| Overlay folder (list, open in a window, copy URL, rename, delete -> trash) | `/api/overlays`, `/api/overlays/rename`, `/api/overlays/delete` | |
| Overlay chat | `/api/overlaychat/status\|ask\|apply` | Host has it switched off today (no key / `enabled:false`): the box says so |

## Keyboard
`/` search - `Esc` clear - `Alt+1..9` scene N - `Up/Down` move - `Enter` scene live / fold - `Space` or `E` toggle source - `[` `]` or `Tab` switch list - `Shift+N` next match, `Shift+O` / `Shift+C` open / close queue, `Shift+S` spin wheel - `1..4` side tab - `?` help.

## Host contract: DELIVERED by 02 in Host commit `b9fad8f` (live after the Host module restarts)

`/api/events` (SSE, snapshot with activity+chat), `/api/customs/state` (`gameMode`), `POST /api/customs/mod {action,value}` (returns state + `ran`; page falls back to `/api/run` on 404), `/api/wheel/state`, `/api/chat/recent` -> `{ok,seq,messages}` (chat `ts` in ms, converted by the page). Nav entry: 01's route `master`, pop-out `pop-master` (needs `Rebuild-App.bat`). Still missing on the Host: OBS stream/record/replay-buffer controls and a `streaming` flag on `/api/obs/status`.

Original wish list (kept for reference; the page works without any of it):
1. `GET /api/events` (SSE, loopback, `retry: 1000`, 15 s heartbeat comment, `id:` per message, `Last-Event-ID` resume). First message `snapshot` = `{obs, obsstatus, live, customs, wheel, chat[], activity[]}`. Then `obs` (same shape as `/api/obs/tree`; invalidate the 2 s tree cache on obs-websocket events so changes made in OBS itself show at once), `obsstatus`, `live`, `customs`, `wheel`, `chat` {seq,user,display,text,ts}, `activity` (one `/api/activity` item).
2. `GET /api/customs/state` -> `{open, activity, mode, format, gamemode, casualStyle, koth, queue:[{username,display,mmr}], match:{id,status,orange,blue}|null}`.
3. `GET /api/chat/recent?since=&limit=` -> `[{seq,user,display,text,ts}]`.
4. `/api/obs/status` is missing the OBS **stream** output state (`streaming`) and there are no start/stop record, start/stop stream or save-replay endpoints, so those are read-only pills today.
5. `/api/wheel/spin|new|reset` return only `{ok}`; returning the new wheel state would save one poll.

## Stubbed / not done
No OBS recording/stream/replay *controls* (no Host endpoint). No source reorder / lock. Overlay file *editing* is not in the page (the overlay chat covers changes). Chat sending is not offered (`/api/say` needs the module token by design). Scene folders come from the Host's prefix/override logic only.

## What needs a rebuild
`App/src/**` is new: **one `App\Rebuild-App.bat` (shell only)**, after 01 adds the nav entry. No core rebuild. Host additions (SSE etc.) need only a Host module restart.

## Test
`node Tests/master/run.mjs` (26 tests: row builders, folders, groups, search, optimistic/rollback, customs allow-list, SSE parser + reconnect + Last-Event-ID, poller, reconcile cost, round trip against the mock). Visual check: `python -m http.server 8799 --bind 127.0.0.1` in `App/src`, `MOCK_OPEN=1 node Tests/master/mock-host.mjs 8798`, open `http://127.0.0.1:8799/master/master.html?host=http://127.0.0.1:8798`. The real OBS was never toggled; the one-off live fixtures were read with GETs only.

## Live verification (2026-10-21, Host b9fad8f, read-only)

Against the running Host (GET only, writes stubbed): 18 scenes/17 sources, SSE push 17 ms, customs queue + `gameMode`, wheel, 30 feed events, commands and overlays tabs all load; view-only scene click and search work. Chat rendering (ms to s timestamps) and the optimistic scene click (3 ms visible, rollback on refusal) were checked against the mock in a real browser. Writes with the Tauri token can only be exercised inside the app; outside it the Host answers 401 and the page rolls back with a toast, as designed.

## Layout v2 (Ivan's redesign)

Scenes and Sources are ONE column split 50/50 (`#col-obs`); the side pane (Customs / Feed / Commands / Overlays) takes all remaining width and height. Customs is categorised like the website (Activity, Queue, Next match, Match, Teams, Settings, KOTH, Players, Wheel) in a multi-column flow, colour coded: green open/Fill/In, red close/clear/kick/destructive (two-click confirm), orange/blue team results and "stays", Activity red with the live one ringed. Mode / size / game mode / KOTH are one-click segmented buttons; the current one is greyed (`.cur`). Orange/Blue wins are disabled with no live match; the Manual pick row shows only in Manual mode. Control bar: any control click takes control at once (the Host runs actions as the broadcaster, so there is no lock step); it shows `controlHolder` from the Host if one is set, else "you (app)" after a click. New allow-listed actions: `activity` (`rl|fn <name>` or `end`), `pick`, `streamer` (sent through `/api/run`; the Host's `/api/customs/mod` does not carry them yet).

## Logs (Feed tab)

Chips: All / Chat / Players / Backend / Events. Players = join, leave, kick, strike, removals, team making; Backend = overlay actions, bot actions, errors; Events = Twitch events. Removals that share a `group` (end of a game) fold into one underlined "6 players" row; click to show or hide the names. Team making is one line: `Blue: a, b, c  Orange: d, e, f`, coloured. Search (`/`) filters the log too.

Host contract asked of 02: `X`, the same items pushed as SSE `log`, and a `logs` array in the snapshot (backfilled from history). Until it exists (404), the page builds the Players log itself from customs changes (no history) and logs its own button presses as Backend lines; the feed says so.

Overlays tab: shows a clear "not connected yet: <reason>" note when `/api/overlays` fails, "Loading…" before the first answer, and "No overlay files" when the folder is empty.

Update: 02 delivered the real feed (Host commit `75349e9`): `GET /api/eventlog?kind=players|backend&since=<ms>&limit=` (events `{id, ts ms, kind, type, user, text, group, detail}`, oldest first) plus SSE `playerlog`. The page polls both kinds with `since`, normalises with `normLog`, folds `match_clear` / `removed` / `leave` runs sharing a `group` into "N players", shows `teams` from `detail.blue/orange`, and reds `detail.level == error`. The older `/api/logs` wording above is superseded; the client-side fallback still applies while the endpoint is 404.

## Spotify strip

A bar under the header: now playing (`GET :8771/api/now`, polled every 3 s) and Like / Back / Skip / Ban song 🚫💿 / Ban artist 🚫👤 (`POST :8771/api/mod-action {action}`; the two bans need a second click). It needs the Spotify module to send CORS headers for the app's origin and to accept the app (no module token reachable from the page); until then the strip reads "Spotify module not reachable" and button errors show the HTTP text. `?music=<url>` overrides the module address (tests).

## Docked Spotify player (replaces the strip)

Fixed bottom-right card (`#player`, shrinkable with the – button, remembered). Shows cover, title, artist, album, progress, requester; buttons: like, previous, play/pause, next, ban song, ban artist (ban buttons are two-click armed, no confirm/prompt). Data: `GET /api/state` (+ `/api/now` fallback) on 127.0.0.1:8771, every 2.5 s.

- Like/prev/skip/bans: `POST /api/mod-action` (tokenless from tauri origins).
- Play/pause, volume, device switch: `POST /api/control {action: resume|pause|volume|transfer}`. Needs the same tauri-origin exemption as `/api/mod-action` in the Spotify module; otherwise the click toasts an error.
- Volume menu (🔊): **Stream** = the Spotify Connect device (slider = device volume, Device button lists `/api/devices` and transfers). **Me** is shown disabled with a note: a second independent output needs OBS per-source monitoring, not built.
- Cover art loads from `i.scdn.co`; the Tauri CSP has `img-src 'self' data:`, so art shows only after `https://i.scdn.co` is added to `img-src` (falls back to a ♪ tile until then).

## Customs: drag and drop + strikes

- **Drag and drop** (queue rows and in-game rows are draggable): queue → queue = `!move <user> <pos>`; queue → Orange/Blue = `!in <user> <team>` (refused client-side if the team is full or no game runs); team → other team = `!in`; team → queue = `!out <user>` (+ `!move` to the drop position). In-game ✕ = `!out` then `!kick`. All go through `/api/run` as broadcaster (these chat commands exist in the bot); the simulator does the same moves locally.
- **Strike chip** on every row: three marks, perma = red, temporary = yellow, half = dim yellow ½, unused slot = gray. Click opens a popover: ✕ cancel, `+ I` temp (`!strike @u`), `+ I perma` (`!strike @u perma`), `−` (`!unstrike @u`, temp first, then `!unstrike @u perma`). `+` buttons are grey with an orange hover outline, `−` is red outlined with a red glow.
- **Data**: the chip reads `customs.strikes[<lowercase user>] = {temp, half, perma}` (+ optional `strikeLimit`, default 3). The Host does not send this yet (asked 02); until then the app keeps a local tally per player so the chip still moves, and the title says counts are unknown.

## Simulator chat, activity defaults, streamer row

- **Simulator chat**: the sim posts its events to `POST /api/customs/sim-say` with `speak:true` (join/leave/kick/queue_open|close|clear/match_start/result/koth_stays/koth_wait), in order, after each action. The "Chat: ON/OFF" button in the sim panel (default ON, remembered) switches it; OFF sends nothing. Blocked (30 s duplicate guard) and errors show as toasts; a Host without the route shows one toast. Kill switch on the Host: `Data\sim_say.json {"enabled":false}`. The sim's "Waiting for players" state stays local (no event for it).
- **Activity defaults**: one table `ACTIVITY_DEFAULTS` in `master-core.js` (competitive = 2v2 + KOTH off + balanced; KOTH = 1v1 + KOTH on; others KOTH off). Choosing an activity sends `!activity ...` and then only the Host commands that differ (`!koth on|off`, `!format`, `!mode`, see `activityPlan`); leaving KOTH restores the old team size. The buttons highlight the target at once (5 s overlay) and the simulator applies the same table. The Host's `!activity` does not do this itself (asked 02 to move it server-side).
- **Streamer In/Out** is a single compact row between Activity and Queue (same `!streamer in|out`).
