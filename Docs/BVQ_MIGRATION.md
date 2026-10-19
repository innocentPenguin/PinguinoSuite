# BVQ migration (with Unit 01) — runtime data from %AppData%\BVQ into the Suite

Status 2026-10-19: **not executed**. Backup exists in `Archive\backups\2026-10-19-m1-start\BVQ\` (contains secrets — keep local).

## What lives in %AppData%\BVQ today
chat_*.json, current_match, live_state, matches, mmr_cache, players, problems, queue, settings. No `bots.json` / `bots_secrets.json` yet.

## Dependencies the C# has on that folder
- All bots resolve the data folder via env var `BVQ_DATA_DIR`; default is `%AppData%\BVQ`. **No code change needed** to relocate.
- `settings.json`: `OverlayDir` (still `D:\PinguinoBot\overlays`), `ObsSources` (16 duplicate rows), secrets `TrnApiKey`, `WebSyncKey`.
- `chat_settings.json`: `CommandsFile`/`UpdatesFile`/`OpinionsFile` (still `D:\PinguinoBot\...`), secret `ApiKey`, `RolesUrl`.
- OBS overlays read `live_state.js` from `OverlayDir`.

## Steps (do with Streamer.bot CLOSED)
1. Fresh backup (one already exists from today).
2. Copy `%AppData%\BVQ\*` to `D:\PinguinoSuite\Data\runtime\` (keep secrets files there, outside any publish/zip).
3. Set user env var `BVQ_DATA_DIR=D:\PinguinoSuite\Data\runtime`; restart Streamer.bot (env is read at process start).
4. Edit `settings.json`: `OverlayDir=D:\PinguinoSuite\PinguinoB0t\overlays`; dedupe `ObsSources`.
5. Edit `chat_settings.json`: repoint the three file paths into `D:\PinguinoSuite\PinguinoChat\` (copy the files from `D:\PinguinoBot` first).
6. Repoint OBS browser sources (local file) to the Suite overlay paths.
7. Leave `%AppData%\BVQ` untouched for one week as the rollback copy (rollback = remove the env var).

## Unit coordination
- Unit 01: confirm they do not also write to `%AppData%\BVQ`; agree on the single runtime folder above.
- Unit 03 (PinguinoMulti): shares `intro_queue.json` once built (see ROUTING/AUDIT).
- Unit 05 (PinguinoSite): reads `live_state` / wheel session via the Core web sync, never the folder directly.

## Folders outside the Suite still to consolidate
`D:\PinguinoBot`, `D:\PinguinoBackup`, `D:\InnocentPenguinSite`, `D:\InnocentPenguin-source.zip`, `D:\.remember`. Diff each against `PinguinoSite`/`PinguinoB0t` first, then move into `Archive\legacy\`. Nothing has been moved yet.
