# Decisions

- 2026-10-19 Replacement name for BVQ: **Pinguino**.
- 2026-10-19 Migration: phased, env var first; legacy dir kept until tested.
- 2026-10-19 Secrets: plain files in `Data/secrets`, gitignored (provider interface kept so DPAPI/keyring can be added later).
- 2026-10-19 Platform: improved Python core now, Tauri shell later.
