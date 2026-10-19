# Rename note: "BVQ" -> "Pinguino"

Decided 2026-10-19 (user). Status: **in progress** (Phase C). Non-C# files done; C# bot files wait for Unit 02.

| Old | New |
|---|---|
| `BVQ_DATA_DIR` (env var) | `PINGUINO_DATA_DIR` (old name honored as deprecated alias for one release) |
| `%AppData%\BVQ` | `D:\PinguinoSuite\Data` (legacy dir kept read-only until tested) |
| `[BVQ]` log prefix | `[Pinguino]` |
| `BvqSettings` and similar identifiers | `PinguinoSettings` |
| Streamer.bot action "BVQ Engine" | "Pinguino Engine" (old name still recognized until re-import) |

Baseline before rename: 446 hits in 69 files. Each applied change will be logged below (file, count).

## Applied changes

- 2026-10-19 Pipeline (`Pipeline/*.mjs`, 9 files, 25 hits): hardcoded `%AppData%\BVQ` replaced by the new `Pipeline/lib-paths.mjs` `dataDir()`. Order: `PINGUINO_DATA_DIR` -> `BVQ_DATA_DIR` (deprecated alias) -> legacy `%AppData%\BVQ` while it exists (so the pipeline and the still-legacy live bots never split) -> `Data\runtime`. Comments now say "<data folder>".
- 2026-10-19 Data: legacy `%AppData%\BVQ` copied (not moved) into `Data\runtime` (no overwrites). Legacy dir untouched. Cutover = set `PINGUINO_DATA_DIR=D:\PinguinoSuite\Data\runtime` for Streamer.bot and the pipeline task (user decision, not done yet).
- Still named BVQ on purpose: the live Streamer.bot action "BVQ Engine" (until re-import); C# files (`PinguinoBotCore.cs`, `PinguinoChat.cs`, `PinguinoHelper.cs`, `Shared/PinguinoRouter.cs`, `Shared/PinguinoBots.cs.txt`) and `Tests/*/harness.cs` + `run-*.ps1` that set `BVQ_DATA_DIR` (Unit 02); `Docs/BVQ_MIGRATION.md`; historical mentions in Docs.
