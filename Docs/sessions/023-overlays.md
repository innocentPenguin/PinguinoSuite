# 023 - PinguinoB0t overlays + Host overlay modules (fork of 02)

Session id: `local_30e19219-6bb0-4db8-ac65-ae0800f6ee15`. Transcript to grep: `C:\Users\ivanm\.claude\projects\D--\30e19219-6bb0-4db8-ac65-ae0800f6ee15.jsonl`.
Owner of: bot scripts, Host modules `PinguinoHost/Host{SubRoll,QueueIdle,OverlayOptions,Scenes}.cs`, and `PinguinoB0t/overlays/*`. Only the coordinator (00) restarts/launches the Host. Updated: 2026-10-23.

## 1. What was built, and why
Ivan's own words this stretch were few: "yes to all" (approving: keep gifted subs in T2/T3, a new-subs idle card, a pre-stream overlay-tag check). The rest came as relayed requests from 00 (Ivan's wishes, second hand).
- **"Subs!" idle card** (fe54667, 2da8952, eb52697): ONE scrolling card in the queue idle cycle listing every subscriber by tier (T1/T2/T3), with layouts flat/separated/sprinkled, anniversary highlight ("N YR"), gold/diamond frames. Why: Ivan wanted all subs shown, one list, tiers visible. Gifted subs stay out of T1 and in T2/T3 (confirmed by Ivan).
- **Sub roll-call** (06612cf) `!subs roll`, plus queue idle leaderboards (80abe64).
- **Overlay fit options** (`overlay-options.js` + `HostOverlayOptions.cs`): scale, anchor, pad, x/y, maxw/maxh, fit, overflow, preset (safe 5%, tv 10%), guides; per-overlay and "*" in `Data\runtime\overlay_options.json`; sliders page built by 01 from `/api/overlay-options/schema`. Why: overlays must fit the safe area on any source size.
- **New-subs idle card** (0415910): subscribers of the last 30 days, newest first; queue_idle config v3 (backup `.bak-v2`).
- **Pre-stream overlay check** (0415910) `GET /api/overlay-options/health`: lists overlay pages missing the `overlay-options.js` tag (`scene*` and backup pages are skipped).
- **Idle detect delay 20 s -> 10 s** (d8d2fb2) at 00's request ("cut idle detection time by half"). The "no timer until idle starts" half of that request had nothing to act on: the queue overlay draws no countdown; I told 00 and asked where Ivan sees one. Unanswered.
- **Overlay scenes** (6eea49a plan, 4b7720a phase 1, f641606 per-game + alerts, d6ee73b editor): `scene.html?profile=h|v` stage with every overlay as an iframe widget, `HostScenes.cs` (`/api/scene-widgets`, `/api/scene-layouts`), `scene-editor.html`. Why: Ivan wants ONE full-screen OBS source per orientation, less OBS clutter, customisable per game. Full plan and API in `Docs/OVERLAY_SCENES_PLAN.md`.

## 2. Decisions and failed attempts
- Widgets are iframes of the unchanged standalone pages (zero rewrites, standalone sources keep working). Sub-part widgets (team cards only, wheel only...) need a `?part=` mode in each page: deferred until 02 lands the wheel/team-box change.
- Alerts stay STANDALONE (Ivan moves them per game). The widget (03's page, `http://127.0.0.1:8766/obs/alerts`) exists but is off by default; if used it is pinned at z100 and the standalone source must be removed or every alert plays twice; sound plays inside the scene source.
- `overlay-options.js` scales `body` about an anchor of the SOURCE, not of the card. Not applied to the stage (`scene*` is exempt).
- Scrolling cards use `setTimeout(33)` not requestAnimationFrame: rAF does not fire in the hidden browser pane (and may throttle in OBS).
- Failed/bit me: the Windows git-bash tool chokes on long heredocs with mixed quotes ("unexpected EOF"): write scripts with the Write tool and run them. `/tmp` paths are not visible to Windows python started from bash (use `cygpath -m`). A v2->v3 migration crashed silently because `x["metric"]` throws on chain arrays; the catch returned defaults. The sim Host exits when stdin is /dev/null: keep stdin piped (see test scripts).
- Test pattern: sim Host `--sim --no-sync --data tmp --suite D:\PinguinoSuite`, env stripped of `PINGUINO_*`, unique port + `PINGUINO_COMPAT_WS_PORT`.

## 3. Hand-off gotchas, test and restart steps
- Build for tests: copy PinguinoHost (excluding bin/obj) to a temp dir, `dotnet build -c Release -o <out>`, then `python Tools/test-host-<x>.py <out>/PinguinoHost.dll`. Tests: subroll, queueidle, overlayopts, scenes (queueidle/subroll sleep 61 s: the config cache is 60 s). The scenes test occasionally hits a slow Host start; re-run once.
- Not a bug: `wheel.html` shows an idle wheel when the sim Host has no session.
- Restart needed (coordinator only) for: HUD widget registry (phase 3), scenes API, per-game layouts, new-subs card + config v3, health check, idle delay 10 s default (the live `queue_idle.json` was edited to 10; it is gitignored). Host rebuilt 05:01 includes phase 1 (4b7720a) but NOT f641606/d6ee73b host changes (per-game, alerts): needs another rebuild.
- Layouts live in `Data\runtime\scene_layouts.json` (gitignored); the stage re-reads every 5 s.
- API paths: `GET /api/scene-layouts?profile=h[&layout=][&js=1]`, `POST /api/scene-layouts {action,...}`, `GET /api/scene-widgets` (NOT `/api/scenes/layouts`).
- Pages: `http://127.0.0.1:8770/scene.html?profile=h&preview=1`, `/scene-editor.html`.

## 4. Future plans (priority order)
1. Wire `setgame` (`POST /api/scene-layouts {action:"setgame",profile:"*",game}`): primary = Master View activity selector (013/01); also the Host's Twitch category change if seen.
2. `?part=` modes agreed with 02 AFTER their wheel/team-box change (double-width box, ??? pulse, vertical). DONE in phase 3 (needs the restart-free static files only; registry needs a Host rebuild): HUD widgets goal/latest/subfooter/chat/customs/nowplaying (all off by default) and takeover (stage polls /api/wheel/public, hides non-pinned widgets; postMessage pgTakeover overrides). Game-stats HUD not built: no data source yet (ask Ivan what he wants shown).
3. (done, see 2)
4. `!layout name` chat command (mods) and a Suite panel embedding the editor + layout picker (01).
5. Optional postMessage bus so the stage fetches data once for all widgets.

## 5. Things Ivan may be forgetting
- OBS: the two scene browser sources (1920x1080 and 1080x1920) must be created; nothing exists yet. Keep audio on for the scene source if alerts are ever framed.
- Default layout positions are guesses: nobody has checked them on the real stream; use the editor. No real-stream test was done (hard rule: never go live from here).
- The Host must be restarted (and rebuilt past 05:01) to see the per-game layouts and editor saves; the editor page works as a plain file but its API does not.
- Unanswered: where does Ivan see a countdown timer on the leaderboards (queue overlay has none)? Which source is authoritative for the current game?
- Risks: the 800x600 alerts page is served by Multi on port 8766: if Multi is down the alerts widget is blank. A layout without any visible widget gives an empty scene. Auto-switch silently falls back to the active layout when no layout is tagged with the current game.
- `moderator:read:chatters` still needs Ivan's streamer re-sign-in; `test-host-obs.py` was failing (not mine).
