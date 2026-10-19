# Decisions

- 2026-10-19 Replacement name for BVQ: **Pinguino**.
- 2026-10-19 Migration: phased, env var first; legacy dir kept until tested.
- 2026-10-19 Secrets: plain files in `Data/secrets`, gitignored (provider interface kept so DPAPI/keyring can be added later).
- 2026-10-19 Platform: improved Python core now, Tauri shell later.
- 2026-10-19 Platform (supersedes earlier line): **Tauri v2 shell now**, hosting the existing Python core as a headless sidecar; core API is token+Origin protected; modules register via `module.json` (see MODULE_CONTRACT.md). Rust core rewrite is optional/later.
