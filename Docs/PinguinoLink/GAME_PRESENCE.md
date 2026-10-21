# Game presence: gaming PC -> Discord (design, 2026-10-21)

Status: DESIGN ONLY. Not built yet. Off by default when built.

## Goal
The gaming PC has no Discord. Ivan wants the game he is playing shown in Discord so his status stays current.
Flow: gaming PC (Link agent) -> hub PC (has Discord) over the paired Tailscale mesh -> Discord.

## Hard rules
- Official routes only: Discord Rich Presence through the local Discord client IPC, plus a channel webhook. NO user token, NO selfbot, NO status spoofing (Discord ToS).
- Off by default; one toggle in Link settings on each PC (sender and hub have separate toggles).
- Reads only the process name of the foreground window. Never window titles, never screenshots, never other apps.
- No OBS or go-live involvement. Link only reads the process list; it sends no keys.
- Sending goes through Link's own mesh route to the hub. Chat/Discord lines never go through the Host chat paths.

## 1. Detection (gaming PC, Windows)
- Every 15 s run a fixed PowerShell snippet (execFile, no string built from input): GetForegroundWindow -> GetWindowThreadProcessId -> process name + whether its window rect covers its whole monitor (fullscreen/borderless).
- Decision order:
  1. Process name is in the configured known-games list -> use its friendly name. Defaults: RocketLeague.exe = Rocket League, FortniteClient-Win64-Shipping.exe = Fortnite. List is editable in settings (`game.known`, lines `exe=Name`).
  2. Else, if `game.auto` is on and the foreground window is fullscreen/borderless and the exe is not in the ignore list -> friendly name = exe name without `.exe`, tidied. 
- Ignore list (default, editable): browsers (chrome, msedge, firefox, brave, opera), launchers/stores (steam, steamwebhelper, EpicGamesLauncher, Battle.net, Origin, EADesktop, UbisoftConnect, GalaxyClient), shell and tools (explorer, obs64, Discord, Spotify, code, devenv, vlc, mpv, Teams, Zoom, PinguinoLite, Suite app).
- Debounce: a game must be foreground 30 s to start, and be gone 60 s to stop (alt-tab does not flicker the status).
- State: `{game, since}` (since = ISO time the game became current) or null.

## 2. Transport (sender -> hub)
- New peer route on the hub `POST /api/mesh/presence` body `{game, since}` or `{game:null}`; peer-auth only like the other mesh routes; game name max 64 chars, control chars stripped.
- Sender posts on change, plus a heartbeat resend every 120 s. The hub treats no update for 5 min as "stopped" so a crashed or offline gaming PC clears itself.
- Hub setting `presence.accept` (off by default) chooses whether it accepts presence from paired PCs, and `presence.from` which paired device is trusted (one device).

## 3a. Discord Rich Presence on the hub
- Hub talks to the local Discord client over its IPC named pipe `\\?\pipe\discord-ipc-0..9` (Node `net`, no dependencies): handshake (op 0, `{v:1, client_id}`), then `SET_ACTIVITY` (op 1) with `{details: game, timestamps:{start}, assets}`. Clear = `SET_ACTIVITY` with no activity.
- Needs Ivan's own Discord application id (`presence.discordAppId`, not a secret). Without it this part stays off.
- If Discord is not running: retry quietly every 60 s, log once.
- Limitation to tell Ivan: Rich Presence shows the activity as "Playing <our app name>" under the application he creates. Name the Discord app after the game does not work per game; we set `details` to the game name and the app can be called e.g. "Ivan's gaming PC".

## 3b. Webhook fallback
- Setting `presence.webhookUrl` stored in the Suite key vault (secret `DISCORD_PRESENCE_WEBHOOK`), never in config.json or logs.
- First change posts one message "Now playing X" (`?wait=true`, remember message id). Later changes EDIT that message (`PATCH .../messages/{id}`) instead of posting new ones. When the game stops, edit to "Not playing". At most one call per 30 s (coalesce changes); on a 429 wait `retry_after`.
- If the message was deleted (404) post a new one once.
- Dedupe: identical text is never sent twice.

## Settings (Link, group "Game presence")
`game.send` (gaming PC, off), `game.auto` (on, only matters when send is on), `game.known`, `game.ignore`, `presence.accept` (hub, off), `presence.from`, `presence.discordAppId`, `presence.webhook` (on/off; URL in vault), `presence.ipc` (on/off).

## Tests (no real Discord)
Fake IPC pipe server and fake webhook HTTP server; fake process snapshots injected into the detector. Checks: known game, auto fullscreen game, ignore list, debounce, stop on timeout, IPC handshake and activity frame, webhook post then edit, rate limit, dedupe, settings default off, presence route refuses unpaired and untrusted callers.

## What Ivan must set up
1. Create a Discord application at discord.com/developers/applications; give the app id to Link (`presence.discordAppId`). Optional: upload a large image named `pc` as the Rich Presence art.
2. Optional webhook: in the channel's settings create a Webhook and put the URL in the key vault as `DISCORD_PRESENCE_WEBHOOK`.
3. Both PCs paired in Link (needs Tailscale on), Discord running on the hub with "Display current activity" enabled in Discord's Activity Privacy settings.
4. Turn on `game.send` on the gaming PC and `presence.accept` on the hub.
