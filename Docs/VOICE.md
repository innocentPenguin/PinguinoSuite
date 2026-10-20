# PenguinComm > Speak (module `voice`, port 8772; formerly "Pinguino Voice")

A talking co-host. Named **personas** (voice, speed, pitch, effects, catchphrases, intro/outro, stinger sound, own wording) announce follows, subs, resubs, gifts, cheers, raids, redeems, stream online/offline and typed `!tts`. **Silent unless the master switch is ON** (default OFF). Page: nav "Voice" (module `ui`). Code: `Suite\modules\voice` (stdlib server, numpy effects, Windows SAPI via a resident PowerShell worker, winsound playback). Data: `Data\runtime\voice\` (`config.json`, `presets\`, `backups\`, `history.jsonl`).

## Safety rules (always on)
- Master OFF / muted / quiet-hours-mute: nothing is synthesised or played; the attempt is logged with its outcome (Console source `voice`).
- Secrets are never read: tokens, `oauth:`, keys, passwords, long random strings, e-mails, IPs, card-like numbers become "a secret". Links become "a link". Profanity mask/skip, length cut/skip, repeat squash, blocked people.
- Page **Preview** buttons play inside the page only (work while master is OFF). Test events and Say go through the real pipeline and are heard only when master is ON.
- Voice *commands* (Listen / Voice Studio) stay silent in chat; Pinguino Voice only adds optional on-PC spoken feedback.

## What is configurable (every setting has a one-line help under it)
Personas (add/duplicate/delete, default), per-event persona + wording variants (`min:N|text` for amount tiers) + min amount, cooldown, priority, stinger, read-message, only-live; per-role, per-platform, per-person persona; `!tts` (min role); limits (length, rate/min, per-person wait, profanity, links, emoji, repeats, names cleanup, blocked people, own bad words); queue (queue / interrupt / drop-new, max, max age, gap, interrupt priority, merge bursts); quiet hours (mute or whisper); pronunciation dictionary; master volume; accent colour + dark/light; presets (5 built in + yours), export/import JSON, auto-backups (15), reset.
Template variables: `{user} {amount} {tier} {viewers} {bits} {what} {message} {persona} {catch} {time}`.

## API (127.0.0.1:8772; the page is same-origin, others need the module/app token)
GET `/api/status /api/config /api/voices /api/history /api/presets /api/export /api/prestream /api/help /api/selftest` · POST `/api/config /api/master {on} /api/mute {minutes} /api/speak {text,user,role,platform,persona} /api/event {kind,user,amount,...} /api/test-event {kind} /api/preview {persona,text,config} /api/stop /api/replay /api/preset {op: save|load|delete|import|restore|reset} /api/chat-command`.
Events come from the Host: the module polls `GET :8770/api/activity` (starts from "now", never replays old events). Other modules and Actions steps can `POST /api/event`.
Chat: Actions & Events trigger `!tts` / `!voice` + step `module_command` to `http://127.0.0.1:8772/api/chat-command` (`!tts` must be enabled in the page; `!voice mute|unmute|stop|again` mods only). It always replies silently.

## Tests
`cd Suite\modules\voice`, then `..\..\.venv\Scripts\python.exe -m unittest discover -s tests` (fake engine, no audio).

## Apply
A new module is a drop-in manifest, discovered at core start: needs a core **relaunch** (no rebuild; no core .py changed). After that, module code changes need only `Update-Module.bat voice`.

