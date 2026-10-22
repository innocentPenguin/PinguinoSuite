# In-app updates (Suite and Lite) — design

Goal: the installer puts the base on a PC once; after that the app updates itself. Reuses `Suite/updater/lib` (manifest + sha256, optional Ed25519, `github` source, DPAPI token at `Data/runtime/update_token.dpapi`) and `App/Update-Module.ps1`.

## Suite

**Check.** Settings > Updates card (button "Check for updates") plus a quiet check once a day at startup. Core endpoint `GET /api/update/check` calls the updater `check` with the github source (private repo, read-only key already stored) and compares the installed `install.json` version/commit with the latest release.

**What changed.** The release manifest gets a per-component map `components: {shell, core, host, listen, multi, link, spotify, voice, site}` with a version/hash each. The card lists only the ones that differ, with release notes.

**Apply, per component.**
- Modules (Listen, Multi, Link, Spotify, Voice): own "Update" button. Pulls only that component's files, then restarts only that module (Update-Module.ps1 logic via `Data/runtime/control`). No app restart.
- Shell / core / Host: button says "needs restart". The files are staged, and the swap happens on the next quit/launch by the updater helper (same pattern as `applyupdate.mjs`: wait for exit, verify sha256, back up, swap, relaunch).

**Safety.**
- Blocked while live: `/api/live` (stream uptime) — the button is disabled with the reason.
- Backup of the replaced files to `Data/updates/backup/<from>-<time>`, so "Roll back" is one click and restores the previous version.
- Never touches `Data/`, the vault or config. Sha256 on every file, paths confined to the install dir, one update at a time (lock file).
- No OBS contact.

## Lite
Same card inside Lite for its own pieces and the modules it hosts. Lite already has the release/tag check (c2dada3 + `Docs/LITE_APP.md` manifest); we extend that to read the same component map and reuse `Suite/updater/lib` rather than a second implementation. Needs 012 to confirm how Lite stores its installed version.

## What I can build first (small, safe, no restart needed)
1. Core: `GET /api/update/check` (read-only; github source, component diff, live flag) + tests.
2. Settings > Updates card: check button, daily quiet check badge, per-component list, release notes.
3. Per-module Update button for Listen (my module) using Update-Module.ps1 + backup + rollback; the others follow the same path.
4. Shell/core/Host staged update + restart-swap, and Lite hookup, after a go from 00/012.

Open: the release builder must emit the `components` map (Build-Release.mjs change, mine), and Ivan's one-time sealed-key step is still needed for the private-repo read.

## Built (this commit)
- Release manifest carries `components` (per-part sha256, from `Build-Release.mjs`); `Suite/updater/lib/components.mjs` defines the parts: shell, core, host, listen, multi, link, spotify, voice, tools (scripts/docs). Site assets are not shipped in the release, so there is no site part.
- Updater CLI: `check` (per-part diff + live flag), `apply --only a,b [--stage]`, `rollback [--plan]`, `launch` (swaps staged app parts or a staged rollback while nothing is running; full auto-update now only when `auto_update: true` in install.json).
- Core: `GET /api/update/check`, `POST /api/update/apply {parts}`, `GET /api/update/job`, `POST /api/update/rollback` (`suite/updates.py`): module parts = stop that module, swap its files, start it again; shell/core/Host = verified and staged, applied at the next start. Refused while live (core live state, plus the updater's Host check).
- Shell: Settings > Updates card (check, per-part Update, Update all, roll back last update), quiet check once a day.
- A development tree (no `install.json`) never updates itself.
- Not wired yet: `updater.mjs launch` is still not called by the launcher (00 adds the line to PinguinoApp.bat / the exe). Until then staged app parts wait for it. Lite: not done, needs 012.

## Install profiles (minimal PinguinoLite PC)
`install.json` gains `profile` and `parts`. `full` (this PC) has no `parts` and keeps everything. `lite-minimal` keeps `["lite","link","tools"]`: Lite's exe + Start-Lite.bat, Link, and the updater/scripts/docs. Defined in `Suite/updater/lib/profiles.mjs`.

- Install: `node Installer/install.mjs --target <dir> --profile lite-minimal --github|--url|--local ...` (not with `--repo`; the release must carry per-part info, i.e. built by the current `Build-Release`). Records the per-part hashes of what it laid down.
- A part the profile does not keep is never updated, never listed as a change and never blocks "current". `updater.mjs check` lists them under `optional: [{id,name,module,files,bytes}]`; `status` shows `profile` and `parts`.
- **Install on demand:** `updater.mjs apply --only spotify [--core-port N]` (naming a part adds it to `parts` and downloads it; sha256, backup and the live guard apply as for any update). Result: `ok`, `message`, install.json `parts` now includes it.
- **Eject:** `updater.mjs eject --part spotify`. Only module parts. The caller stops the module first. The files are MOVED to `Data/updates/ejected/<part>-<time>/files/...` (nothing deleted; a module's own `data/` folder and `Data\` stay), and the part leaves `parts`/`components`. Refused while live. Output `{ok, message, moved, kept_in}`.
- **Verify:** `updater.mjs verify [--only a,b]`. Read-only; compares each installed part with the release package: `{ok, version, parts:[{id, state: ok|damaged|missing|not-in-release, missing[], changed[], *_count}], all_ok}`. Parts not installed are skipped.
- **Repair:** `updater.mjs apply --only <part> --repair` rewrites the part's files from the release even though its hash matches (use after verify says damaged/missing).
- Rollback works for an on-demand install too (it removes the files the install created and restores `parts`).
