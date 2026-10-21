# Replay stats plan (Lite) — who won, per-player stats, for the site

Status: PLAN + step 1 (scanner/parser in Lite), 2026-10-21, session 012. Owners: Lite scanner/parser = 012; Host endpoint = 02; site display = 05; hand-over/coordination = 00.

## Goal
Lite (running on the streamer's gaming PC) finds new Rocket League `.replay` files, decodes them **locally**, and writes one small JSON per match: teams, players, score, winner, per-player goals/assists/saves/shots/score. The Host/site read those JSONs. Winner detection can also settle queue matches (`Data\runtime\matches.json` has `Winner: null` until someone reports it).

## Findings (checked on this PC, 2026-10-21)
- Replay folders: `Documents\My Games\Rocket League\TAGame\Demos` (Steam) and `...\DemosEpic` (Epic). **Neither exists on this PC yet**; only `Cache, Config, Logs, SaveDataEpic` do. Rocket League only writes a file there when a replay is saved (manually from the match history/post-match screen). Nothing can be parsed until Ivan saves a replay. Lite watches both folders and any extra folder listed in `%APPDATA%\gg.pinguino.lite\replay_dirs.txt` (one path per line).
- The Suite already has `players.json`: Twitch name -> `Platform` + `GameId` (in-game name). That is the link from a replay player to a Twitch viewer.
- Matches with Blue/Orange rosters and `Winner` live in `Data\runtime\matches.json`.
- No parser in the repo. ballchasing.com is a hosted replay database (needs an API token and uploads the raw replay): rejected, see below.

## Parser choice: `boxcars` (Rust crate, embedded in Lite) — local, offline, no key
- boxcars is the library behind rrrocket, MIT, pure Rust. We link it into Lite, so there is **no external exe, no token, no upload**.
- Header-only parse (`never_parse_network_data`): the replay header already holds everything we need: `Team0Score`, `Team1Score`, `TeamSize`, `PlayerStats[]` (Name, Platform, OnlineID, Team, Score, Goals, Assists, Saves, Shots, bBot), `Goals[]` (PlayerName, PlayerTeam, frame), `Id` (match GUID), `Date`, `MapName`, `MatchType`, `TotalSecondsPlayed`. Fast (ms per file), tolerant of new game versions (no network data to break).
- **Not in a replay: MMR / rank.** The replay has no ratings. MMR keeps coming from the Suite's own rank sources; Lite does not invent it. (Per-player MMR stays absent from the result JSON.)
- Rejected: ballchasing API (uploads raw replays, needs a key, rate limits, no MMR anyway); shelling out to rrrocket (extra binary to ship and trust).

## Data shape (one file per match)
Path: `<lite dir>\replays\results\<match-guid>.json` (written atomically: tmp + rename). `<lite dir>` = `D:\PinguinoSuite\Data\lite` (see LITE_APP.md).
```json
{
  "schema": 1,
  "match_id": "A1B2C3D4...",           // replay header Id (GUID); falls back to sha1 of the file
  "played_at": "2026-10-21T15:04:05",   // header Date, local time of the PC, no zone
  "status": "complete|incomplete",      // incomplete = no score info (left early / unfinished)
  "team_size": 3,
  "map": "Stadium_P",
  "duration_s": 312,
  "blue":   { "score": 4, "players": [ {"name":"we1rdshark2.0","platform":"epic","twitch":"yoohoo15","score":512,"goals":2,"assists":1,"saves":3,"shots":5,"bot":false} ] },
  "orange": { "score": 2, "players": [ ... ] },
  "winner": "blue|orange|draw|null",
  "goals": [ {"team":"blue","player":"we1rdshark2.0","t_s":41.2} ],   // t_s only when the header gives frame + fps
  "mvp": "we1rdshark2.0",               // highest in-game Score (ties: null)
  "source": "lite-replay-v1"
}
```
- `twitch` is filled from `players.json` (GameId + Platform match, case-insensitive) when readable, else null. Unknown names stay as in-game names.
- `blue` = team 0, `orange` = team 1 (Rocket League convention). Missing score fields mean 0 (RL omits zero scores).
- An index `<lite dir>\replays\index.json` (`schema`, `updated_at`, `scan_dirs`, `items[]` = match_id, played_at, score, winner, file) is what the Lite Replays page and Host read for lists. State for dedupe: `<lite dir>\replays\state.json` (path -> size+mtime -> match_id | error).

## Privacy
- Only files in the streamer's own replay folders (+ explicit extra dirs). No recursion elsewhere.
- **Raw replays never leave the PC**: Lite never uploads or copies them. Only the small result JSON is produced.
- The result JSON has **no file paths, no OnlineID/Steam/Epic account ids, no PC names**. Public-facing fields are in-game name, platform label, optional Twitch name. If a name should be hidden on the site, the site (05) filters it using the Suite's opt-out list; the data does not carry it.
- Nothing is sent anywhere by Lite in step 1. Sending raw replays anywhere (e.g. to another PC) happens only if Ivan says so.

## Delivery to Host / site (proposal; 02 and 05 confirm)
1. **File contract (default, no token, no ports):** Host reads `Data\lite\replays\index.json` and `results\*.json`. Same pattern as the rest of the Lite contract.
2. **Host (02):** expose `GET /api/replays` (index) and `GET /api/replays/{id}`, public-safe subset as above, and optionally set `Winner` on the matching queue match in `matches.json` when the roster Twitch names match (all `twitch` fields resolved, scores decisive). The auto-set should be proposal-only until Ivan approves it.
3. **Site (05):** match history page + per-player lines (goals/assists/saves/shots, win rate) built from the Host endpoint; Penguino look; in-game names only unless `twitch` is public.
4. If Lite runs on a different PC from the Suite, the folder `Data\lite\replays\results` is what has to reach the Suite machine (sync/copy of small JSONs, or an authenticated POST to a Host endpoint 02 defines). Not built now.

## What step 1 delivers (this session)
- `src-tauri/src/replays.rs`: scanner thread (stat-only tick every 3 s only while RocketLeague.exe runs AND a gated Suite activity is active (Host GET /api/customs/state: casual, competitive or koth, non-sim, queue open or match live; ranked reserved, off), plus 2 min grace; otherwise 30 s; unreadable state = slow; file must be unchanged across two ticks before parsing; + "Scan now"), dedupe state, boxcars header parse, pure `extract()` (unit-tested), atomic result + index writers.
- Lite **Replays** page: folders being watched (and whether they exist), the last matches (score, winner, players), "Scan now", honest empty state ("no replay saved yet: in Rocket League, save a replay from the match history").
- Out of scope now: network-frame data (ball/boost/possession), uploads, site pages, Host endpoint, MMR.

## Risks / open questions
- Not tested against a real replay yet (none on this PC). `extract()` is tested with a JSON shaped like rrrocket output; the first real file may need field-name tweaks.
- Replays are only produced when saved in-game; there is no auto-save. Ivan may want to enable/automate saving (a BakkesMod plugin could do it, but that is a third-party mod: decision for Ivan, not assumed).
- Queue matches have in-game names that may differ from `players.json GameId` (renames): unmatched names stay unmatched.
