# Task: Tauri shell + integration-ready core

Goal (user /goal): cross-platform PinguinoSuite app on Tauri, ready for other apps to integrate.

## Done
- `App/` Tauri v2 project: window, tray (close-to-tray), single-instance, autostart plugin (capability-gated), sidecar supervision of the Python core (`--headless`, random per-launch token, graceful `/api/quit` on exit), `core_config` IPC for the UI.
- UI = copy of the existing dashboard (`App/src/index.html`) + `bootstrap.js` that routes `/api` and `/ws` to the core with the token. The core serves this same file in standalone mode (single copy, no drift).
- Core (`Suite/suite/suite.py`): token auth + Host/Origin checks + CORS for Tauri origins, `/api/capabilities`, cross-platform process stop (killpg vs taskkill), non-Windows safe autostart, drop-in `module.json` discovery, `PINGUINO_PORT`.
- Verified: unauthenticated 401, bad Origin 403, authenticated state/capabilities OK, quit OK (port 8791 smoke test).

## Not done / blocked
- Rust toolchain + MSVC Build Tools are not installed, so the Rust shell has **not been compiled**. Needs user OK to install (rustup, VS Build Tools), then `cd App && npm install && npm run tauri dev`.
- Icons are a minimal generated set; run `npx tauri icon` for the full set (icns) before cross-OS bundling.
- Listen (:8765) and Link remain unauthenticated; per-module tokens planned.
- macOS/Linux untested; Python must be installed (bundling the core as a sidecar binary is a later step).

## Rollback
`App/` is new; delete it. Core changes are in git history (`git checkout -- Suite/suite/suite.py`).

## Update: toolchain installed and verified (2026-10-19)
- Installed via winget: Rustlang.Rustup (Rust 1.99.1 stable) and Microsoft.VisualStudio.2022.BuildTools (C++ workload).
- `cargo check` and `npx tauri build --no-bundle` succeed; exe at `App/src-tauri/target/release/pinguino-suite.exe`.
- Ran with `PINGUINO_PORT=8792`: window opens, dashboard renders with live module state (Listen running), unauthenticated API 401, bad Origin 403, core sidecar spawned.
- Shell honors `PINGUINO_PORT`. Installer bundling (NSIS/MSI) and macOS/Linux builds not yet tried. An older unpatched Suite on :8760 makes the shell talk to the wrong core; stop the old Suite first.

## Update: module auth + installer + CI (2026-10-19)
- Core passes `PINGUINO_API_TOKEN` into every module's env and sends `Authorization: Bearer` on `on_live`/`on_offline` hooks.
- Listen (:8765) now has a Host/Origin guard (core, Tauri and own origins; extra via `PINGUINO_EXTRA_ORIGINS`), non-browser (no Origin) writes need the token, `/ws` checks Host/Origin. Verified: evil Origin 403, bad Host 403, no token 401. Dashboard (allowed Origin) still works.
- Link is registered (`Suite/modules/link/module.json`, Unit 04); its own security model lives in `Docs/PinguinoLink/03-SECURITY-MODEL.md`. Link must adopt `PINGUINO_API_TOKEN`; tracked for Unit 04.
- Full icon set generated (`npx tauri icon`); `npx tauri build --bundles nsis` produced `PinguinoSuite_0.1.0_x64-setup.exe` (2 MB).
- `.github/workflows/app.yml`: Windows/macOS/Linux build matrix. **macOS/Linux builds are unverified until it runs on GitHub** (the root folder is not yet a pushed repo).


## Update: autostart switched (2026-10-19, user-approved)
- HKCU Run `PinguinoSuite` changed from `pythonw ...\suite.py --background` to `...\App\src-tauri\target\release\pinguino-suite.exe --background` (stays in tray). Rollback: set the old value back. No Pinguino Startup shortcuts existed; the `PinguinoBot Log Update` scheduled task is the pipeline and was left alone.
- Caveat: points at the build output; rebuild replaces it. Install the NSIS setup later for a stable path.

## Update: Link adopts core token (2026-10-19)
- Unit 04's Link already accepts `PINGUINO_API_TOKEN` (`x-link-token`). Core hook calls now send `Authorization`, `X-Pinguino-Token` and `x-link-token`. Verified against a running Link: no token 401, core token 200, foreign Host 421.
- Remaining honest gaps: macOS/Linux never built (no remote repo/WSL/Docker here; CI workflow ready, needs the repo pushed to GitHub); per-module tokens (all modules share the core token); Python core not bundled.

## Update: per-module tokens (2026-10-19)
- Each module gets `PINGUINO_API_TOKEN` = HMAC(core token, "module:<id>") (`module_token()` in suite.py). Modules never see the core token; core hooks use the module's token. Verified on Listen: master token 401, module token passes the guard (404 on a nonexistent route).
- Open: macOS/Linux builds (need GitHub push + CI run), bundling the Python core for standalone installs.
