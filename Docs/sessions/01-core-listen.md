# Session notes: UNIT 01 (Suite Core / shell lead + Listen module owner)

Last updated 2026-10-23 (final hand-over to the new supervisor "20 - Suite"; 01 has stopped coding). Session id `9e804717-c369-472f-8998-483f8aefd7a3`.

## 1. What I built or changed, and why
Requests come from 00 (relaying Ivan). Main work, newest first (commit hashes in git):
- **Module view reset bug** (031bf59). Ivan: while in Listen or Comm the Suite "puts him back on that module's home page". Cause: core `Module.refresh()` called a module "starting" after ONE missed 1.5 s health ping; the shell then swapped the iframe for a card and mounted a fresh one. Fix in core (4 missed pings in a row) and shell (loaded frames never rebuilt by redraws; grace period; fewer reload paths).
- **Listen review card** (584cfba): word highlight while playing, scrub bar, speed, loop, error note saved with the line (`segments.note`, also in gold.jsonl). Ivan asked for follow-along, play controls, and a box to describe the error.
- **Report a problem** (5d96aa1): floating button on every page; core `suite/feedback.py` + `/api/feedback` writes `Data\feedback\<time>-<route>.md/.json` + screenshots.
- **Canned commands page** (34e4af2), **Economy, Timers, Overlay fit pages** (bd8cc16): for 02/022/023 Host endpoints.
- **Listen sentence-level segments** (d780696): shorter subtitle lines (`SEG_MAX_S=12`, `SEG_GAP_S=0.8` in asr.py).
- **Release dry run** (e3491c2, Docs/RELEASE_DRYRUN.md): signed release, full and lite-minimal installs, verify/repair/eject.
- **Audit rounds 1-3** (a265531, 34e0dcf and earlier): test isolation (`PINGUINO_LOG_DIR`), nosniff on sounds, chat-sent poll reset.
- Earlier: updater (Suite/updater), installer, sounds, fullscreen etc. (see `git log --author` / messages).

## 2. Decisions and failures
- Shell fix is belt and braces (core hysteresis + shell guards) because a frame reload loses user state anyway.
- Feedback stored as plain files, not in a DB, so 00 can just read them. Secrets pattern-blanked.
- Listen tests must use a temp data dir (`LISTEN_DATA_DIR`): one of my test runs wrote a row into the real ears.db (removed by me, only my row).
- Failed/learned: `hostJ` always POSTs (use `hostGet` for GET endpoints); node ESM imports need file:/// URLs; updater command word must come first; release versions must be plain numeric; heredocs mangle backslashes (write files with Write tool or Python).

## 3. Pass on to the next session
- Only 00 builds/launches/restarts. I never launch. Shared working tree: commit with targeted `git add`; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; I do not push.
- `App/src/index.html` is CRLF, ~260 KB: patch via Python normalising `\r\n`. Syntax check: extract script to a file and `node --check`.
- Tests: `Suite/.venv/Scripts/python.exe -m unittest discover -s tests` in `Suite` (91) and in `Suite/modules/listen` (24); updater: `node --test` in `Suite/updater` (38). System python lacks requests/numpy.
- UI check without the app: a small mock server (core + Host + module pages) in a scratchpad plus the browser pane; not kept in the repo.
- Restart needs: core change = core rebuild; shell = app rebuild; Listen = module restart.
- NEVER go live in OBS, never touch OBS, never delete `%AppData%\BVQ`, never click "Remove plaintext".
- Not verified in the real app: new Economy/Timers/Canned/Overlay pages against the real Host, fullscreen, sounds page, chat-sent sound, real signed release/update, Report a problem, Listen card controls, the reset fix.

## 4. Future ideas (priority)
1. Real-app click-through of everything in the "not verified" list above after the next rebuild.
2. Real signing key + signed release (see Docs/RELEASE_DRYRUN.md).
3. Show Report a problem items inside the Suite (list view, mark handled).
4. Listen: use the saved notes to guide learning/regrade; waveform in the review card.
5. Lite install on demand UI (profile/verify/eject contract is ready for 012).

## 5. Chat history
`C:\Users\ivanm\.claude\projects\D--\9e804717-c369-472f-8998-483f8aefd7a3.jsonl`. Grep for: `module reset`, `Report a problem`, `confidence worst-first`, `Hysteresis`, `RELEASE_DRYRUN`, `00 -> 01`.

## 6. Things Ivan may be forgetting
- The one-time signing-key steps are still his: create the real Ed25519 pair, seal the private seed with `Installer/Seal-InstallKey.bat`, publish the public key in install.json. Until then releases are unsigned or dry-run only.
- Rebuilds pending for the latest fixes (core + app + Listen restart); nothing from 031bf59 onward is live yet.
- The Report-a-problem folder (Data\feedback) will contain screenshots of the screen; keep it out of any push/zip (check .gitignore covers Data).
- Core test suite earlier polluted real logs/DB twice before isolation fixes; check ears.db and events.jsonl look sane.
- Uncommitted files by others in the tree (Deploy/, PinguinoSite-*, live_state.js) are not mine.

