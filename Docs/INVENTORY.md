# Verified inventory — real Streamer.bot vs PinguinoSuite (2026-10-19)

Source of truth: `C:\Users\ivanm\Documents\PinguinoB0t\data\actions.json` (44 actions), checked with `Tools\check-deployed.ps1` (read-only).
Backup taken first: `Archive\backups\2026-10-19-m1-start\` (contains secrets — keep local, never publish).

| Repo source | Intended action | In Streamer.bot now? |
|---|---|---|
| PinguinoB0t\PinguinoBotCore.cs (sha ea4ae3515867) | `PinguinoBot` | **No.** Old copy runs as **BVQ Engine** (22 command triggers `!join !leave !queue !pos !kick !next !reroll !balance !register !mmr !win !lobby !format !setmmr ...`), code differs. |
| PinguinoChat\PinguinoChat.cs (8b6a11d5a3b7) | `PinguinoChat` | **No.** Old copy runs as **chatbot** (Twitch chat trigger 133). |
| HelperPinguino\PinguinoHelper.cs (66304994afea) | `PinguinoHelper` | **No.** |
| Shared\PinguinoRouter.cs (9aad6f13082e) | `PinguinoRouter` | **No.** |
| PinguinoB0t\PinguinoBotFirsts.cs | First / firsts | Old copy in **First** (3 triggers). |

Other relevant live actions: `chat`, `First TIme System (Bell)`, `chat (first time today) T2` (+Copy) on First Words (trigger 120), subs `Normal/Resub/Super/Prime/Gifted` (103/104/105), `Followed`, `Cheers`, `Raided`(off), ChatGPT* group (disabled), `ChatGPT Call` command regex `@?PinguinoB0t` (still enabled — would double-answer after cutover). Queues: Ads, latest, Twitch API, Twitch Clip, First Time, PinguinoBot, shoutout.

`%AppData%\BVQ`: no `bots.json` / `bots_secrets.json` → router never ran live. `settings.json` OverlayDir and `chat_settings.json` Commands/Updates/Opinions files still point at `D:\PinguinoBot\...`; `ObsSources` contains 16 duplicate rows.

Shared-code sync (`Shared\sync-shared.mjs --check`): all four copies up to date.
