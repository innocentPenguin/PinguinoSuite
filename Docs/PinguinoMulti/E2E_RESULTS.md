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
