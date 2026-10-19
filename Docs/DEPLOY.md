# Deploying the four bots into the real Streamer.bot

Streamer.bot: `C:\Users\ivanm\Documents\PinguinoB0t\`. Each action compiles on its own, so the code is **pasted** into an *Execute C# Code* sub-action (a file on disk is not enough). Do NOT edit `data\actions.json` while Streamer.bot runs.

## Before anything
1. `node Shared\sync-shared.mjs --check` → all "up to date".
2. `powershell -File Tools\check-deployed.ps1` → shows what is deployed vs repo (today: all four MISSING).
3. Backup exists: `Archive\backups\2026-10-19-m1-start\`. Do the BVQ migration (BVQ_MIGRATION.md) first.

## Per action
| Action name | Source file to paste | Trigger |
|---|---|---|
| PinguinoBot | PinguinoB0t\PinguinoBotCore.cs | the 22 `!` command triggers (moved from BVQ Engine) |
| PinguinoHelper | HelperPinguino\PinguinoHelper.cs | none (called by Router) |
| PinguinoChat | PinguinoChat\PinguinoChat.cs | none at first; later First Words (120) and subs (103/104/105) |
| PinguinoRouter | Shared\PinguinoRouter.cs | Twitch Chat Message (133) — enabled LAST |

1. Actions → Add Action, named exactly as above (`bots.json` references these names).
2. Add sub-action: *Core → C# → Execute C# Code*.
3. Open the source file as UTF-8, select all, paste into the sub-action editor. (Some comments show mojibake like `â•â•â•`; harmless, but if compile complains, strip non-ASCII from comments.)
4. Click **Compile**; the log must show no errors. Save.
5. Set the action's Queue to the existing `PinguinoBot` queue (blocking off).
6. Re-run `Tools\check-deployed.ps1`: `identicalTo` must show the right name for every action.

## Staged cutover (verify each stage before the next)
- **A. Side by side:** new actions have no triggers. Compile each.
- **B. Core:** move the command triggers from *BVQ Engine* to *PinguinoBot*; disable (do not delete) *BVQ Engine*. Test `!join !leave !queue !next !win` and the overlay.
- **C. Helper + Chat:** run each manually with test args.
- **D. Router last:** create `bots.json` in the data folder, enable trigger 133 on PinguinoRouter; disable legacy `chatbot`, `chat`, `First`, `First TIme System (Bell)`, `chat (first time today) T2` (+Copy) and the command **`ChatGPT Call`** (regex `@?PinguinoB0t`) so nothing double-answers.
- **Rollback:** re-enable the legacy actions above and disable the four new ones; or, with Streamer.bot closed, restore `actions.json` from the backup.
