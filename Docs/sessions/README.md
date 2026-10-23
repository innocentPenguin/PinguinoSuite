# Session notes index

One file per engine session, same six sections each (built, decisions, next session, plans, history, "things Ivan may be forgetting"). Kept current by each session; this index and the combined list by 00.

| File | Session | Owns |
|---|---|---|
| [00-coordinator.md](00-coordinator.md) | 00 Pinguino | builds, launches, restarts, routing, APP_LOG, IDEAS |
| [01-core-listen.md](01-core-listen.md) | 01 PinguinoSuite | Tauri shell, frozen core, Listen, installer/releases |
| [012-pinguinolite.md](012-pinguinolite.md) | 012 Lite | PinguinoLite app (second PC) |
| [013-master-view.md](013-master-view.md) | 013 Master View | Master View page in the Suite |
| [02-host.md](02-host.md) | 02 PenguinHost | C# Host, bots, economy (file pending from 02) |
| [021-helper.md](021-helper.md) | 021 Helper | PinguinoHelper bot |
| [022-chatty.md](022-chatty.md) | 022 Chatty | ChattyPinguino bot, games, canned commands |
| [023-overlays.md](023-overlays.md) | 023 Overlays | scenes, overlays, scene editor, Firsts |
| [03-PinguinoMulti.md](03-PinguinoMulti.md) | 03 Multi | chat, alerts, OBS sources |
| [04-pinguinolink.md](04-pinguinolink.md) | 04 Link | OBS/Stream Deck, device mesh, Lite install |
| [05-PinguinoSite.md](05-PinguinoSite.md) | 05 Site | innocentpenguin.com (Railway) |
| [music-spotify.md](music-spotify.md) | Music | Spotify module, song requests |

## Combined: things Ivan may be forgetting (2026-10-23 05:10)

Keys and sign-ins (only Ivan can do these)
- `SPOTIFY_API_KEY` into the key vault and Railway (site bridge cannot authenticate). (Music, 05)
- `OBS_WS_PASSWORD` into the key vault; real OBS control from Link is untested without it. (04)
- Twitch: re-sign-in for the new scopes, and "Reconnect Twitch" on the site /mod page so subs/bits sync. (02, 05)
- YouTube token with the youtube scope (Multi settings); Kick app + `channel:write` (Kick stays read-only until then); TikTok @handle + OK to install TikTokLive. (03, 013)
- Discord: Server Members intent + Manage Roles for booster sync and roles. (05)
- One-time release signing: create the Ed25519 pair, `Installer\Seal-InstallKey.bat`, public key in install.json. Until then releases are unsigned/dry-run; the Lite update check always says "No release published yet". (01, 012)

Decisions waiting
- `!speak` TTS: name, price, go-ahead, play into OBS? (02)
- Slots per-symbol values; want 💎 back? (02/022)
- Firsts rebuild: apply for real? (02)
- Chatty `!raid` line wording OK? End-of-stream recap on (default off)? Per-command use counts in the editor? (022)
- Loan/give/returning-chatter alerts stay OFF by default? Teklynk custom templates wanted? (03)
- Song-request leaderboard: week/month counts or lifetime only? (Music, 05)
- Lobby password policy is "never": OK, or do customs need a bot path for passwords? Bedrock Connect: DNS or not before the console answer goes public. (021)
- Link: set this PC's role to hub and give real OBS scene/input names; Tailscale on for a two-PC test; restrict OBS port 4455 to localhost (held for the replay-buffer hotkey). (04)
- Merch pages were removed on purpose; confirm before bringing them back. Search Console/Bing not set up. (05)

Not yet seen live (built, tested with fakes only)
- Master View writes (team names/colours, Fortnite KOTH, title/tags push, recap post, raid prep). Simulator "Chat ON" and Recap "Post in chat" post to REAL chat. (013)
- Site fed by real Host data (loans, give limits, depreciation, activity push, gifted tags). (05, 02)
- 15 new alert types, shoutout clip, intros (need 02's GET /api/intro + rules). OBS browser source needs audio on. (03)
- Spotify channel playlist add, YouTube link requests, lyrics overlay; native "PinguinoSuite" player. (Music)
- Lite install/update on the other PC: needs a built release + install source; replays need Rocket League saving replays there. (012, 04)
- New Suite pages (Economy, Timers, Canned, Overlay), Listen card controls, Report-a-problem, module reset. (01)
- Helper Spanish + typo suggestions; first live game must show exactly one line per command (Chatty + Host fallback). (021, 022)

Housekeeping
- Nothing from today is pushed to GitHub except the site (d9f1ad6 live). Suite push waits for Ivan's word; then 01 re-runs Build-Installer.
- `Data\feedback` (Report-a-problem screenshots) and `Data\helper\review.jsonl` hold screen/chat text: keep out of pushes and zips.
- Helper AI budget `MaxAiCallsPerHour` = 40; a busy night falls back to the English pack.
- Old site worktrees still on disk (05's file lists them); ~100 MB Lite scratch data in 012's scratchpad can be deleted.
- Held until Ivan says "done": end-of-night 3x code audit + 4-tier docs.
