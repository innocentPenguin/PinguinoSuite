# PinguinoHost - run the bots without Streamer.bot (2026-10-19)
A .NET 8 console app. It compiles the same four C# files (PinguinoB0t\PinguinoBotCore.cs, PinguinoChat, HelperPinguino, Shared\PinguinoRouter.cs) at start with Roslyn, supplies a `CPH` subset (`PinguinoHost\HostCPH.cs`) and dispatches chat like Docs\TRIGGERS.md: `!` core commands -> PinguinoBot, everything else -> PinguinoRouter. A 3 s timer runs the web sync. Single lock: one message at a time.

## Run
- Simulation (no Twitch): `Tools\run-host.ps1 -Sim`, then type `user: text` (`*user:` = mod, `#user:` = broadcaster). Test: `Tools\test-host.ps1` (PASS verified).
- Live: copy `Data\host_secrets.template.json` to `Data\runtime\host_secrets.json`, fill Channel, ClientId, UserToken (chat:write, moderator:manage:banned_users), SenderId, BroadcasterId; run `Tools\run-host.ps1`. Chat is read via anonymous IRC; replies/timeouts via helix. Never commit or print the secrets file.
- State/data: `Data\runtime` (override `--data`); globals persist in `host_globals.json`; `routing.log` as in ROUTING.md.

