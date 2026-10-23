# Session 013 - Master View (notes)

Owner: session 013, started by 00 (coordinator, local_9b055c40-005d-4fad-892a-7133e1382dd1). Last updated 2026-10-23.

## 1. What was built, and why
The Master View is one page inside the Suite app (Tauri v2), under `App/src/master/` (`master.html`, `master.css`, `master-core.js` = pure logic, `master.js` = UI). It talks to the Host (127.0.0.1:8770), the Spotify module (8771) and Multi (8766). Ivan's brief, relayed by 00: one super-responsive control page in Penguin orange/dark.
Docs: `Docs/MASTER_VIEW_APP.md`. Tests: `Tests/master/run.mjs` (37 tests) + `Tests/master/mock-host.mjs`.

Commits (oldest to newest): b065ab7, 97c1a33, 83e3918, 4834b5b, 9e4f47c, 497ec62, 37b6a16 (base, feeds, logs); 47c618c Spotify strip; 7b4ad4f docked player; 7e3cd84 drag/drop + strikes; ed421f8 simulator chat, activity defaults, streamer row; 30bbd14 wheel Queue/Undo/Tourney; d33ceec activity "what about the N players?" chooser, sim streamer, toast dedupe, site-style queue, Wheel Cancel dropped (Ivan: Cancel means the GAME); 48c67a1 "Fill empty slots"; 41d1855 strike chips labelled by game; 0813384 team name/colour editor, Fortnite row + sizes, Stream tab; 5a5be09 recap preview/post, raid prep, teams POST uses `hex`; a74f201 activity change calls `POST /api/scene-layouts setgame` (RL -> "Rocket League", Fortnite activities -> "Fortnite", End -> ""); needs the rebuilt shell.

