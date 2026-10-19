# Moderation scopes for Connect Multi — proposal (not applied)
Quick mod actions in the Chat page need two more Twitch scopes on the owner-only Connect Multi flow:
`moderator:manage:banned_users` (timeout/ban) and `moderator:manage:chat_messages` (delete).
Change: PinguinoSite `worker/index.js` `const MULTI_SCOPE='user:read:chat user:write:chat'` -> append both scopes. The viewer login is unaffected (separate scope constant), so no viewer re-approval.
Effects: the owner presses Connect Twitch in Multi once more and approves the extra permissions; Multi's capabilities `mod_timeout`/`mod_delete` turn on automatically. Needs a PinguinoSite deploy, so it waits for Ivan's explicit OK (site pushes need it).