## Not done / unverified
- Verified live 2026-10-19: anonymous IRC read of a real public channel (#xqc) dispatched real Twitch message ids through the Router into routing.log. Still untried: helix send/timeout, EventSub, OBS (need your tokens / OBS running).
- Not supported: Streamer.bot-only features (OBS actions, First Words, sub/raid triggers, timed actions other than web sync). Events other than chat messages are not wired.
- Do not run Host and Streamer.bot on the same channel at once (double replies).

## Replacement coverage (added 2026-10-19)
| Streamer.bot gave us | PinguinoHost | Status |
|---|---|---|
| Chat message trigger / `!` commands | Twitch IRC (anonymous) -> Router / Core | sim verified, live untried |
| CPH calls the bots use (TryGetArg, SetArgument, Global vars, RunAction, SendMessage, TwitchTimeoutUser, Log*) | `HostCPH` | all 13 used calls covered |
| OBS (ObsSetScene/Show/Hide/IsConnected) | obs-websocket v5 client (`ObsHost/ObsPort/ObsPassword`) | written, untested vs real OBS |
| Sub/gift/cheer/raid/follow triggers | Twitch EventSub websocket -> PinguinoChat (`eventType`, `userName`, `tier`, `bits`, `viewers`) | written, sim events only (`event TwitchSub alice 2`) |
| Timed web sync | 3 s timer | sim |
| Overlay file serving | built-in HTTP on 8770 (8765 = PinguinoListen, 8766 = PinguinoMulti) | players.html served OK |
| First Words, Stream Deck actions, Streamer.bot UI | not replaced | gap (Chat already tracks first-seen in chat_memory) |

EventSub needs a user token with scopes: channel:read:subscriptions, bits:read, moderator:read:followers, chat:write, moderator:manage:banned_users.

## Suite integration and setup interface (2026-10-19)
- `Suite\modules.json` has a `host` module (port 8770, health `/api/status`, cwd `PinguinoHost`, `dotnet bin/Release/net8.0/PinguinoHost.dll`). Start it from the Suite UI like the others; it is not started with the Suite by default (flip `start_with_suite` in the UI once you cut over). Backup of the old file: `Suite\modules.json.bak-prehost`.
- All setup is done in the browser at **http://127.0.0.1:8770/setup** (no JSON editing): Client ID -> "Sign in with Twitch" (stores the token, fills your sender/broadcaster IDs and channel), channel, OBS host/port/password. Status pills show chat / can reply / events / OBS. Add `http://localhost:8770/auth` as a redirect URL in your Twitch app first.
- Secrets are written to `Data
untime\host_secrets.json` (local only) and never sent back to the page (`hasUserToken` / `hasObsPassword` flags only). API accepts localhost Host/Origin only. Saving needs a module restart.
- Tests: `Tools	est-host-api.ps1` (HOST API: PASS) and `Tools	est-host.ps1` (HOST SIM: PASS). Verified through a real Suite: module appears, starts, goes `running`, stops.
- Still unverified: Twitch sign-in round trip, helix send/timeout, EventSub, OBS (need your account / OBS running).
- OBS client verified against `Tools\mock-obs.py` (real obs-websocket v5 password handshake): auth OK, host reports `obsConnected: true`. Scene/source calls not exercised; real OBS still untried.

## Stream Deck / hotkeys and mock-Twitch test (2026-10-19)
- **Stream Deck replacement:** `POST http://127.0.0.1:8770/api/run` with body `{"text":"!next","user":"ivan"}` runs the text as the broadcaster (role 4) through the same dispatch as chat. In Stream Deck use a "Website" or an HTTP-request plugin action (POST, JSON body); a multi-action works for `!next`, `!win blue`, etc. Localhost-only (Host/Origin checked); no other PC can reach it.
- **First Words:** the host reads the IRC `first-msg` tag and passes `firstMessage` to the bots, so first-chat greetings work without Streamer.bot. It is not Streamer.bot's First Words database (no cross-stream "first words ever" history beyond `chat_memory.json`).
- **Mock Twitch test:** env `PINGUINO_HELIX_BASE` and `PINGUINO_EVENTSUB_URL` redirect helix / EventSub. `Tools\test-host-twitch.ps1` (uses `Tools\mock-twitch.py`) checks token resolution via `/users`, the helix chat send with Bearer + Client-Id headers, `/api/run`, and EventSub subscription calls: "HOST TWITCH(mock): PASS".
- **Still only verifiable with real credentials/OBS:** the browser sign-in round trip at id.twitch.tv, real helix acceptance of the scopes, real EventSub notifications, timeouts on a real channel, and real OBS scene/source changes. The paste route (`Deploy\PASTE-CHECKLIST.md`) stays as the fallback until those are confirmed.

## Embedded in the Suite shell (2026-10-19)
- `GET/POST /api/bots`: status (enabled, runs, last run, last error) and settings for PinguinoB0t, PinguinoChat, HelperPinguino. Writes bots.json / chat_settings.json / helper_settings.json; bots reload within ~10 s.
- Page: Suite dark theme, responsive, no popups; CSP `frame-ancestors` allows self, tauri://localhost, http(s)://tauri.localhost, loopback.
- Guard: Host must be loopback; Origin must be loopback or Tauri. POSTs: same-origin page is trusted; every other writer (Tauri shell, Stream Deck with Origin, scripts) needs `Authorization: Bearer` or `X-Pinguino-Token` equal to PINGUINO_API_TOKEN / PINGUINO_MODULE_TOKEN (if neither is set, only non-Tauri callers pass). PINGUINO_DATA_DIR is honored.
- Twitch sign-in navigates the top window to id.twitch.tv (framing is refused), then returns to /auth on 8770.

## Separate chatters per bot

Each bot can speak as its own Twitch account. In the Host page every bot card shows **Speaks as** and a sign-in button.
Signing in from a card (core / chat / helper) stores that account's token in `bots_secrets.json[role]` and sets `Bots[role].Account` and `Sender:"helix"` in `bots.json`. The Router's `PgSay` then posts through that account.
The "Sign in as streamer" button in the setup section keeps filling `host_secrets.json` (EventSub, timeouts, fallback speaker).
Sign in as the bot in a private window or log out of Twitch first (the flow uses `force_verify`). The Channel must be set first. Bots must be mods in the channel for timeouts. A bot without its own account keeps speaking through the shared account.

## Console log and prestream readiness

- **Console log:** the Host appends `{ts,module:"host",level,source,msg}` lines to `Data\runtime\console\host.jsonl` (rotated at 2 MB). Warnings/errors: chat or EventSub lost, EventSub subscription refused (token/scopes), chat send refused (HTTP code, rate limit, token rejected), OBS lost, and anything the bots report through `LogWarn`/`LogError` (router, AI, send-as-bot failures). Info: start, chat/EventSub/OBS connected. No chat text or secrets; the same line repeating within 30 s is written once.
- **`GET /api/prestream`** (loopback only; served from a copy at most 90 s old and also written to `consoleprestream-host.json` every 2 min, per MODULE_CONTRACT): `{status, items:[{id,label,status pass|warn|fail,detail}]}`. Checks: chat, EventSub (and refused subscriptions), streamer sign-in (token valid, hours left), each bot account (valid, has `user:write:chat`, hours left; core must have its own account), mod status of pinguinob0t (when the streamer token allows the check), bot modules loaded, OBS, Streamer.bot port 8080, AI key present, innocentpenguin.com/api/faq, last warning/error age. It never sends a chat message. Twitch checks use `id.twitch.tv/oauth2/validate`; an answer takes up to about 8 s.

## Single instance and master device

- **Per PC:** a Host takes a mutex per data folder; a second Host on the same folder exits (a restart waits up to 12 s for the old one to let go).
- **Several PCs:** Host is a `singleton` module (see MODULE_CONTRACT "Devices: master / auxiliary"). When the core launched it (module token present) it polls `GET /api/device/lease` every 10 s. It connects nothing (chat, EventSub, OBS, bots, sends) until it has seen `is_master:true`. When that turns false (twice at start, once when running) or the core is unreachable for 60 s, it disconnects chat and EventSub, waits 1.5 s and exits so the core can start it again on promotion. A core without the endpoint (404) counts as "single device = master". Standalone runs (no token) are not gated. Env for tests: `PINGUINO_LEASE_URL`, `PINGUINO_LEASE_POLL`, `PINGUINO_LEASE_GRACE`.
- **Streaming flag:** while OBS reports streaming the Host posts `{"on":true|false}` to `/api/device/streaming` (on change, and every 60 s while on).
- **Status:** `lease` in `/api/status` and `/api/summary`, a "master" item in `/api/prestream`. Test: `python Tools/test-host-lease.py` (mock core).

## Dashboard summary and bot control

`GET /api/summary` returns connections, chat rate (messages in the last minute / per minute over 5 min, active chatters, moderators seen in the last hour), per-bot health (signed in, enabled, last run, last error), the lease state and the last warning. `/api/bots` also carries each bot's `signedIn`, `signedInAs`, `health` and command list; the Host page shows them on every bot card with Send test, enable switch and sign-in button.

## Quick control from chat: `!pg` (mods and the streamer)
`!pg status` (bots on/off + login, chat/EventSub/OBS state, EventSub delay) · `!pg core|chat|helper on|off` (switch a bot off for a while, same as the card toggle) · `!pg test` (each bot says hi from its own account, so you see who really speaks) · `!pg cutover` (is the Streamer.bot cutover on). Viewers get no reply. If chat cannot be reached the answer is printed in the Host console instead. Pre-stream now also checks the streamer's permissions (what is missing for events/clips/ads/shoutouts), Twitch event delay, and whether the OBS replay buffer runs (!clip needs it).
