# Drive cleanup, Runner 2 (step 1: survey, read-only)

Scope: inside `D:\PinguinoSuite`, excluding `Data\`, `.git`, `node_modules`, `App\src-tauri\target`. Survey time 2026-10-20 ~22:35 CDT. Nothing was removed or moved when this was written.
Method: SHA256 of every file over 20 KB (2,890 files); a full SHA256 of the VOD files. Cutoff for "recent" is 20:26 (2 hours).

## Summary

| # | Item | Size | Verdict |
|---|---|---|---|
| 1 | 24 identical VOD mp4s in `Suite\modules\listen\data\sources` | 21.0 GB (20.1 GB removable) | **Remove 20 of 24, keep 1, skip 3 recent. Needs a go-ahead (the delete was blocked by the permission classifier).** |
| 2 | `App\src-tauri\target` | 2.26 GB | Regenerable. **Ask 00** (rebuild may run). |
| 3 | Site forks `PinguinoSite-cmd`, `PinguinoSite-v`, `wt-mobile` | ~26 MB each | Not stale-looking. **00/05 to decide.** |
| 4 | `Deploy\` legacy Streamer.bot paste files | 0.5 MB | Archive (move). Not in the Streamer.bot archive, so move, don't delete. |
| 5 | Test `bin\`+`obj\` copies | ~8 MB | Regenerable, low value. Leave unless wanted. |
| 6 | Empty dirs `wt-verify`, `wt05b` | 0 | Remove (empty). |
| 7 | `.bak` files | ~1.5 MB | Keep, except as noted below. |

Everything else duplicated is tiny: only 16 MB of redundant file bytes across the whole tree, and 14 MB of that is the site forks and test build outputs.

## 1. Listen module VOD downloads (the big one)

- Path: `Suite\modules\listen\data\sources\vod-*.mp4`
- 24 files of exactly 876,626,811 bytes, **all with the same SHA256** `9ce1053dafda...38de` (full-file hash, not a prefilter). One new copy appears about every 30 minutes (09:44 through 21:36 today).
- Not referenced: none of the 24 ids exist in `ears.db` `sessions`. The real VOD sessions have different ids (`vod-b40bde2d` is the one converting now) and their finished audio lives in `data\audio\*.ogg`.
- Other files there: `vod-5254f0b6.mp4` (384 MB, 09:23, not in db, different content, not touched), `vod-b40bde2d.mp4` plus `.part-FragN.part` (the live download, hands off).
- Likely cause (for the listen owner, not for me): something retries a VOD download on a timer, each retry gets a new random id and the same truncated or capped result. It will keep filling the disk (about 1.75 GB per hour) until fixed. D: has 291 GB free, so it is not urgent but it is a runaway.
- Referenced by: `ingest.py` looks up `cfg.SOURCES.glob(sid + ".*")` only for ids in the DB, so the orphans are never read.
- Plan if approved: keep `vod-12833b25.mp4` (oldest) as the single sample, delete the other byte-identical ones that are older than 2.5 h and not in the DB (20 files, about 17.5 GB), re-verifying the hash before each delete. Skip `vod-12528281`, `vod-22ffc2f2`, `vod-3e1b0d65` (inside the 2 h window; they can go next pass). Script is ready at the scratchpad (`vodrm.py`).
- Clean rebuild path: re-ingest by URL from `ears.db`, nothing needs these files.

## 2. `App\src-tauri\target`

2.26 GB, gitignored, regenerable with `cargo build`/`tauri build`. Not touched. Needs 00 to say no rebuild is running or queued.

## 3. Site copies

Canonical: `D:\PinguinoSuite\PinguinoSite` (own git repo, Railway deploy).

| Dir | Own .git | Diff vs canonical (files differing) | Recently modified | Git status in suite repo |
|---|---|---|---|---|
| `PinguinoSite-cmd` | yes | 44 | no | untracked |
| `PinguinoSite-v` | yes | 42 | no | untracked |
| `wt-mobile` | yes | 27 | **yes (after 20:26)** | untracked |

These are git worktrees or clones used for 05's forks, with diverging work. Each also has its own `.git`, so the commits would be lost if deleted. About 8.9 MB of the duplicated content is identical page and asset files across all four, but removing only those would break each tree. Verdict: do not remove. If 05 confirms the forks are merged, archive each whole directory.

## 4. `Deploy\`

`PinguinoBot.cs`, `PinguinoChat.cs`, `PinguinoHelper.cs`, `PinguinoRouter.cs`, `PASTE-CHECKLIST.md` (all from 2026-10-19, untracked in git). These are the Streamer.bot paste files. They are not duplicated in `Archive\streamerbot-2026-10-19` (that holds docs, config, backups, raw data). Referenced only by docs (`Docs\AUDIT.md`, `HOST.md`, `RENAME_NOTE.md`) and by `Tools\build-index.py` (indexer path filter; a missing folder is harmless). No csproj, bat or test uses them. Verdict: MOVE to `Archive\drive-cleanup-2026-10-21\Deploy\`.

## 5. Test build outputs

`Tests\*\bin`, `obj`, `build` hold about 8 MB: six copies of `Newtonsoft.Json.dll` (3.4 MB redundant) plus bin/obj pairs of the same exe and pdb. All gitignored and regenerable by `Tests\*\run-*-tests.ps1`. Low value, and the test runs I need later would just recreate them. Leaving them.

## 6. Empty directories

`wt-verify`, `wt05b`: empty. Safe to remove.

## 7. Backup-style files

| File | Verdict |
|---|---|
| `Suite\modules.json.bak-prehost` | keep (pre-Host rollback point, tiny) |
| `s05data\support.json.bak` (1.2 MB) | keep until 05 confirms; `s05data` looks like a stray data dir for 05 |
| `PinguinoSite\data\*.json.bak` (5 files) | keep, inside the site repo |
| `Suite\suite_settings.json.bak` | modified 21:48, skip |
| `Archive\PinguinoB0t-versions\harness.cs.empty-stray` | 0 bytes, remove |
| `Archive\PinguinoB0t-versions\PinguinoBotCore.before-*.cs` (8) | archives, keep |

## Not touched

`Data\`, `.git`, secrets, anything git-dirty (`Docs\clipmap\merge.cjs`, `PinguinoApp\PinguinoApp.bat`, `PinguinoB0t\CHANGES.md`, `PinguinoB0t\commands.json`, `PinguinoB0t\overlays\live_state.js`), `Suite\.venv` (three duplicate pip exes, 0.4 MB, not worth it).
