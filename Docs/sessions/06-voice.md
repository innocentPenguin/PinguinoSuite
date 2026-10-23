# Session notes: 06 Voice (Speak + Listen voice work)

Last updated: 2026-10-23 05:30. Session id: local_ (this session; transcript below). Docs: `Docs\VOICE.md` (Cycle 6 and 7), `Docs\INDEX.md` ("Voice (owner: 06)"). Speak = module `voice`, port 8772, Python venv `Suite\.venv`, data in `Data\runtime\voice`. Listen = port 8765, Host = C# port 8770.

## 1. What I did and why
- **Speak core:** pipeline master/mute/quiet gate, limits, persona, queue, play (`config.py`, `brain.py`, `engine.py`, `textproc.py`, `server.py`). Master switch OFF by default.
- **Hourly self-review** (`review.py`): rule-based, reads the Listen transcript, chat logs, voice log and Console logs; writes reports and `incidents.jsonl`; one-click suggestions limited to a SAFE_SETS allow-list.
- **Spoken control** (`voicectl.py`): wake word, strict grammar, confirm step (25 s), caps, protected names (the bot itself is always protected), ignores its own voice, audit log `control.jsonl`. Game/title/timeout go through Host `/api/channel/update` and `/api/mod/timeout`. OFF by default.
- **Listen fixes** (commits to 2026-10-22): VODs-button memory crash, ingest runaway loop (attempt cap, reuse of finished downloads, 6 GB sources cap), Retry/Restart UI, menu freeze (`/api/sessions` grouped query), port 8765 busy guard, voice-command safety (`action_allowed`: Listen can never call obs/stream), inline-editable transcript review (commit 8c2b3fe).
- **Latest:** one-line log for client disconnects (857a7f9), audit round 1 (909475d), `!speak` alias for `!tts` plus audio routing design (26afe27).
- Tests: Speak 73 (`Suite\modules\voice\tests`), Listen 14. Run with `Suite\.venv\Scripts\python.exe -m unittest discover -s tests` inside each module.

## 2. Decisions and failed attempts
- HARD RULE: never go live or test going live in OBS; no voice path may start the stream. Raid-by-voice is NOT built; it may only create the same pending-confirm request as a typed `!raid` and waits for 02's endpoint.
- Modules never post chat directly; anything said in chat goes through the Host say endpoint. Never read secrets aloud.
- `control.enabled` and the master switch change only through their own endpoints and only Ivan turns them on.
- A module cannot spawn or wake a Claude session; `incidents.jsonl` / `/api/incidents` is the hook a session can watch.
- Heredoc/CRLF pitfalls when patching files from bash: use Python with newline preservation or the Edit tool. `psutil` is not installed in the venv.
- Port 8765 had stray holders once: kill by command line, then `Update-Module.bat listen`.

## 3. For the next session
- Nothing running needs a restart that I know of, but confirm `Update-Module.bat voice -NoBuild` and `listen -NoBuild` were applied after 26afe27 and 8c2b3fe (the Host must re-read the voice manifest to route `!speak`).
- Verify live (never verified): spoken control against a real transcript, the hourly review on real stream data, real playback and cloud voices, `!speak` once enabled, the inline transcript editor on the Learn tab.
- Audit rounds 2 and 3 of 3 for Voice were not done (round 1 read only `voicectl.py` and `review.py`; still unread this audit: `server.py`, `brain.py`, `config.py`, `engine.py`, `textproc.py`).

## 4. Future plans, by priority
1. Audit rounds 2 and 3 (the unread files above) with tests.
2. Raid-by-voice once 02 publishes the endpoint (pending-confirm only).
3. Core `/api/voice/dispatch` should also refuse obs/stream actions (01's area; Listen already does).
4. Speak a mic-lost alert; a memory watchdog for VOD jobs; tune the hourly review on a real stream.
5. `listen.log` rotation (supervisor/core; the file was 82 MB).

## 5. Where my history lives
- Transcript: `C:\Users\ivanm\.claude\projects\D--\b05675bb-975f-499e-a447-e6096677f645.jsonl` (grep it).
- Code history: `git log -- Suite/modules/voice Suite/modules/listen` (my commits end with the Co-Authored-By Sonnet 5.5 line).
- Data: `Data\runtime\voice` (history.jsonl, incidents.jsonl, reports, control.jsonl), logs `Suite\logs\voice.log`, `Data\runtime\console\voice.jsonl`.

## 6. Things Ivan may be forgetting
1. The 24 old `vod-*.mp4` files (about 21 GB) in Listen's sources are untouched and await your say-so; the duplicate-VOD cleanup is a list for you.
2. Master switch and spoken control are both OFF; nothing speaks or obeys until you switch them on.
3. `!speak`: approved by Ivan (!speak, 100 points via redeem, anyone when redeemed, mod-only typed); still open: whether a second virtual cable for the voice is OK.
4. Voice has never been tried on a real stream: do one supervised test with the master ON before relying on it.
