# Session notes: 03 PinguinoMulti

Last updated: 2026-10-23 05:05. Module: `D:\PinguinoSuite\Suite\modules\multi` (port 8766). Docs: `Docs\PinguinoMulti`. Python: `Suite\.venv\Scripts\python.exe`. Tests: `Suite\modules\multi\tests` (110 pass).

## 1. What I built and why
Everything is committed locally. Nothing from this session has been pushed. Only 00 restarts or launches the app (`Update-Module multi`).

| Commit | What | Why |
|---|---|---|
| 3f7edb2 | Scene follow: alert profile switches with the OBS scene (`scene_follow.py`, polls Link `/api/obs` every 3 s) | 00 relayed Ivan's wish that alerts follow the scene |
| f4aecbf | Fixed a SyntaxWarning in a docstring | Noise in the logs |
| 5b2fb0a | Reads the Link token for port 7777 | Needed for scene follow |
| b5ff59b | Stream info and schedule endpoints (YouTube and Kick title/schedule) for 013 Master View | Request from 013 |
| 5eb4c96, 4322886, 3522fcd | Chat page "Sounds" section (local only): sounds for real people, first-time, returning, mention, question, with a 0 s gap option | Ivan asked for sounds on the chat page; revised to real people only |
| 5f5dec6 | Alert queue upgrades: merge many into one, overflow drops the lowest priority, per-type delay, remove from the waiting list | 00 relayed "central alert queue" |
| b8d9bb1 | Viewer intros through the alert queue: Multi plays only intros the Host marks approved, once per viewer per stream | Ivan wanted viewer intros |
| 70ffd14 | 15 new alert types, shoutout with clip, vertical-aware stage | "Alerts for everything" and the shoutout clip alert, relayed from 00 |
| 95ca440 | Shoutout settings matching Ivan's current Teklynk tool: clip only, progress bar, 10 s delay, rules for the Host | Ivan's existing tool settings, relayed by 00 |
| fbf65c6 | `/obs/alerts` accepts `?w=&h=&scale=`; editor help on duplicates and audio | 00, for the full-screen scenes |

Earlier commits: 8236213, 3a45798, bce562a, 064be6a, 2381753 (the first Multi milestones).
I quote Ivan only through 00's relays. The goal 00 gave: replace everything Ivan uses today with PinguinoBot and our stack.

## 2. Decisions and failed attempts
- Multi accepts the Host token only on `/api/alerts/` and `/api/events`. It stays that narrow so the Host cannot reach the rest.
- Intros: Multi never stores or approves them. It plays only what the Host reports as approved, and re-checks length (140) and links itself.
- Clips: only direct mp4 URLs from Twitch's clip hosts play. Anything else drops the clip and keeps the name card.
- Unknown alert types go to an editable "custom" type so nothing goes silent.
- I dropped my own full-screen canvas proposal and followed 023's `Docs\OVERLAY_SCENES_PLAN.md`: 023 owns the stage and editor, I supply the alerts page.
- Failed or fixed along the way: `git commit -a` swept in other sessions' files, so I reset and committed with explicit paths. Bash heredocs and `/tmp` paths broke patch scripts, so I write patch scripts to the scratchpad and run them with the venv Python. The session-messaging limit pauses sends after about 10 messages until Ivan types.

## 3. For the next session
- Never run `git commit -a`; add only your own paths (`git add Suite/modules/multi`). Other sessions share the same repo.
- Test: `cd Suite\modules\multi; ..\..\.venv\Scripts\python.exe -m pytest tests -q`. JS: `node --check static\alerts_ui.js`.
- Restart: only 00 runs `Update-Module multi`. Multi was restarted by 00 at 04:45 with 70ffd14 and 95ca440; fbf65c6 still needs one.
- Alert flow: Host feed or `/api/events` -> `_alert_from_message` in `server.py` -> `alerts.Engine.submit`. Host extras go through `POST /api/alerts/fire` (Host token).
- Shoutout rules (command, mods only, cooldown, raid rule, clip pick) are only stored in Multi. 02 must apply them.
- Open or unverified:
  - Nothing has been checked live in a browser or OBS: the Sounds UI, editor fields, shoutout clip layout at 800x600 and vertical, `?w/h/scale`.
  - Host `GET /api/intro?platform=&user_id=` (port 8770) does not exist yet. Intros play nothing until 02 builds it.
  - Kick, YouTube and TikTok feeds, the stream info endpoints, and scene follow against Link are untested live.
- Never go live in OBS or test it. Never send duplicate messages.

## 4. Future plans, by priority
1. Check everything above in a browser/OBS with 00 (alerts editor, clip, sounds).
2. 02's endpoints: `/api/intro`, the shoutout fire with a clip, event types for the new alert types.
3. Alerts widget inside 023's scene stage; remove the standalone source then.
4. Goal bar and hype-train bar overlays.
5. Dashboard as the default Multi window; launcher settings for Kick, YouTube, TikTok.
6. Kick webhook relay (needs Ivan's Kick app and a site change). YouTube refresh-token flow.
7. Held audit rounds 2 and 3 (includes the Twitch 4007 reconnect fix). TikTokLive install only with 00/Ivan's go-ahead and his @handle.
8. Not built from the Teklynk list: custom message/title/details templates, a dedicated video-size setting, a profile badge.

## 5. Where my history lives
- Session id: `3c227418-fce3-49e1-92c5-9885a3d6daf7`.
- Transcript: `C:\Users\ivanm\.claude\projects\D--\3c227418-fce3-49e1-92c5-9885a3d6daf7.jsonl`.
- Grep for: `[03]`, `shoutout`, `intros.py`, `scene_follow`, `OVERLAY_SCENES_PLAN`, `sounds.js`.
- 00 is `local_9b055c40-005d-4fad-892a-7133e1382dd1`, 02 `local_58156ab8-4c1b-4654-a4a3-48687e71d813`, 023 `local_30e19219-6bb0-4db8-ac65-ae0800f6ee15`, 05 `local_a7f59c84-45c5-420c-b135-91a4240e19ef`.

## 6. Things Ivan may be forgetting
- Nothing from this session is pushed to any remote.
- Intros do nothing until 02 builds the Host endpoint and the website intro form (05) exists.
- Shoutout clips and rules need 02's side. Clip rules are only stored in Multi, not enforced.
- Kick (app, `channel:write` scope), YouTube (refresh token) and TikTok (his @handle) each need his keys or accounts. TikTokLive is not installed.
- Alert sound and clip audio: the OBS browser source needs its audio on, and the standalone alerts source must be removed if alerts are placed in a scene.
- The suite's sound for chat is off by default; the Sounds section is local to the browser window.
