# Router streamer-first hook — proposal for Unit 04 (not applied)

Multi side is done: `GET http://127.0.0.1:8766/api/claims` returns `{"claims":[{"message_id","user","platform","score","expires_in"}...]}` for open medium/high cards for `claim_ttl_s` (20 s).

Proposed Router change (in `Shared\PinguinoBots.cs.txt`, then `node Shared\sync-shared.mjs`), default OFF:
1. Setting `multiClaimHold` (bool, default false), `multiClaimUrl` default the URL above.
2. In the router, before dispatching a chat message to PinguinoChat: if enabled, do a 300 ms-timeout HTTP GET; if any claim has `user` == the message's user (or `message_id` matches), set the result to `defer` (existing protocol) so the streamer answers first. Any error/timeout = continue as today (fail open).
3. Never hold messages from bot accounts (`PgIsBotAccount`).
Why not applied: file belongs to the bots unit and is pasted into Streamer.bot; changing it needs that owner's review and a Streamer.bot re-paste.
