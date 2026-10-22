# Railway secret rotation (innocentpenguin.com)

Written by 05 on 2026-10-21 after Railway's security disclosure. Read-only research: no secret value was read or printed. The list below is what the site CODE reads (from `worker/` and `scripts/local-server.mjs`); only Ivan can see which ones are actually set in the Railway **Variables** tab. Builds are paused on Railway, so nothing is pushed or redeployed by us; rotating a variable in Railway normally triggers a redeploy, which may wait until builds resume.

Rule of thumb: rotate everything that is set, in the order below, one at a time, and check https://innocentpenguin.com after each. Anything that was ever pasted into chat, a log, or a screenshot counts as leaked.

## Secrets the site holds on Railway

| Variable | What it is | Where else it lives |
|---|---|---|
| `SESSION_SECRET` | Signs the login cookie and OAuth state (47 uses). | Local `PinguinoSite\.env` only. |
| `BOT_API_KEY` | Bearer key for everything the home PC sends/polls (`/api/bot/*`: commands, boards, economy, profiles, wheel...). | **Home PC:** the Host reads it from the encrypted vault `Data\vault.bin` under the name `BOT_API_KEY` (`SiteHttp.Key()` in `PinguinoHost`). The older PinguinoB0t Core has the same value as `WebSyncKey` in `Data\runtime\settings.json` (plus old copies in `Data\backups\...\settings.json` and `Archive\backups\...\settings.json`). Local `PinguinoSite\.env`. |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Twitch app: "Log in with Twitch", live status, owner roles sync. | Twitch developer console. Local `.env`. |
| `DISCORD_BOT_TOKEN` (+ `DISCORD_NEWS_CHANNEL_ID`, not secret) | Discord bot reading #announcements and server boosters. | Discord developer portal. Local `.env`. |
| `SPOTIFY_API_KEY` | Bearer key for the PC Spotify module -> `/api/spotify/*`. | **Home PC:** `Data\vault.bin` name `SPOTIFY_API_KEY` (module `spotify`), and write-only in `spotify\config.json`. |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Spotify client credentials (search only). | Spotify developer dashboard. |
| `EPIC_CLIENT_ID` / `EPIC_CLIENT_SECRET` | Epic account link. **Not set yet** (feature is off and its routes answer 404). Create these fresh later; nothing to rotate. | n/a |
| `GOOGLE_*`, `KICK_*`, `TIKTOK_*` (`_CLIENT_ID/_SECRET/_KEY`) | Extra login providers. Only matter if set. | Each provider's developer console. |
| `SITE_ORIGIN`, `PORT`, `DATA_DIR` | Not secrets. | |

Also sensitive but NOT a variable: the Railway data volume (`DATA_DIR`) holds member records, and the **owner's Twitch token** used for the roles / supporter sync (kept server-side). It cannot be rotated from Railway; it is replaced by Ivan reconnecting on `/roles` after the Twitch secret changes (below).

## Order and steps

Do the cheap, low-impact ones first; the ones that need the PC last (so the PC is ready before the site key changes).

1. **`SESSION_SECRET`** (no PC work)
   - Generate: `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` (needs 32+ chars; the site refuses logins with a shorter one). Replace the Railway variable.
   - Breaks: every viewer and mod is logged out once and has to log in again. Pending login attempts (10 min) fail once. Nothing is lost server-side.
   - Ivan clicks: Railway > service > Variables > `SESSION_SECRET` > paste new value > Deploy.
2. **`DISCORD_BOT_TOKEN`**
   - Discord developer portal > the bot > Bot > **Reset Token** > copy > paste into Railway.
   - Breaks: news card falls back to `content/news.json` and booster sync stops until the new token is deployed. Old token stops working immediately.
3. **`SPOTIFY_CLIENT_SECRET`** (if set)
   - Spotify dashboard > the app > Settings > View client secret / rotate > paste into Railway. Breaks: `/music` search until redeploy.
4. **`SPOTIFY_API_KEY`** (needs a matching PC change)
   - New random 32+ char string. Set it in Railway AND in the Spotify module (Setup tab > Website > key, which writes `spotify\config.json`; or the Key vault in Integrations). Change both in one sitting.
   - Breaks: the music mirror (`/music`, `/overlay/music`) shows stale/offline until both match. Harmless otherwise.
5. **`TWITCH_CLIENT_SECRET`**
   - Twitch developer console > the app > **New Secret** (this invalidates the old one) > paste into Railway.
   - Breaks: login with Twitch and live status fail until the redeploy finishes. **Also** the owner's stored roles/supporter token stops refreshing: after the deploy, Ivan opens `/roles` and presses Connect/Reconnect (owner Twitch login) once. Viewers' existing sessions keep working (they are signed with `SESSION_SECRET`).
6. **`BOT_API_KEY`** (needs 00 to update the Host; Ivan does the Railway click)
   - 00 prepares first: generate a new 32+ char random key, but DO NOT change anything yet.
   - Then, in one quick window (not during a stream): (a) 00 stores the new key in the Host vault under `BOT_API_KEY` and in PinguinoB0t `WebSyncKey` (`Data\runtime\settings.json`) and restarts the Host/Core; (b) Ivan sets `BOT_API_KEY` in Railway and deploys. Order between (a) and (b) does not matter, but keep the gap short.
   - Breaks during the gap: bot <-> site bridge answers 401 (the Host reports it in `/api/site/status` and stops retrying until the key matches): queue/customs panels go stale, `!join` from the site, points/boards pushes and loan requests wait. The Host retries after the key is fixed. Nothing is lost permanently; waiting commands expire after a few minutes.
   - Afterwards 00 should scrub the old key: `Data\backups\pre-migration-*\settings.json`, `Archive\backups\*\settings.json` and any `Archive\PinguinoB0t-versions\*.cs` copies that contain a real `WebSyncKey` value (they are on disk in plain text; delete or blank them). Local `PinguinoSite\.env` should get the new value too.
7. **`GOOGLE_*`, `KICK_*`, `TIKTOK_*`** (only if set): regenerate each secret in its console, paste, deploy. Breaks that provider's login until redeployed.
8. **`EPIC_CLIENT_SECRET`**: not set yet. When Ivan creates the Epic app (see `Docs\EPIC_LINK_SETUP.md`), use fresh values and never reuse any pasted earlier.

## After rotating

- Railway > Variables: remove any leftover/unused variable (old names, test keys). Check the Railway **Deployments** and activity log for access you do not recognize, and review team members and API tokens in Railway account settings.
- Railway's own account: rotate the account password, enable 2FA, revoke old Railway API/CLI tokens (Account > Tokens). This is Ivan's click; we never handle those.
- GitHub (`innocentPenguin/PenguinSite`, private): confirm no secret was ever committed (we never commit `.env`; it is in `.gitignore`) and review deploy keys / Railway's GitHub app access.
- Verify live after each step (the site is read-only to check): `/`, log in with Twitch, `/customs` shows bot data, `/music`.
- Sessions 00/02: if you rotate `BOT_API_KEY`, expect the Host's `/api/site/status` to show the key refused until it is updated; that is expected.

## What Ivan must click (short list)

1. Railway Variables: new `SESSION_SECRET`, new `DISCORD_BOT_TOKEN`, new `SPOTIFY_*` values if set, new `TWITCH_CLIENT_SECRET`, new `BOT_API_KEY` (with 00).
2. Discord developer portal: Reset Token. Twitch console: New Secret. Spotify dashboard: rotate secret.
3. After the Twitch change: `/roles` > reconnect owner.
4. Railway account: password, 2FA, revoke tokens.
