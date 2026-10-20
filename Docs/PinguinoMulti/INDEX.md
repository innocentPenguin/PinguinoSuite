# PinguinoMulti index (unit 03, port 8766, code in Suite/modules/multi)

## Backend
| File | What | Key parts |
|---|---|---|
| server.py | FastAPI app: REST + `/ws`. INDEX block with section line numbers at the top of the file | OBS (`/obs/*`, `/api/obs/*`), dashboard profiles (`/api/dash*`), `/api/viewers`, `/api/send` (one platform, 30 s duplicate guard, Twitch plain lines via Host say), cards, panes/splits, ding/pop, windows, auth |
| obs.py | OBS widget settings (chat/activity/follow): sanitize, Synchra import/export, `hidden()` filter | `sanitize`, `from_synchra`, `to_synchra`, `hidden`, `IVAN_CHAT` |
| viewers.py | Live viewer counts every 30 s (Twitch Helix, YouTube, TikTok) pushed as WS `viewers` | `run`, `_twitch`, `_youtube`, `_tiktok` |
| host_feed.py | Reads Host `/api/activity` (follow, redeem, mod notices, raid_out, poll, prediction, hype) and says Twitch lines via Host `POST /api/say` | `to_message`, `_live_text`, `say`, `run` |
| pipeline.py | ingest, scoring, NOTICES (event types never ranked) | `NOTICES` |
| store.py | SQLite + kv | `kv_get`, `kv_set` |
| connectors/ | twitch (EventSub), discord, youtube (polling, `video_id`), tiktok (unofficial, room viewers) | `describe()`, `send()` |
| panes.py / windows.py | split panes (flow/platform/events/people), window presets | `/api/splits/apply` |

## Frontend (static/)
- index.html: shell, WS `on()` (hello, message, conn.status, viewers).
- dash.js: dashboard. `renderDash`, `dPanels`, `dFill`, `dFlow` (split flow), `dGifts`, `dViewRefresh`, drag divider, `dSplitWindows`.
- obs.html: the OBS browser source page (chat/activity/follow). obs_ui.js: widget editor (`/?type=obs`).
- chat.js, side.js, launcher.js, style.js: classic chat page, side panel, launcher, chat look.

## Docs
- OBS_WIDGETS.md (widgets, dashboard features), STREAM_READY.md (stream checklist), SITE_SCOPE_PROPOSAL.md.

## Tests
- Suite/modules/multi/tests/test_core.py (82 pytest), tests/e2e_live.py (throwaway server on 8799).
