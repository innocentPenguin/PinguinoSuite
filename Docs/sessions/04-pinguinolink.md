# Session 04 - PinguinoLink (notes, updated 2026-10-23)

I am the permanent lead of UNIT 04 PINGUINOLINK. Code: `Suite/modules/link/`. Docs: `Docs/PinguinoLink/` (INDEX.md is the source map). Coordinator: session 00. Lite app: session 012.

## 1. What I built and why
Everything is committed in the git repo `D:\PinguinoSuite` (nothing pushed to GitHub, on purpose).

- **Link core (earlier work)**: Tailscale-only device mesh with pairing codes and per-peer tokens, OBS control through obs-websocket (macro allow-list, risky actions need a second click), dashboard page, settings card, console log (`Data/runtime/console/link.jsonl`), doctor with opt-in AI (off by default).
- **PinguinoLite contract** (commits 95d10a7, 19bb22d, 94be3b7): `src/lite.mjs` writes `Data\lite\status.json`, `installed.json`, `modules_catalog.json`, `update_status.json`, `update_manifest.json` and reads `requests\*.json` (see `Docs/LITE_APP.md`). Why: 00 relayed that Lite needs a file-drop contract with Link.
- **Local-only updates** (58ddc58, bcf4fd9, d62daf7, 022f143): `src/pkg.mjs` installs/updates/uninstalls/rolls back modules from hash-checked zips in `Data\lite\packages`, `cli.mjs pack <module>` makes a package, paired PCs share update files over the mesh. Why: Ivan chose "local-only, no GitHub" (relayed by 00) after first saying "local folder first, then check network access to find streaming pc, then can we use private github, ill just need to login".
- **Lite self-update apply** (d0674ab): after the click in Lite, a detached helper (`src/applyupdate.mjs`) waits for Lite to close, re-checks the hash, backs up the install folder, runs the setup with `/S`, relaunches, and restores the old version if the installer fails. Why: Ivan said YES (relayed by 00). Lite quitting kills its Link child, so the helper has to run detached.
- **Never go live** (75cec3b, b2edff4): Ivan's hard rule "NEVER go live or test going live in OBS". Tests set `PINGUINO_NEVER_REAL_OBS=1` which blocks port 4455 in `src/obs.mjs`; tests no longer write to the real Console log; Start Stream is OFF by default (setting `safety.allowStartStream`), enforced in `runMacro` and `runRequests` (403 for StartStream/ToggleStream); the default `start` macro was removed from new configs.
- **Lite reuses the running Link** (fd10c1a): a Lite-started `serve` exits 0 when a Link already answers on the port (only when `PINGUINO_LITE_DIR` is set and no `PINGUINO_API_TOKEN`).
- **Audit round 1** (ce70ea9, 3dc9d70): update cannot double-start, busy flag cleared, real `installed_at`.
- **Game presence** (Discord status from the gaming PC): designed (b1fea2d), then CANCELLED by Ivan. Design doc kept as `Docs/PinguinoLink/GAME_PRESENCE.md`; no code exists.

## 2. Decisions and failures
- Local-only update source, no internet (Ivan).
- OBS port 4455 stays open on 0.0.0.0 for now: Ivan's gaming PC uses a replay-buffer clipping hotkey; restrict it only after Link fully replaces that.
- Zip is read in-process (no shell, zip-slip protected, 5000 files, 300 MB cap).
- Failures / gotchas I hit: `python -` in a bash command hangs (never use it); heredoc quoting and `sed` eat backslashes (use the Edit tool for regexes with `\`); tests once wrote into the real `Data\lite` and the real Console log (now gated by tmpdir and `PINGUINO_NEVER_REAL_OBS`); the 401 noise in the log came from a Link process started before the core's persistent module key existed (core commit 957b5ec, `Data\runtime\module_secret`), gone after the restart.
- `git add -A Docs` once swept other sessions' Docs files into my commit b2edff4. Use explicit paths.

## 3. For the next session
- Run tests (from `Suite/modules/link`): `node src/selfcheck.mjs`, `meshcheck`, `macrocheck`, `settingscheck`, `remotecheck`, `litecheck`, `pkgcheck`, `updcheck`, `applycheck`, `reusecheck`. All pass as of 2026-10-23. remotecheck could rarely flake on a port clash (range widened).
- Only session 00 launches/restarts the Suite app and Link. A Link restart is needed for any new Link commit to take effect.
- Open: module start/stop/restart from Lite is not built (Lite gets "not available yet"). Other modules (voice, spotify, multi, listen) have no `"version"` in `module.json`, so `pack` refuses them.
- Never send chat lines from Link; if ever needed use the Host say endpoint only. No key injection, no custom VPN/encryption, no remote shell.

## 4. Future plans, in priority order
1. Module start/stop/restart from Lite (via the Suite core).
2. Add `"version"` to every module's `module.json` (their owners) so they can be packed and updated.
3. Real two-PC test over Tailscale (pairing, update fetch, macro forwarding).
4. Real OBS test of read-only calls once the password is in the vault.
5. Restrict OBS port 4455 to 127.0.0.1 once Link replaces the replay-buffer hotkey.
6. macOS pass.

## 5. Chat history
Session id `a5adf387-08ff-407b-9d4d-e8bfc4ad871e`. Transcript: `C:\Users\ivanm\.claude\projects\D--\a5adf387-08ff-407b-9d4d-e8bfc4ad871e.jsonl`. Grep for: `selfupdate-apply`, `allowStartStream`, `PINGUINO_NEVER_REAL_OBS`, `GAME_PRESENCE`, `reusecheck`, `audit 1`. The summary at the start of the later part of the chat covers earlier work.

## 6. Things Ivan may be forgetting
- The OBS WebSocket password is not in the key vault (`OBS_WS_PASSWORD`), so real OBS control from Link is untested.
- Link role: this PC is still configured as a client; set it to hub (with confirmation) on the streaming PC and match the real scene/input names in the macros (BRB, Main, Mic/Aux are guesses).
- Tailscale was Stopped; pairing between two PCs has never been tested.
- OBS port 4455 listens on all interfaces (left on purpose, but it is an exposure).
- Start Stream is disabled by default; to use it he must switch on "Allow Start Stream" in Link settings himself.
- The running Link must be restarted by 00 to run the latest code; Lite apply (self-update) has only been tested with a fake installer, and no built PinguinoLite.exe existed when I last looked.
- Nothing has been pushed to GitHub.
