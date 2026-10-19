# Rename note: "BVQ" -> "Pinguino"

Decided 2026-10-19 (user). Status: **not yet applied** — Phase C of the migration plan.

| Old | New |
|---|---|
| `BVQ_DATA_DIR` (env var) | `PINGUINO_DATA_DIR` (old name honored as deprecated alias for one release) |
| `%AppData%\BVQ` | `D:\PinguinoSuite\Data` (legacy dir kept read-only until tested) |
| `[BVQ]` log prefix | `[Pinguino]` |
| `BvqSettings` and similar identifiers | `PinguinoSettings` |
| Streamer.bot action "BVQ Engine" | "Pinguino Engine" (old name still recognized until re-import) |

Baseline before rename: 446 hits in 69 files. Each applied change will be logged below (file, count).

## Applied changes
_None yet._
