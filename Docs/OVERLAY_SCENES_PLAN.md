# Full-screen overlay scenes - plan / contract (draft for 00, 03)

Ask (Ivan): ONE OBS browser source for 1920x1080 (horizontal) and ONE for 1080x1920 (vertical), each holding all current overlays as placeable widgets, with a layout editor and saved layouts. The 800x600 alerts overlay stays. Existing standalone overlays keep working unchanged.

## Design in one paragraph
A new page `scene.html` (the "stage") reads a saved layout and puts every widget in an `<iframe>` of the existing standalone overlay page (same OverlayServer, port 8770, no X-Frame-Options/CSP so framing works). Each iframe has a design size, is scaled/placed by CSS transform, and keeps polling its own data exactly as today. So no overlay is rewritten, standalone use in OBS still works, and `overlay-options.js` keeps working inside each widget. `scene-editor.html` edits the layout on a canvas. Layouts are JSON served by the Host.

## Pages
| Page | Size | Purpose |
|---|---|---|
| `scene.html?profile=h` | 1920x1080 | stage, horizontal OBS source |
| `scene.html?profile=v` | 1080x1920 | stage, vertical OBS source |
| `scene-editor.html` | any browser tab | drag/resize/snap editor, live preview, save/load/activate layouts |
| alerts (03) | 800x600 | stays its own source; also offered as a widget (iframe, same contract) |
Optional `?layout=name` overrides the active layout (for testing); no param = the profile's active layout.

## Widgets (v1)
| id | iframe src | design size | notes |
|---|---|---|---|
| queue | queue.html | 560x720 | idle leaderboards + queue card; self-hides when idle/active logic says so |
| players | players.html | 1920x1080 | full-canvas today: widget is scaled to the box; h profile default |
| players_vertical | players_vertical.html | 1080x1920 | v profile default |
| subroll | subroll.html | 1920x1080 | credits/roll; scaled to box |
| wheel | wheel.html | 1920x1080 | takes over (high z, can be set "takeover" = hidden until it has something to show) |
| alerts | 03's page | 800x600 | placeable like the rest |
Widget record: `{id, src, x, y, w, h, scale, z, visible, opacity, params:{query string}, takeover}`. New widgets later = add one row to a registry (`/api/scene-widgets`), no stage code change.
Design sizes above are my first guess from the current files; I verify each when phase 1 starts, and 03 confirms the alerts size.

## State sharing
No shared bus needed in v1: each widget polls what it polls today (live_state.js, /api/queue-idle, /api/subroll, /api/wheel/public). The stage only passes `?scene=1&host=...` so a widget may skip its own safe-area options when embedded. Phase 3 (optional): the stage fetches once and pushes via `postMessage` if polling load matters.

## Layouts (storage + API, Host side)
- File `Data\runtime\scene_layouts.json`: `{profiles:{h:{active:"default", layouts:{name:{widgets:[...], bg:null, updated}}}, v:{...}}}`.
- `GET /api/scene-layouts[?profile=h][&js=1]`, `POST /api/scene-layouts` (token or same-origin, like overlay-options): save/duplicate/delete/rename layout, set active. Values validated and clamped; unknown keys dropped.
- Stage re-reads every 5 s (as overlay-options does) so activating a layout switches live in OBS. A first-run default layout per profile is generated from the current overlay positions so nothing changes visually until someone edits.
- Chat/hotkey switching later: `!layout name` (mod) and a Suite button via the same POST.

## Editor
Canvas scaled to the browser tab with the real stage size; drag, resize handles, numeric fields, z-order, show/hide, snap to grid/safe area (reuses the 5%/10% guides), per-widget scale, live preview with `?preview=1&mock` data, undo, save as / duplicate / delete / activate, profile switch h/v. Embeddable in the Suite app by 01 (it is just a page).

## Phases
1. Host: `HostScenes.cs` + routes + tests (`test-host-scenes.py`), generated default layouts. Stage `scene.html` rendering widgets from a layout, h and v profiles. (me)
2. Editor `scene-editor.html` with save/load/activate. (me)
3. Alerts widget wired with 03; per-widget polish (takeover for wheel, queue idle visibility); optional postMessage bus; `!layout` command; Suite embed (01).
Each phase: committed locally, tested in the browser pane at 1920x1080 and 1080x1920, no restart/push without 00. Never goes live in OBS.

## Who does what
- 023 (me): Host API, stage, editor, tests, docs.
- 03: alerts overlay page URL + size + whether it can be framed (no X-Frame-Options), and any priority/takeover rules for alerts vs other widgets.
- 01: optional Suite panel embedding the editor + layout picker.
- 00: approve plan, restarts, OBS source setup (two browser sources pointing at scene.html).

## Open questions
1. Do players/subroll/wheel stay full-canvas widgets scaled into a box, or should the editor also let players be arranged as sub-parts (e.g. only the team cards)? Proposal: whole-page widgets in v1.
2. Should the 800x600 alerts source be framed inside the scenes by default, or only exist standalone (so alerts keep their own OBS audio/duck behaviour)? Proposal: standalone stays the default; widget optional.
3. Layout switching by chat command in v1 or later? Proposal: later.
