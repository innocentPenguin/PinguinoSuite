# Overlays - operator page (Ivan / mods)

All overlays are plain browser sources served by the Host. Base URL `http://127.0.0.1:8770/` (the Host must be running). Nothing here needs OBS to go live to be checked: open the URL in any browser tab.

## 1. The two big sources (recommended)
| OBS source | URL | Size |
|---|---|---|
| Scene, horizontal | `scene.html?profile=h` | 1920x1080 |
| Scene, vertical | `scene.html?profile=v` | 1080x1920 |
The scene holds every overlay below as a placeable widget. Arrange it in `scene-editor.html` (`?profile=v` for vertical). Layouts are saved on the Host and the stage picks changes up within 5 s. Alerts stay their own 800x600 source. Preview outlines: add `&preview=1`; grid: `&grid=1`; test another layout: `&layout=name`.

## 2. Standalone overlays (still work on their own)
| Overlay | URL | Source size | Empty / Host down looks like |
|---|---|---|---|
| Players (team cards) | `players.html` | 1920x1080 | nothing while there is no match; stays if the Host drops (last state) |
| Players, vertical strip | `players_vertical.html` | 1080x250 (sized from its height: never use a tall source) | nothing while no match |
| Queue + leaderboards | `queue.html` | 420x760 standalone, 560x720 as widget | idle leaderboard cards cycle after ~10 s idle; blank if the Host is down |
| Customs status | `customs.html` | 420x160 | after 3 failed polls (~9 s) it fades out instead of claiming QUEUE CLOSED |
| Sub roll / credits | `subroll.html` | 480x1000 standalone, 1920x1080 as widget | blank until `!subs roll` / start |
| Tournament wheel | `wheel.html` | 1920x1080 | an idle wheel (normal) when no session |
| Chat feed | `chat.html` | 460x520 | empty |
| Goal bar / latest / sub footer | `overlay/goal?id=followers`, `overlay/latest`, `overlay/subfooter` | 900x80 / 600x300 / 1920x120 | goal shows 0 progress; latest empty until an event |
| Now playing | `http://127.0.0.1:8771/overlay` (Spotify module) | 640x200 | blank when that module is down |
| Alerts | `http://127.0.0.1:8766/obs/alerts` (Multi) | 800x600 | blank when Multi is down |

## 3. Part modes (`?part=`), also registered as scene widgets
`wheel.html?part=wheel|teams`, `players.html?part=teams|header`, `queue.html?part=list|idle`, `customs.html?part=status|info`. All are OFF by default in every layout; switch them on in the editor. The wheel parts take over the screen while a wheel is running (the stage hides other widgets).

## 4. Fit / safe-area options (every overlay)
Added to any overlay URL or set for all in the Suite sliders page (`/api/overlay-options/schema` feeds it): `scale, anchor, pad, x, y, maxw, maxh, fit, overflow, preset (safe 5% / tv 10%), guides=1`.
- Saved per overlay or `*` for all, and per resolution profile: `name@1080p`, `*@4k`, `name@vertical`... Profiles: `1080p`, `1440p`, `4k`, `vertical`. The page picks its profile from its own size (portrait = vertical, height >= 2000 = 4k, >= 1300 = 1440p, else 1080p); `?profile=4k` forces one.
- One-click safe-area padding (px): 1080p 54/108, 1440p 72/144, 4k 108/216, vertical 54/108 (safe/tv).
- Scene pages are exempt (the stage itself is the full frame).

## 5. If something is blank - check in this order
1. Is the Host up? `http://127.0.0.1:8770/api/status`.
2. `http://127.0.0.1:8770/api/prestream` lists items: `overlays` (every page carries the fit script), `scenes` (the active layout has something visible, and widgets on other ports like alerts 8766 / now playing 8771 have a listener), `obs`.
3. `http://127.0.0.1:8770/api/scene-health` shows the same scene problems in plain words (per profile).
4. A widget on another port (alerts, now playing) is blank when that app is not running: start it.
5. Data endpoints in a tab: `/live_state.js` (queue, match, teams), `/api/customs/state`, `/api/queue-idle`, `/api/wheel/public`, `/api/subroll/state`.
6. Rehearse without Twitch: `python Tools\rehearse-overlays.py <host dll>` (sim Host on its own port; never touches OBS).

## 6. After the players_vertical size fix (2026-10-23)
The vertical widget used to be registered as a 1080x1920 box, which blew the 1080x250 strip up into thin pillars. New layouts get 1080x250 at the bottom of the vertical stage (y 1670). A layout saved BEFORE the fix keeps the old box: open `scene-editor.html?profile=v`, pick the layout, select "Players (vertical)", set x 0, y 1670, w 1080, h 250 (scale 1) and Save; or Delete the layout to get the fresh default.

## 7. Never
Do not go live to test overlays. Nothing here needs it. Hard rule for all sessions.