## Cycle 2 additions
- **Cloud voices (optional, OFF by default):** persona engine `openai` (voice name + optional acting `style` with gpt-4o-mini-tts) or `elevenlabs` (voice id). Needs vault keys `VOICE_OPENAI_KEY` / `VOICE_ELEVENLABS_KEY` (declared in the manifest, test buttons) and the switch "Allow cloud voices". Only the finished, secret-free sentence is sent; failures fall back to the Windows voice (switchable).
- **Schedule:** spoken reminders (every N min, jitter, needs-activity, persona, random lines). Silent whenever the master is off/muted.
- **Output device** (e.g. a virtual cable) via sounddevice, nicknames (how a name is said), repeat suppression, spoken voice-command confirmation (`POST /api/event {"kind":"voice_cmd","what":"skip"}`, off by default), Rehearse all, `/api/integrations`, `/api/devices`, `/api/test-cloud`, `/api/timer-fire`.
- Page uses the Suite theme (`theme.css` tokens + live theme messages).

## Cycle 3 additions
Milestones (every Nth follow/sub/raid, or every N bits/viewers; daily or forever; counted even while silent; `GET /api/counters`, `POST /api/counters-reset`), persona by time of day, your own WAV sounds as persona/event stingers (`/api/sounds`, `/api/sound-upload` max 2 MB, file names sanitised, only inside `Data\runtime\voice\sounds`), history CSV export (`/api/history.csv`), output-device list de-duplicated.

## Stream-day safety (cycle 5)
Default volume 60 %, master OFF, chat/!tts/cloud all OFF. **Sound check** button (page header, same-origin click only) plays one line on the real output even with the master OFF. Feedback loop with Listen: Speak publishes when it plays audio: `GET :8772/api/speech-intervals?since=<epoch>` -> `{speaking, intervals:[[start,end],...]}` and `Data\runtime\voice\speaking.json` `{speaking, until}`; Listen may skip transcribing those moments. Best fix: play the bot on headphones / another output device. Pre-stream items `voice-output` (voice + device + volume) and `voice-loop` (warn when master ON and default speakers). Host-feed outages log at debug (one warn per 30 min after the first 90 s).

## Cycle 6: hourly review + spoken control
**Page tab "Review & control".**

*Hourly review* (rule-based, local, never speaks). While the Host says you are live, every `review.interval_min` (60) minutes, and once more when the stream ends, it compares what Speak said with your Listen transcript, the chat logs, the Listen voice log and the Console logs. Checks: talk-overs (it spoke while you did), complaints/praise in your words ("shut up", "too loud", "nice"), mispronounced names, repeats, drops/play errors, master on but silent, Console problems, spoken-control activity. Score = 100 minus 8 per warning and 20 per serious finding. Reports: `Data\runtime\voice\reports` (last 48). Findings carry one-click suggestions limited to a safe allow-list (volume, rate, wait, dedupe, queue size/age, max chars). Serious findings are appended to `Data\runtime\voice\incidents.jsonl`.

*Link to Claude:* a module cannot start or wake a Claude session. The live hook is `incidents.jsonl` / `GET /api/incidents`; a Claude session can watch it (Monitor) and investigate with a fork when a line appears.

*Spoken control* (OFF by default; only the switch on that page turns it on, never a config POST, preset, import or restore). Say "pinguinobot change the game to X", "... change the title to X", "... timeout NAME for 5 minutes", then "pinguinobot confirm" (or press Confirm; expires after 25 s). Safety: strict grammar, fuzzy wake word, unsure transcript lines ignored, never obeys its own voice, name must resolve to exactly one recent chatter, protected names, longest timeout 600 s, per-action allow switches, secrets/profanity/length refused, cooldown, full audit log (`control.jsonl`, Console source "control"). "Try a sentence" rehearses without doing anything.
Needs Host endpoints `POST /api/channel/update {game|title}` and `POST /api/mod/timeout {user,seconds,reason}` (requested from 02); until they exist, actions report "unsupported".

New API: GET `/api/control /api/review/reports /api/review/report?id= /api/incidents` · POST `/api/control/enable|confirm|cancel|try`, `/api/review/run|apply`. Pre-stream items `voice-control`, `voice-review`. Tests: 65 (`test_review_control.py` adds 19).
Apply: `Update-Module.bat voice -NoBuild` (manifest help only changed; Listen VOD fix needs `Update-Module.bat listen -NoBuild`).
