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
