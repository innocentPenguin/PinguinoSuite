# 03 PinguinoMulti - audit round 1 of 3 (2026-10-22)

Scope: everything changed since the chat-comfort work (alerts.py, alert_media.py, server.py alert routes + token guard, chatux.js, alerts.html, alerts_ui.js). Read line by line.

## Fixed (all in Multi, tests 98 pass, was 95)
1. Alert queue runner died permanently if one emit raised -> every later alert silently lost. Now guarded; error goes to the "What fired" log, queue continues.
2. Webhook numbers: amount "abc", inf, nan, 1e400, lists crashed submit/fire with a 500 (OverflowError was not caught). One safe `_int`; text fields (message, display, recipient, level, tier) capped.
3. POST /api/alerts/config with a malformed body reset the saved alerts to defaults. Now 400.
4. Upload read the whole body before the size check; Content-Length is now checked first (413).
5. Protocol-relative urls (//host/x.mp3) were accepted as sound/media; refused.
6. Host-sound import: bad Volume value raised; empty sanitized file name could copy onto the folder. Both guarded.
7. Editor autosave: a slow reply could overwrite newer edits, and a failed save crashed the editor (config undefined). Fixed, shows "Not saved".
8. The dedupe memory grew without bound; pruned.
9. Earlier in the night: Host token (module_token host) accepted on /api/alerts/* and /api/events only; Multi writes its token to alert_bridge.json.

## Log review (Data\runtime\console\multi.jsonl, 238 lines)
- needs_auth for Discord/YouTube on every start: expected (no tokens set), not a fault.
- Twitch "4007 invalid reconnect" ~12:15-12:35 on 10-19, 10-20, 10-21: self-recovers in 3-4 s, so up to ~4 s of chat can be missed once a day. Likely cause: after session_reconnect the new socket's session_welcome triggers _subscribe again (subscriptions carry over on reconnect). NOT changed tonight because it cannot be tested without a live Twitch session; proposed fix for round 2/3: skip _subscribe when the welcome arrives on a reconnect URL.
- One ConnectionResetError "unhandled" on 10-21 09:43: already handled by _loop_exception since, not seen again.
- Host activity feed "not reachable yet" lines appear only around restarts.

## Not verified (needs Ivan/00, not done here)
Real Host events and audio in OBS, !alert end to end (needs Update-Module multi), real Data\runtime sound import.
