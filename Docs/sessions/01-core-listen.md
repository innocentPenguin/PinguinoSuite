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
**Unverified in the real app (mock/browser-pane only):** Economy, Timers, Canned commands, Overlay fit pages; Report a problem box (Dataeedback output); the module-reset fix in the running Listen/Multi/Comm (watch a few minutes); Listen card controls (013 confirmed them on the live module page at 127.0.0.1:8765: PASS); fullscreen; sounds page; chat-sent sound; real signed update. Shell pages need the core token, so a plain browser cannot reach them: someone with the real window must click them.
**Open questions to Ivan (defaults):** create the real signing key now (default: wait for his word); permanently hide the old junk Listen rows (default: filter only).
**Where things are:** shell UI `App/src/index.html` (CRLF, patch via Python), core `Suite/suite/suite.py` (+ feedback.py), Listen `Suite/modules/listen/`, updater `Suite/updater`, installer `Installer/`. Test commands in section 3.