## 2. Decisions and failures
- Optimistic overlays (`ui.ov`, `teamsOv`...) so clicks feel instant; `reconcile` only updates rows when their `sig` changes, so rows must carry every displayed field.
- Two-click `armed()` for dangerous buttons; no `confirm()`/`prompt()` (Tauri blocks them).
- Customs actions go through `/api/customs/mod` allow-list, anything else through `/api/run` as broadcaster.
- Teams: Host stores `{name,color}` in customs state; POST body is `{orange:{name,hex}}` (02's shape). Fallback to localStorage + a toast if the route 404s.
- Team size: customs 2v2/3v3/4v4 (1v1 button removed, KOTH sets it); Fortnite 1/2/3 + free 1-16.
- Stream tab: Twitch via Host `/api/channel/update|info`; YouTube/Kick via Multi `/api/stream/info|schedule`; TikTok = copy block. Scheduling creates an entry only.
- Failures fixed: stale mock host (kill port 8798 and restart); `\n` escaping in generated test code; old "9v9 -> null" test changed to 17v17.

## 3. Pass-on / gotchas
- HARD RULE from Ivan via 00: NEVER go live or test going live in OBS. No go-live control exists in Master View and none may be added.
- Only 00 builds/launches/restarts app, Host, modules. Never edit `PinguinoHost\*.cs`. Commit own files only (`git add <paths>`, never -A). Never push.
- Test only against the mock: `MOCK_OPEN=1 node Tests/master/mock-host.mjs` (port 8798) and `python -m http.server 8811` in `App/src`; open `http://127.0.0.1:8811/master/master.html?host=http://127.0.0.1:8798&music=http://127.0.0.1:8798&multi=http://127.0.0.1:8798`. Force fresh files with `fetch('/master/<f>',{cache:'reload'})` then reload. Run `node Tests/master/run.mjs`.
- Do not post to the real chat, spin the wheel, or toggle scenes while testing.
- Open bugs/unverified: see section 6.

## 4. Future ideas (priority order)
1. Live check of everything below once Ivan is at the PC.
2. "Last stream" card in the header (recap text + best clip).
3. Raid prep hotkey with a confirm step.
4. Fix editor hint text: customs chat lines keep the 🔷/🔶 emoji prefix before the team name (02), not plain text.

## 5. Chat history
Session id 2ea0c6c4-3f9f-4f2b-a70e-a6b34c1a07de. Transcript: `C:\Users\ivanm\.claude\projects\D--\2ea0c6c4-3f9f-4f2b-a70e-a6b34c1a07de.jsonl`. Grep for: `Master View`, `teamsNow`, `wheelQueue`, `askDo`, `siPush`, `recapDo`, `NEVER go live`.

## 6. Things Ivan may be forgetting
- Everything is verified on the mock/simulator only; no live writes tested (team names/colours, `!format` above 4v4, Fortnite KOTH, Twitch title/tags push, recap post, raid prep, wheel Queue/Undo).
- YouTube needs a token with the youtube scope pasted in Multi's settings; Kick needs a `kick_token` with channel:write from a Kick app login that does not exist yet (Kick stays read-only); TikTok is manual copy only.
- Spotify cover art needs the CSP `img-src https://i.scdn.co` (01 added; confirm it is in the build).
- Simulator "Chat ON" would post to real chat; keep it off unless intended.
- Recap "Post in chat" is a real chat post (30 s duplicate guard only).

### 6b. Read-only live check 2026-10-23 (22 - Master View; GETs only, nothing written)
Host 8770, Multi 8766, Spotify 8771 were up. Every GET the page uses answered 200 with the shape the page expects: /api/status, /api/obs/status, /api/obs/tree (connected:false, empty, because OBS is not connected), /api/live (live:false), /api/activity, /api/recap/preview ({ok,text,line,clip?,window}), /api/channel/info ({ok,title,game,tags}), /api/customs/state (has teams {orange,blue:{name,color}}, strikes, strikeLimit, controlHolder), /api/wheel/public, /api/wheel/state, /api/scene-layouts?profile=h, /api/chat/recent, /api/commands/profiles, /api/overlays, /api/eventlog, /api/overlaychat/status, /api/events (SSE snapshot first, retry:1000). Multi GET /api/stream/info answers; YouTube says connected:false (no token in Multi settings), so the Stream tab shows that error now. Spotify /api/state and /api/now fine; /api/devices returned 429 rate limited once (the page must keep showing the last list, it does). 404 on GET only: /api/commands/profile and /api/control (POST endpoints, expected). Multi has no /api/health (not used). No shape differences found.
Contract fixes this round: teams POST now sends {color} (the Host reads color, not hex); setgame confirmed against HostScenes.cs. The running Suite shell still shows the Link page; the new header (Last stream card, Raid prep, Shift+R) appears after the next shell rebuild by 100. Screenshot via App/Shot-Quiet.ps1 worked (needs -ExecutionPolicy Bypass); it showed the Link page, not Master View, so no Master View pixels were captured.

### 6c. Work 2026-10-23 (22 - Master View, worker under 20 - Suite)
Done, all in own files, mock-tested (49 tests): setgame/Fortnite/KOTH/teams contract, stream info tab, last-stream card + raid prep, write error mapping + double-click dedupe (cf8da45), layout check at 900 / 1366x768 / 2560x1440 (no overflow), text size option (9dfa369), Mods chip + status strip (3054338), intro approve/reject + streaks top 5 (4304ee0), per-source error budget + banner (82bb64c), self-review cleanup (7105c2b), QA checklist DocsqaSUITE_CLICKPATHS.md (4e78862). All of it needs the Tauri shell rebuilt by 100 before it shows in the app.
Pass-on: never fire POST /api/intros, /api/raid/prep, wheel or chat writes against the real Host from tests (mock only). The Host reads `color` (not `hex`) for team colours. Spotify `/api/devices` can 429.

## Status 2026-10-23 05:35
Role changed by 00: Q&A pool only (no coding, no restarts). Questions come via old 00; new supervisor is 100 - Coordinator (Docs/SESSIONS_STRUCTURE.md). Also found: Listen review card first line (52:24) has a 0.4 s clip for a 14-word sentence (reported to 01).
