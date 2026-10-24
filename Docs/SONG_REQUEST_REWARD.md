# Song Request reward: the Host's own copy

**Why.** Twitch only lets the app (client id) that created a channel point reward refund or complete its redemptions. The "Song Request" reward was
created by another app (Streamer.bot), so every refund the Host tried came back `HTTP 403 ... Client-Id must match the client ID used to create the custom reward`
(7 times on 2026-10-23). Rejected or skipped songs kept the viewer's points. The fix is a reward that the Host itself creates. Nothing is created
automatically: you run the steps below once.

The Host now also notices this by itself: the first refund that fails with that 403 logs one warning ("reward ... was created by another app") and the
Host stops asking Twitch for that reward. `GET http://127.0.0.1:8770/api/rewards` lists every reward with `"owned": true/false` (the same applies to the
Speak and timeout rewards: if one shows `owned:false`, do the same steps for it with its own title).

## Steps (about 3 minutes)

1. **Note the old reward's cost and prompt** in Twitch (Creator Dashboard > Viewer Rewards > Channel Points > Song Request). The cost is required below.
2. **Rename the old reward** to `Song Request (old)`: Twitch does not allow two rewards with one title. (Do not delete it yet: the 8 viewers below still have
   redemptions in its queue.)
3. **Create the Host's reward** (Host running, streamer signed in on the Host setup page with `channel:manage:redemptions`). In PowerShell, with your cost:

   ```powershell
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8770/api/rewards/create -ContentType application/json -Body '{"title":"Song Request","cost":1000,"prompt":"Type the song name or a Spotify/YouTube link"}'
   ```

   The answer has `"created":true`, the new `id`, and `"automationSwitched":true`. If it says another app already has that title, step 2 was not done yet.
   Calling it again is harmless (`"already":true`).
4. **The automation follows by itself.** "Spotify: channel point song request" (`spotify-redeem`) now has the new reward id on its trigger, so only redemptions of
   the new reward start it (the old one no longer does). Check at `http://127.0.0.1:8770/automations` that the action is enabled.
5. **Refund the 8 lost redemptions by hand** in Twitch's Rewards Queue (Creator Dashboard > Viewer Rewards > Channel Points > Rewards Queue, filter `Song Request (old)`):
   snowyroses_ x2, lvlmarshmello x1, stefan77777777f x3, pineyapplie x2. Select each > **Reject** (gives the points back).
6. **Delete the old reward** once its queue is empty.
7. **Test:** redeem the new reward yourself with a song the module rejects (for example a bad link): the points come back at once and the Host log shows `refunded redemption`.

## What changed in the Host

* `GET /api/rewards`: all rewards and whether the Host owns them. `POST /api/rewards/create {title?, cost, prompt?, inputRequired?, automation?}`: makes the Host's own reward,
  copies cost/prompt from a same-titled reward when it is the Host's, points the `spotify-redeem` automation (or the one named in `automation`) at it. Never runs on its own.
* Redeem triggers can carry a `rewardId`; when present it must match (title is then ignored).
* Refund/complete for a reward Twitch said belongs to another app: one warning, no repeated 403s.

## Picker (one click instead of the steps above)

Host page > Automations > an action with a "Channel point reward" trigger > **Load my channel point rewards**. Pick a reward, then:

* **Use this reward**: for a reward the Host owns (refunds work). Points the action at it. Works for any reward-driven action, not only songs.
* **Take over** (shown for rewards made by Streamer.bot / Songify): the Host creates its own copy (same title, cost, prompt, colour, cooldowns, limits) and points the action at it.
  Twitch only lets the app that made a reward edit it, so the Host's attempt to rename the old one to `<title> (old)` and disable it is normally refused (one try, never retried).
  Then the copy is called `<title> (Host)` and the message says **turn the old one off in the Twitch dashboard** (you can rename the copy back afterwards). If the rename is allowed the copy keeps the exact title.
* API: `POST /api/rewards/use {rewardId, automation?}` and `POST /api/rewards/takeover {rewardId, automation?}` (automation defaults to `spotify-redeem`). Answers carry `needsTakeover`, `oldRenamed`, `manualStep`, `message`.
* Needs `channel:manage:redemptions`. Without it both answer `needsScope:true` and "sign in as streamer again on the Host setup page" instead of a raw HTTP error.

The manual steps above stay valid as the fallback.
