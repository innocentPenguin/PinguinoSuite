# Project State (2026-10-19)

- Git initialised at root (baseline commit). PinguinoSite remains its own repo (ignored here).
- Legacy data snapshot: `Data/backups/pre-migration-20261019-065904` (+ sha256 manifest). Legacy `%AppData%\BVQ` untouched.
- `Data/{config,state,logs,secrets}` created (empty). Nothing migrated yet; bots still read `%AppData%\BVQ`.
- Secrets decision: plain gitignored files (risk R1).
- Open: assignment item 10 ("Add…") was truncated; awaiting user.
- Tauri app scaffolded in `App/` (uncompiled: no Rust/MSVC yet). Core hardened with token/Origin auth. See tasks/2026-10-19-tauri-shell.md.
