# Multi end-to-end pass (2026-10-21 09:37)

Real server process on a throwaway port with a throwaway data folder; nothing audible, no network, no live accounts. Script: `Suite/modules/multi/tests/e2e_live.py`.

**84/84 passed**

| Area | Check | Result | Detail |
|---|---|---|---|
| Core | server starts, /api/status | PASS | 4 connectors |
| Core | connectors declared | PASS |  |
| Core | no platform connected -> Twitch needs_auth (honest) | PASS |  |
| Ingest | messages arrive over WebSocket | PASS | ['hello', 'card.new', 'message', 'message', 'message', 'conn.status'] |
| Ingest | question+mention makes a priority card | PASS |  |
| Ingest | messages stored and listed | PASS |  |
| Ingest | score is explained (reasons) | PASS | ['mention', 'question'] |
| Ingest | duplicate id ignored | PASS |  |
| Cards | card action: snooze | PASS |  |
| Cards | card action: reopen | PASS |  |
| Cards | card action: answer | PASS |  |
| Cards | hotkey dismiss acts on top card | PASS | {'ok': True, 'card': 'c:twitch:dev:1792593414817', 'state': 'dismissed'} |
| Assist | mark to answer creates a card | PASS |  |
| Cards | after-stream recap | PASS |  |
| Cards | streamer-first claims endpoint | PASS |  |
| Chat | search finds a message | PASS |  |
| Assist | chatter card (who is this) | PASS |  |
| Assist | private note saved | PASS |  |
| Chat | mute viewer in ranking | PASS |  |
| Chat | pin a message | PASS |  |
| Assist | quick-reply templates | PASS |  |
| Assist | suggested replies (no AI key -> templates) | PASS | no AI key |
| Assist | translate degrades gracefully without a key | PASS |  |
| Assist | unknown message -> 404 | PASS |  |
| Safety | no broadcast-to-all send | PASS | {'detail': 'choose one platform that supports sending (no broadcast to all)'} |
| Safety | send blocked while Twitch is not connected | PASS | {'detail': 'Host refused (401)'} |
| Safety | mod action refused without the scopes | PASS | {'detail': 'Moderation is not authorised: reconnect Twitch with moderator permissions'} |
| Look | chat look loads defaults | PASS |  |
| Look | chat look saved + validated | PASS |  |
| Look | hostile style values are rejected | PASS |  |
| Look | follow event pushed with the module token | PASS | {'ok': True, 'id': 'evt:twitch:1792593417321'} |
| Safety | event push without a token is refused | PASS | token required |
| Look | stream-safe popout serves | PASS |  |
| Look | style editor page serves | PASS |  |
| Look | follow shown as a styled event, never ranked | PASS |  |
| Dashboard | chat rate + top chatters | PASS | 1.0 |
| Dashboard | aux feed snapshot | PASS |  |
| Sounds | ding off by default, bell sound found | PASS |  |
| Sounds | ding settings validated + saved | PASS |  |
| Sounds | missing sound file refused | PASS |  |
| Sounds | chat pop settings saved | PASS |  |
| Sounds | new-chatter ding plays (silent at volume 0) | PASS | {'enabled': True, 'platforms': ['twitch'], 'scope': 'stream', 'first_ever': False, 'returning': True, 'sound': 'D:\\PinguinoSuite\\Data\\sou |
| Sounds | chat pop plays (silent at volume 0) | PASS | {'enabled': True, 'platforms': ['twitch', 'youtube'], 'sound': 'D:\\PinguinoSuite\\Data\\sounds\\chat-pop.mp3', 'sound_exists': True, 'volum |
| Sounds | new-chatter feed for the bot | PASS |  |
| Secrets | discord token stored write-only | PASS |  |
| Secrets | no secret in /api/setup or /api/settings | PASS |  |
| Console | prestream items all have help | PASS | ['ai', 'conn-discord', 'conn-tiktok', 'conn-twitch', 'conn-youtube', 'ding', 'file-rules', 'file-settings', 'pop', 'queue', 'store', 'window |
| Console | Twitch down is a FAIL, optional ones pass (skipped) | PASS |  |
| Console | integrations items with help + test path | PASS |  |
| Console | integration Test fails honestly when not connected | PASS | {'detail': 'Twitch is needs_auth: Connect Twitch in Settings (Connect Multi)'} |
| Console | help index incl. module overview + secrets | PASS |  |
| Console | console log written, no secrets, valid JSON lines | PASS |  |
| Console | prestream-multi.json fallback written | PASS |  |
| Windows | create a chat window | PASS |  |
| Windows | list windows with monitor placement | PASS |  |
| Windows | update window settings | PASS |  |
| Windows | delete window | PASS |  |
| Windows | built-in layouts include Combined Chat | PASS |  |
| Windows | monitor list | PASS |  |
| Look | 10 ready-made looks listed | PASS |  |
| Look | pick a ready-made look | PASS |  |
| Look | undo goes back | PASS |  |
| Look | save my own look | PASS |  |
| Look | export then import round trip | PASS |  |
| Look | import refuses junk | PASS |  |
| Split | by-platform split makes two panes | PASS |  |
| Split | flow split links the two halves | PASS |  |
| Split | each half keeps its own look (bad keys dropped) | PASS |  |
| Split | changing the split mode keeps each half's look | PASS |  |
| Windows | pop-out position is remembered | PASS |  |
| Split | pane page loads | PASS |  |
| Sounds | chat pop can be limited to roles | PASS |  |
| Sounds | reset sounds to defaults | PASS |  |
| Setup | setup info for the launcher | PASS |  |
| Ranking | explainable rules + defaults | PASS |  |
| Ranking | learning view | PASS |  |
| Ranking | AI usage view (no key: local only) | PASS |  |
| Ranking | voice suggestions disabled by default | PASS | {'enabled': False, 'suggestions': []} |
| Safety | foreign Origin write refused | PASS |  |
| Safety | tokenless writer refused | PASS |  |
| Safety | writer with the module token accepted | PASS |  |
| Safety | non-loopback Host refused | PASS | 403 |
| Performance | 300-message burst handled | PASS | {'in': 305, 'dupes': 1, 'dropped': 0} |
| Performance | queue drained | PASS | 0 |

## 2026-10-23 05:40-06:00, 40 - Multi: first browser look at the alert engine (throwaway server on port 8797, built-in browser)
| Area | Result |
|---|---|
| `/obs/alerts?demo=1&bg=1` at 800x600 | PASS. Cards render, no console errors. |
| 15 new types via `POST /api/alerts/test` (hype_start/level/end, goal_progress, tip, gamble_win, shop, guess, milestone, raid_out, poll, prediction, first_chatter, custom) | PASS. Every card has text (e.g. "Hype train level 3!", "Raiding penguin with 7 viewers!", "penguin guessed the chatter!"); played in priority order, one at a time. |
| loan / give / returning_chatter | PASS. Off by default ("test loan not shown: type disabled"). |
| Shoutout with a clip via `POST /api/alerts/fire` | BUG FIXED (ef540a1). Clip-only card with an unplayable clip URL was an empty box with a progress bar for ~14 s. Now falls back to the name card ("Go check out Pengu_Friend!"). A real Twitch clip URL has still not been seen playing (needs the Host's fire call with a direct mp4). |
| Alerts editor `/?type=alerts` | PASS. All 33 types listed (off ones marked), shoutout panel has clip + rules fields, export/import/duplicate/delete profile, media upload buttons, "what fired" log live. Not exercised: actual file upload, import of a file. |
| `/obs/goal` | PASS. Bar + "42 / 100 (42%)" after `POST /api/goal`. Page only polled, no WS (by design). Added `?bg=1` preview background. |
| Dashboard `/` | PASS as the default window (activity feed + chat, Alerts button). No left nav yet (backlog). |
| Not yet looked at | `?w=1920&h=1080&scale=1.5` and vertical 1080x1920, chat page Sounds section, launcher `/?type=launcher`, scene follow against Link, intros against the real Host. |
Host contract finding: `GET http://127.0.0.1:8770/api/intro` already exists and is the Host's OLD sub-intro video system (returns settings/queue). Viewer intros moved to `GET /api/intro/viewer` (commit 157bdd9); 10 - Bots must implement that path.

## Browser pass 2026-10-23 (worker 41, built-in browser, throwaway server on 8786)

Checked by eye / DOM against the current on-disk code:
- /obs/alerts at 800x600, 1920x1080 scale 1.5 and 1080x1920: cards centred (DOM rect checked), no overflow.
- Cards looked at: hype_start/level/end, goal_progress, poll, prediction, first_chatter, tip, gamble_win, shop, guess, milestone, streak, shoutout (no clip). returning_chatter, loan, give are OFF by default (test says "type disabled").
- /obs/goal: bar fills (63/100 = 63%); /api/goal POST works.
- Editor /?type=alerts: all types listed, shoutout clip + rules fields, queue rules, export -> import round trip (new profile "Penguin 2"), media upload (+ rejects .exe), no console errors from the page itself.
- Dashboard / (Activity Feed + Chat, no left nav yet), /?type=launcher, chat Sounds section: render, no errors.

Bugs fixed:
- Tip alert read "tipped 5 !" when no currency: render() now drops the stray space; test tips carry currency USD.
- Test events for goal_progress / poll / prediction / milestone / shop / guess showed "hello colony" and "0": test_event now has realistic text and amounts per type.

Not covered: shoutout clip playback (needs a Twitch clip host, see item 4), audio.

## Intro + shoutout rehearsal without the Host (2026-10-23, worker 41)

`Suite/modules/multi/scripts/fake_host.py` is a stand-in Host: `serve` answers GET /api/intro/viewer (and /api/intro) with `{text, sound_id, status:"approved"}` and serves a test clip; `shoutout` fires a shoutout with that clip through POST /api/alerts/fire. Run Multi with `MULTI_HOST_URL=http://127.0.0.1:<fake port>` and `MULTI_CLIP_EXTRA_HOSTS=127.0.0.1:<fake port>` (both rehearsal-only; production clip hosts stay Twitch-only).
Result in the browser: a first-time chatter message -> "NewPenguin has arrived / Hi chat, ..." intro card; the shoutout card plays the clip after the 10 s delay with the progress bar, then the clip-only card now fades out with the clip (it used to linger empty).
Finding: Multi asks the Host for `/api/intro/viewer`, NOT `/api/intro` (the plain path is the Host's old sub-intro video system and answers 200 with its settings/queue; that 200 was not a viewer intro). The Host must answer `/api/intro/viewer?platform=&user_id=` with status "approved" for intros to play.

## Full-Host rehearsal, all paths at once (2026-10-23, worker 41, `scripts/rehearse.py`)
Rig: Multi in-process on a throwaway DB (port 8788) + `scripts/fake_host.py` (viewer intros by user-id prefix: ok / pending / link / long / err = HTTP 500 / slow = 4 s), a recorder on the engine's emit, real Host-style `POST /api/alerts/fire`, chat messages injected into the inbox so intros come through the real pipeline. ~4 min, `/obs/alerts` open in the browser pane without `?demo` the whole time. Run it again with `python scripts/rehearse.py` (exits 1 on any problem). Nothing left this PC, nobody went live.

Fired at once: 7-alert mixed burst on a paused queue, 6 first-time viewers (+ a repeat message), 3 shoutouts (webm clip, `.mkv` clip, clip from a disallowed host), hype_start/level/end, tip (+ the same id again), gamble_win, shop, guess, loan, give, 12 follows, an unknown Host type, and the Host stopped for ~15 s in the middle with new viewers chatting.

Result (last run: 23 shows = 23 ends, queue drained, longest idle gap between alerts 0 s beyond a shoutout's own "delay before it plays"):
- Queue order is right: raid (9) > tip/gift/hype_start (8, in arrival order) > sub/hype_level (7) > cheer/gamble (6) > intro/guess (5) > shop/custom (4) > follows (3, merged 4-into-1 while queued).
- No duplicates: the repeated tip id and the doubled intro (two messages from one viewer in the same tick) were dropped as "already fired (replay)". `loan`/`give` log "skipped: type disabled". The unknown Host type plays as "Other event" with the Host's text.
- Intros: approved plays once; pending, link text, 300-char text and HTTP 500 never play; a Host slower than 2.5 s plays nothing (no stall).
- Shoutouts: playable-host clip makes a video card; `.mkv` (not playable) falls back to the name card at once (seen in the overlay DOM); a clip from a disallowed host plays as a plain name card (clip dropped, shoutout kept).
- Overlay: followed every show, never stuck on an old card, text-only cards leave on time.
- Editor feed (`/api/alerts` log): every alert shows queued -> fired, merges and duplicates and disabled skips are listed with the reason.

Defects found and fixed:
1. **A viewer whose first message met a dead/slow Host never got their intro** (the `new` flag only exists on the first message). Now a failed lookup (no answer, not "no intro") puts the viewer on a retry list: their next message after the 60 s cache asks again. Test `test_intro_retries_after_host_outage`.
2. **"Host unreachable" banner when the Host merely answered 404/500**: `host_feed._get` now counts an HTTP error answer as reachable (`up: true`, error says `HTTP 404 on /api/...`). Test added to the host-status test.
3. Rig-only: the stdlib fake Host refused some of 7 simultaneous lookups (listen backlog 5), which looked like a Multi bug until the retry list showed it; the rig now uses a backlog of 128.

Not covered: a truly playable mp4/webm clip (no ffmpeg here; webm playback was checked earlier with a browser-recorded clip), and real Twitch clip hosts (rehearsal env only allows the fake Host).

## Media upload edge cases (2026-10-23, worker 41)
Checked on the real routes with TestClient (`test_alert_media_upload_edge_cases`): oversize (413/400), empty, wrong extension (exe, html, svg, no extension, empty name), right extension but wrong bytes (html named .png, text named .mp3), name collisions (`ding_1.wav`, case-insensitive), traversal (`../../x.wav`, `..\..\x.wav`, `/etc/passwd.wav`, `a/../../b.png`, `..%2f..%2fx.png`: all end up inside the library with a plain name, nothing written outside), delete of a name outside the library or unknown (no file touched).
Fixed: (1) content sniffing so a renamed non-media file is refused; (2) Windows device names (CON, NUL, COM1...) get a leading `_` instead of opening a device; (3) **delete while in use**: an alert type that still points at the file now blocks the delete (`{ok:false,in_use:["Penguin: follow"]}`), `force:true` deletes anyway. The editor has no delete button, so nothing in the UI changes.

## OBS chat / activity / follow overlay pass (2026-10-23, worker 41, built-in browser, throwaway server on 8788)
Pages: `/obs/chat`, `/obs/activity`, `/obs/follow` (+ `?preview=1` test mode). Settings come from the editor (`/api/obs/<kind>`); there are no `?w/h/scale` URL parameters (size is the OBS browser-source size, scale is the `canvas_scale` setting), so none were tested.
- Emotes (real id, bad id like `../../x` falls back to text), badges (moderator/subscriber/vip), 300-char word and a 200-char URL without spaces (wrap, no overflow), Hebrew + Arabic mixed with English, emoji, `<img onerror>` text (shown as text), 80-char display name: all render correctly. Page background is transparent (body and html `rgba(0,0,0,0)`).
- **Zalgo** (60 stacked combining marks) bled into the lines above and below. Fixed: more than 3 stacked marks are cut when text is escaped (real scripts use 1-3). RTL text now sits in its own bidi isolate so it cannot reorder the name and colon.
- **Burst 50 messages/s for ~150 s** (7,300 messages, with emotes and badges): live items stay at `max_messages` (30), the DOM holds steady at ~610 elements (the extra ones are lines fading out for 0.85 s, then 330 once idle), JS heap flat at 2-3 MB, zero long tasks, old lines pruned from the top. No growth, no jank.
- Multi restarted under an open page: the page reconnects every 2 s and now **backfills** messages that arrived during the gap (it used to just resume, so lines sent while Multi was down never appeared). If Multi is unreachable when the page loads its settings, the page now retries with backoff instead of staying blank until someone refreshes the source.
- "Host not reachable": the chat/activity/follow overlays never talk to the Host, so there is no such state; when Multi itself is down the overlay stays transparent and keeps retrying (nothing is drawn on the stream on purpose).
- Activity and follow pages: preview rows and the follow card render, no console errors from them.
- `/obs/alerts`: the console buffer held earlier `segs ... .map is not a function` errors from an alert whose `text` was not a list. Every alert type produces lists in the engine (checked all 33 types with odd inputs), so the source was an old payload; `segs()` now accepts a plain string and ignores anything else instead of throwing, so one bad payload can no longer wedge the overlay.
