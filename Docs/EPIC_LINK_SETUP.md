# Epic account link: what Ivan must create (site is built, switched off until then)

Status: built 2026-10-21 by 05, local commit, not deployed. The "Link Epic account" button on /settings#epic only appears once both variables below exist on Railway. Nothing is invented: no credentials are in the code.

## What it does
- Signed-in member presses **Link Epic account**, signs in at Epic, and the site reads ONE thing: the Epic display name (scope `basic_profile`). The token is thrown away right after.
- Stored per member: `epicLink = {id, name, at}`. The Epic account id is internal only (used to stop one Epic account being linked to two members); it is never in any public page or API.
- Display rule everywhere (queue, teams, board, standings, members, profile, mod pages): **linked Epic name wins; otherwise the name the person typed in Settings; never a guess or a bot lookup.**
- The name is refreshed whenever the person presses **Refresh from Epic**. Unlink is in the same place (falls back to the typed name).
- On link, the site queues the bot's existing `!register @<player> <name>`. Field for 02/the bot: the display name arrives as that command's text (same as before); the site's own field is `epicLink.name` (site-only).

## Ivan creates (https://dev.epicgames.com/portal, Epic Games Developer Portal)
1. Make or pick a **Product** (e.g. "Innocent Penguin").
2. Product Settings > **Epic Account Services** > create an **Application** (name "Innocent Penguin Site"), client type **Confidential**.
3. Permissions: enable only **basic_profile** (Display Name). Nothing else.
4. Redirect URLs: `https://innocentpenguin.com/auth/epic/callback` (and for local testing `http://localhost:3000/auth/epic/callback`).
5. Copy the **Client ID** and **Client Secret**.
6. Railway > Variables: `EPIC_CLIENT_ID` and `EPIC_CLIENT_SECRET` (needs `SESSION_SECRET` already set, as for the other logins). Redeploy.
7. Epic may require the Epic Account Services app to be reviewed/published (privacy policy + terms URLs) before the public can sign in; until then only team members of the product can. Check the portal's "Epic Account Services" page for the status.

## Notes / unverified
- Endpoints used (verify against Epic's current docs when setting up): authorize `https://www.epicgames.com/id/authorize`, token `https://api.epicgames.dev/epic/oauth/v2/token` (Basic client auth), user info `https://api.epicgames.dev/epic/oauth/v2/userInfo` (fields `sub`, `preferred_username`). If Epic names a field differently, only the small block in `worker/index.js` ("EPIC GAMES ACCOUNT LINK") changes.
- Not tested against the real Epic servers (no credentials); covered by a local test with a fake Epic.
- Console players: the display name Epic returns may be the Epic name, not a platform gamertag; that is the intended "Epic username".
