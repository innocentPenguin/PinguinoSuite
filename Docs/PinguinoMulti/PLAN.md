# Unit 03 — PinguinoMulti: planning baseline + Milestone 1 (Twitch)

All work stays inside `D:\PinguinoSuite`. Nothing outside it is touched except where noted in §0.

## Context
You want a unified streaming chat (Twitch, YouTube, Kick, Discord, TikTok) with movable windows, explainable priority scoring (local, optional AI), priority cards, reply tracking (typed, clicked, hotkey, Stream Deck, optional voice) and learning. It must work without AI or Streamer.bot. You chose: build now as a Suite module that can grow, keeping a native app as the target; reuse the site's Twitch OAuth.

## 1. Verified implementation status (inspected 2026-10-19)
- PinguinoMulti does NOT exist: no `Suite\modules\multi`, no port 8766, no mention anywhere, no Unit 01/02/03 docs (`Docs\` empty, no CLAUDE.md). The earlier proposal was never built. Treat as greenfield.
- Reusable pieces that DO exist:
  - Suite host `Suite\suite\suite.py` (FastAPI, port 8760, WS event bus `/ws`, `modules.json` supervisor, Edge `--app` window, tray, autostart). Ports in use: 8760 Suite, 8765 Listen, 3000 site.
  - `modules\listen` (Python FastAPI + SQLite WAL + faster-whisper large-v3-turbo) → reuse its ASR for voice reply detection.
  - `modules\link` (Node, OBS-websocket, Tailscale) → remote/mobile monitor path.
  - `Data\profiles` (thousands of per-viewer JSON), `Data\chat_logs`, `lore.json` → seed viewer history/"frequent viewer" signals.
  - Bots (Streamer.bot inline C#, .NET 4.8): `Shared\PinguinoRouter.cs` is the only chat-message trigger; protocol `pinguino.result` = handled/pass/defer; bot-loop guard `PgIsBotAccount`; `PgSay` sender; `PinguinoBotFirsts.cs` has its own trigger and bypasses the router.
  - Site `PinguinoSite\worker\index.js`: Twitch/YouTube/Kick(PKCE)/TikTok viewer OAuth (verified only with fake providers) and a separate broadcaster-only "roles" connect flow (~l.158, 1139, 1159).
- Not present: any Twitch/YouTube/Kick/Discord/TikTok chat reading in the Suite; Streamer.bot has no link to the Suite; Router/bots.json/bots_secrets.json not yet deployed; no Stream Deck profile.
- Caution: `suite_settings`, `chat_settings.json` hold a plaintext AI `ApiKey`. Multi must not copy it; use Windows Credential Manager (`keyring`).

## 0. Housekeeping (organization request) — done in implementation, not now
Related items outside the Suite: only `D:\InnocentPenguin-source.zip` (site snapshot) and compat links in `D:\PinguinoBot`/`D:\InnocentPenguinSite` (blocked until README migration steps done; `%AppData%\BVQ` is code-referenced, do not move; backups in `D:\PinguinoBackup` stay). Plan: move the zip to `Archive\`, leave links alone, document in `Docs\`. Create `Docs\PinguinoMulti\` (PLAN, ARCHITECTURE, PLATFORMS, CONTRACTS, SESSIONS\ log, DECISIONS) as the permanent planning home; archive finished task-session reports to `Docs\PinguinoMulti\SessionsArchive\`.

## 2. Recommended architecture
Headless **core** + **thin UI shells**, so a native shell can replace Edge later with no core rewrite.
- `Suite\modules\multi\` (Python 3.14, FastAPI/uvicorn, registered in `modules.json`, port **8766**, health `/api/status`):
  `connectors\{twitch,youtube,kick,discord,tiktok}.py` → `normalize.py` (one `ChatMessage`) → `dedupe.py` → `store.py` (SQLite WAL) → `priority\{rules,context,history,ai,fallback}.py` → `cards.py` (state machine) → `replies.py` → `api.py` (REST + WS) ; `ui\` static web app; `windows.py` (shell abstraction: Edge now; native later).
- One local WS stream `/ws` of typed events (`message`, `card.update`, `reply.detected`, `conn.status`, `layout.changed`). Every window and any future native/mobile shell is just a client. This is the seam to Unit 01.
- Native intent: shell interface (`open/move/resize/close/monitor info/always-on-top`) abstracted now; Phase 2 evaluates Tauri (WebView2/WKWebView, small footprint, Win+macOS) as the Unit 01 shell. Decision deferred to a Unit 01 spike; Multi UI stays plain HTML/TS so it is reusable.
- Bounded asyncio queues per connector (drop-oldest for low priority, never drop priority-candidate messages), writer thread batching SQLite, crash recovery via last-seen message id per platform.
- Secrets: tokens in Windows Credential Manager (macOS Keychain later). Never in JSON/logs.

## 3. Platform feasibility (research task: verify each against live docs before coding; confidence from current knowledge)
| Platform | Read | Send/reply | Auth | Status |
|---|---|---|---|---|
| Twitch | EventSub WebSocket `channel.chat.message` (scope `user:read:chat`); IRC fallback | Helix `POST /chat/messages` with `reply_parent_message_id` (`user:write:chat`) | OAuth user token + refresh | Official, stable. Badges/emotes via Helix, mod metadata in event, history not recoverable server-side (store ours). |
| YouTube | `liveChat.messages` polling / streamList; quota-heavy | `liveChatMessages.insert` | Google OAuth; chat scopes are sensitive (site comment l.423 notes verification) | Official but quota-limited; no replies/threads; read+send. |
| Kick | Official public API + webhooks (chat events) | Chat send endpoint (OAuth PKCE) | Kick OAuth | Official but young; verify event delivery needs a public webhook URL → may need tunnel (Tailscale funnel/Link) or fall back to unofficial Pusher websocket (label UNOFFICIAL). |
| Discord | Gateway bot, `MESSAGE_CONTENT` privileged intent for configured channels | Bot send/reply | Bot token | Official, stable; channels not "streams"; read/send/reply. |
| TikTok | No official chat API for LIVE | none | — | Only unofficial reverse-engineered libs (e.g. TikTokLive); fragile, ToS risk → **read-only, labeled UNOFFICIAL**, off by default. |
Rules: each connector declares capabilities (`read, send, reply, badges, history`) and UI shows them; read-only platforms never show a send box. Stable ids `platform:channel:msgid`, dedupe set per connector surviving reconnects.

## 4. Windows / monitors
Persist per window (SQLite `windows` + JSON export): type, instance id, x/y/size, monitor id + relative position, DPI scale, platforms, channel filters, font size, spacing, opacity, theme, always-on-top, visible, scroll behavior, preset. Types: unified, per-platform, priority, missed, first-timers, composer, status. Multiples allowed. Monitor disconnect → snap to nearest monitor / primary, remember original to restore on reconnect; DPI changes recompute from relative geometry. Profiles: Streaming, Gaming, Editing, IRL, Minimal, Full Monitoring (switch via UI/hotkey/Stream Deck). Edge `--app` windows are placed with `--window-position/--window-size` and a Win32 helper (pywin32/ctypes) for monitor enumeration, always-on-top, click-through; limit documented, native shell removes it.

## 5. Continuous two-monitor feed
Linked-window group: one logical feed, windows ordered A→B with a defined overflow direction. The server owns the ordered message list and a per-group row layout; window A shows newest rows, rows that scroll past A's top are rendered at B's bottom (and vice versa) using the measured row height, not duplicated. All clients render from the same sequence numbers + shared scroll clock so they stay in sync; resize recomputes capacity per window. Fallback: independent feeds.

## 6. Local priority algorithm (explainable)
Score = Σ weighted signals with caps, shown as reason chips: direct question (`?`, interrogatives, stream-topic keywords), mention of name/channel, first-time chatter, returning/regular (from `Data\profiles`), ongoing conversation with me (replied to my message / thread), repeated unanswered question (decays, capped), learned response-likelihood, configured keywords, sender boost/mute. Anti-abuse: per-user cooldown, duplicate/similar-text suppression, repeated-mention cap, caps/emote-spam penalty. Subscriber status is a small optional weight, default 0. Thresholds → card tiers. Rules editable in UI (`rules.json`), per-rule reset, full reset to defaults, "why this score" panel. Unit tests with fixture chats.

## 7. Optional AI
Only for uncertain band (score within margin of threshold) and event-significant messages; async, never blocks display (message appears with local score immediately, upgrades if AI returns). Providers pluggable (Anthropic/OpenAI/local Ollama), daily/monthly spend cap, latency timeout (e.g. 2 s), cache by normalized text hash, batching, usage report. Modes: Local Only / AI Assisted / Automatic Fallback (on error, timeout, cap → local). Prompt includes only minimal context, no PII beyond username; API key via Credential Manager.

## 8. Cards and reply detection
Card states: new → pinned/open → answered (fade 15 s) / snoozed / dismissed / missed (after 5 min, recoverable) / reopened. Both timers configurable; max cards, sorting, stacking, compact mode so gameplay isn't covered. Actions: pin, dismiss, snooze, answer, reopen, change priority, view context, mute/boost viewer.
Reply signals in order of build: (1) typed in Multi composer, (2) own message seen via platform (reply_parent or @mention of the viewer), (3) click, (4) global hotkeys, (5) Stream Deck (HTTP/WS endpoints + Stream Deck plugin or Companion/Streamer.bot-free URL actions), (6) optional voice: reuse Listen's faster-whisper, rolling transcript → semantic match to pending questions (embeddings or keyword overlap), thresholded; low-confidence → "possible answer" chip for one-click confirm, never auto-close. Mic off by default, visible indicator, no audio stored, transcript retention short and configurable.

## 9. Learning and retention
Log events (answered typed/verbal, ignored, dismissed, reopened, manual boost, missed) with features. Per-feature weight adjustments with bounded step, decay over time, minimum-evidence threshold and per-event clamp so a few mistakes cannot lock a bias; "What I learned" view; manual edit, reset. Retention: messages N days (default 30), learning aggregates longer, voice transcripts hours; export/purge per viewer.

## 10. Cross-module contracts
Define `Docs\PinguinoMulti\CONTRACTS.md` + JSON schemas: `ChatMessage`, `PriorityDecision`, `Card`, `ReplyEvent`. Streamer-first: Multi publishes `multi.claim {messageId, userId, ttl}` on the Suite bus; a small Router addition reads a Streamer.bot global variable/HTTP poll (`multi.claims`) and returns `pass`/hold for PinguinoChat while a claim is active (configurable delay, default off). Because the router and bots are Streamer.bot C# pasted copies, change goes into `Shared\PinguinoBots.cs.txt` + `node Shared\sync-shared.mjs`, plus a `Firsts` hook. Loop prevention: Multi tags its own sent messages, ignores bot accounts (shared list), single collector per platform (Multi is the reader; bots keep Streamer.bot triggers until a later unit decides).

## 11. Performance and security
Message→screen target < 100 ms local; virtualized list (cap ~500 rendered rows/window); burst handling with coalescing; SQLite WAL, pruning job; Whisper off by default and CPU-limited/quantized, GPU only if idle headroom; AI strictly async; connection health panel with latency/reconnect counts; watchdog restart via Suite supervisor; localhost-only bind with per-session token (like Link's `x-link-token`); input sanitization (XSS in chat HTML), no secrets in logs.

## 12. Roadmap
- **M1 (first milestone, Twitch):** module skeleton + `modules.json` entry; Twitch auth; EventSub chat read with reconnect/dedupe; SQLite store; window manager with persisted layouts (≥ unified, priority, missed, composer, status); local priority engine + editable rules + explain; priority cards with timers; manual ack + typed reply (Helix with `reply_parent_message_id`) tracking; tests.
- M2: profiles/presets, linked two-monitor feed, hotkeys, viewer history/search, learning v1.
- M3: Discord, YouTube, Kick connectors; Stream Deck; AI-assisted mode.
- M4: voice reply detection; TikTok (unofficial, read-only); bot streamer-first contract.
- M5: native shell (Unit 01), macOS, mobile compact view (via Link/Tailscale).
Extra ideas: stream-event cards (sub/raid/bits), per-viewer notes, "unanswered recap" after stream, scheduled auto-snooze when in-game, translation, moderation quick-actions, OBS scene-aware preset switching via Link.

## Twitch auth decision (reuse site OAuth) — needs one change
Existing site Twitch login uses only `user:read:subscriptions user:read:moderated_channels` and a code comment warns that changing scopes forces every viewer to re-approve. So: do NOT widen the viewer login. Instead add a broadcaster-only "Connect Multi" flow modeled on the existing roles flow (`worker/index.js` ~158/1159, separate scope constant), scopes `user:read:chat user:write:chat` (+ `moderator:read:followers`, `channel:read:subscriptions` later). Token handed to the local module via a loopback redirect (`http://127.0.0.1:8766/auth/callback`) so refresh tokens live in Credential Manager, not on the site. Site is a separate git repo (Railway) → this change is its own reviewed commit. Open item: Twitch app must register the extra redirect URI.

## Execution model
- Permanent planning session = this one; Unit 03 docs under `Docs\PinguinoMulti\`.
- Task sessions start with `/plan`, one per M1 slice: (a) skeleton+store+API contracts, (b) Twitch auth+EventSub, (c) priority engine+rules+tests, (d) window manager+UI, (e) cards+reply tracking. Each ends with a result note in `Docs\PinguinoMulti\SessionsArchive\` then session archived.

## Critical files
- New: `Suite\modules\multi\**`, `Docs\PinguinoMulti\**`, entry in `Suite\modules.json`
- Edit later: `Suite\suite\suite.py` (module UI link only), `PinguinoSite\worker\index.js` (Connect Multi flow), `Shared\PinguinoBots.cs.txt` (+sync)
- Reuse: `modules\listen\asr.py`, `Suite` WS bus, `Data\profiles`, `Tests\` runner pattern (`run-*.ps1`)

## Verification
- Unit tests for scoring/dedupe/card timers via pytest with fixture chat logs from `Data\chat_logs`.
- Replay harness feeding recorded chat into the pipeline; burst test (1000 msg/s).
- Live: connect Twitch test channel, kill network → reconnect without duplicates; move/resize/close windows, restart, confirm restore; unplug monitor simulation; typed reply marks card answered; AI off by default and everything works.
- Suite health: `modules.json` start/stop from tray, `/api/status` OK.