## 7. HAND-OVER (final state, read this first)
**Commits made after the sections above** (all local, not pushed): 73df6f8 (shell: module `op:external` links may be loopback http, opened with `__TAURI__.shell.open`; adds `shell:allow-open` to App/src-tauri/capabilities/default.json), bccadcd (App/src-tauri/tauri.conf.json `plugins.shell.open` regex = http(s) only), da0d8b2 (updater eject removes folders it leaves empty), 5502618 + c1de3f4 (Listen review hides hallucinated sentences: `(end-start)*40 >= length(text)` in review_next; 43 old junk rows in ears.db hidden, none deleted), fbea143 (these notes).
**PENDING REBUILD / RESTART (nothing below is live yet):**
- Full Tauri rebuild: 73df6f8 + bccadcd (capability + tauri.conf change, not just the frontend), plus 013's a74f201 (Master View setgame on activity change).
- Listen module restart: 5502618 (and 584cfba was already restarted at 05:01).
- No core rebuild pending. Updater is Node (no rebuild).
**Workers I supervised:** 012 Lite (scratch lite-minimal install/verify/repair/eject PASSED; doing: poll Link instead of fixed 3 s, replay-stats card, "Quit and stop Link"), 013 Master View (a74f201 setgame, 0813384 title/tags). Both were told to finish, write their Docs/sessions files and stop. Their notes: Docs/sessions/012-pinguinolite.md and 013's file.
**Signing-key steps (Ivan, one time, not done):** create the real Ed25519 key pair, seal the private seed with Installer/Seal-InstallKey.bat, put the public key in install.json (`pubkey`); then `Build-Release --sign-key`. Until then only unsigned/dry-run releases exist (Docs/RELEASE_DRYRUN.md). A real minimal PC must be installed with --github/--url or `--local ... --update-from owner/name`; a plain --local install records no update source by design.
**Unverified in the real app (mock/browser-pane only, updated 2026-10-23):** Economy, Timers, Canned commands pages (payloads checked against the Host source and a mock); Overlay fit (fixed to read `.options`, commit 64d49c5, needs shell rebuild); Problem reports page + `POST /api/feedback/handled` (commit 2f4e881, needs core + shell rebuild; the live core had no GET /api/feedback); Report a problem box output in `Dataeedback`; the module-reset fix in the running Listen/Multi/Comm (watch a few minutes); Listen review card waveform (`GET /api/segments/{id}/peaks`) and the "noted lines first" checkbox (commit e80311b, needs a Listen restart; tests pass, never seen in the live page); Listen bot-speech filter (119d8d9 + fixes 797a1b1; needs a Listen restart and a live Voice) and Listen Settings panel (Learn from my notes, Bot speech, note conflicts; ab602ac, 797a1b1); notes learning (0a23d0a, 797a1b1, 4100da7); Console Diagnostics block and GET /api/modules/diag (9123c15, d67823a, needs core + shell rebuild); module recovery changes (parallel pings, 4 s timeout after slow answers, guarded health loop, transition reasons in events.jsonl; a0fdfea, core rebuild); GET /api/selfcheck (0ab2c3c, core rebuild); Test go-live two-click simulation with 15 min expiry (2bc2982); registry test (94fcfe4, test only); fullscreen; sounds page; chat-sent sound; real signed update. Shell pages need the core token, so a plain browser cannot reach them: someone with the real window must click them.
**Open questions to Ivan (defaults):** create the real signing key now (default: wait for his word); permanently hide the old junk Listen rows (default: filter only).
**Where things are:** shell UI `App/src/index.html` (CRLF, patch via Python), core `Suite/suite/suite.py` (+ feedback.py), Listen `Suite/modules/listen/`, updater `Suite/updater`, installer `Installer/`. Test commands in section 3.

**012 Lite final (reported to me, stopped coding):** commits ff8c379, b41c28e, 141a126 (+ earlier c2dada3, 8993507, 2dbbe6c, fd20321, 9671ad7, b6e4f8a), all local/unpushed. Needs a Lite release rebuild (`--features custom-protocol`) for everything since b6e4f8a+9671ad7. Open: Lite buttons/quit dialog/F11/icon not clicked live; replay parser never run on a real replay; Lite GitHub repo has no release/manifest; a minimal PC must be installed with --github/--url/--update-from or Install says "no update source"; Modules catalog (04) vs profile can disagree. Its notes: Docs/sessions/012-pinguinolite.md (not committed by 012).
**013 Master View:** did not get the stop order (messaging was throttled); its commits a74f201, 0813384.

### 7b. Read-only verification 2026-10-23 05:50-05:58 (23 - Listen/Core, running app, HTTP GET only)
| Check | Result |
|---|---|
| Suite core tests / Listen tests (temp dirs) | 91 OK / 24 OK |
| Core 8760 `/` | 200. `/api/*` needs the per-launch token (401), so /api/state and module health could not be read; module state read from `Suite\logs\events.jsonl` instead |
| `/api/feedback` on the running core | OPTIONS answers 405 `Allow: POST`: running core has only POST /api/feedback (GET list is not in the live build; expected, it is newer) |
| Module ports 8765/8766/7777/8770/8771/8772 `/` polled every ~12 s for 3 min | all 200 every sample (no flaps seen from outside) |
| Core-side module state (events.jsonl) | after the 05:50 restart all running. **link went "starting" at 05:54:59 and no "running" followed in the next 3+ min**, although Link `/api/health` answered 200 in 30-1000 ms (slow, near the core's 1.5 s ping timeout) and the machine was low on memory (bash fork failed). Needs a look by 20/100: a one-off 4-miss flip is by design, but a missing recovery is not. Check the Link row in the shell |
| Listen 8765 `/`, `/api/status` (asr ready, large-v3-turbo on cuda, live session on), `/api/review/next` | 200, a segment comes back |
| Shot-Quiet screenshot | taken (Spotify page). The "Report a problem" panel is drawn as an open, unstyled block at the right edge and the fab floats mid-window, so the fixed-position styling is not applying in the real window. Cause not known (CSS looks right in source); could be the Shot-Quiet capture. **The text there read "Dataeedback": `` in a template literal is a form feed. Fixed in source (not live until shell rebuild)** |
