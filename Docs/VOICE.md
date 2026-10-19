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
