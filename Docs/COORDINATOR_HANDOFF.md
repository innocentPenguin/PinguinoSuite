# Coordinator handoff (00 - Pinguino), written 2026-10-23 04:58

> Taken over 2026-10-23 05:05 by the new 00 session local_32405a3a-974d-494b-8007-01272497ad35 (Fable). Rebuild BUILD OK, app launched 05:01, Listen restarted, all ports up; engines told the new id.

Read this first, then the memory index (C:\Users\ivanm\.claude\projects\D--\memory\MEMORY.md), Docs\APP_LOG.md, Docs\IDEAS.md. Full old transcript: C:\Users\ivanm\.claude\projects\D--\7fc07e5a-9de1-4177-a16f-0a88b994dfed.jsonl (grep it, do not read it whole).

## Role and hard rules
- I am 00, the coordinator for PinguinoSuite (Tauri Suite app; frozen Python core 127.0.0.1:8760; C# Host 8770; modules: listen 8765, multi 8766, link 7777, spotify 8771, voice 8772; PinguinoLite; site repo D:\PinguinoSuite\PinguinoSite on Railway innocentpenguin.com).
- ONLY 00 builds/launches/restarts. Siblings queue requests. NEVER go live in OBS or test it. Never send duplicate chat messages. No Streamer.bot. Plain `git push` via CLI.
- Check `https://decapi.me/twitch/uptime/innocentpenguin_` before any restart/push (offline = ok).
- Module restart: `powershell -File D:\PinguinoSuite\App\Update-Module.ps1 <listen|multi|host|link|spotify|voice>`. Full rebuild: stop pinguino-suite, pinguino-core AND the Host (dotnet PinguinoHost.dll) first, then `App\Build-All.bat --no-launch` (about 5 min), then launch `D:\PinguinoSuite\PinguinoApp\PinguinoApp.bat`.
- Host write auth: header `Origin: http://127.0.0.1:8770` passes; else Bearer/X-Pinguino-Token.
- Pushes: Suite repo (D:\PinguinoSuite, main) pushed at 04:25 up to 2c1d20b; later local commits exist. Site repo pushed 04:46 (c755029..b500cae). Ivan's approval is needed for pushes; 05 insists only Ivan's typed message approves a site push (00 may push when Ivan told 00).
- Held until Ivan says: end-of-night 3x code audit + 4-tier docs; tell 01 to re-run Installer\Build-Installer.bat after a Suite push.
- Ivan's standing process: when engines finish, run checks, improve, re-check, ask engines what's next (combine questions), then give him the "list of things I need to address". Keep Docs\APP_LOG.md and Docs\IDEAS.md current.

## Sessions (SendMessage `to` = id)
- 01 app/shell/core/Listen/installer: local_c2eba491-9778-4a94-bb81-13f8df1de582
- 02 Host/bots/economy: local_58156ab8-4c1b-4654-a4a3-48687e71d813
- 012 Lite: local_8569ffff-cfee-4636-8b28-35053841e45c
- 013 Master View: local_28897ee2-ca1d-4747-a0fd-bb3c9f980179
- Music/Spotify: local_148f8072-9dba-4c73-b363-af5c8d38b595
- 05 site: local_a7f59c84-45c5-420c-b135-91a4240e19ef
- 03 Multi: local_d506ae20-c89f-4357-a5d4-139227f48aee
- 04 Link: local_4fb256ec-2533-4628-b151-298a4d678528
- 021 Helper: local_6f5d97c2-3914-477d-b04a-e7e5bec9c3af
- 022 Chatty: local_7135181f-2c8d-4cec-8cda-1c0d6edae3ff
- 023 overlays/scenes: local_30e19219-6bb0-4db8-ac65-ae0800f6ee15
- old forks: 00-pinguino-fork local_14510b64-ccc0-4f2f-98f3-bac8dbfd486d, songify-music local_17863c7d-081c-4684-9940-00d38e2078a2

## State right now (04:58)
- Rebuild of the app in progress (Build-All, third attempt after the Host lock). When it prints BUILD OK: launch PinguinoApp.bat, then `Update-Module.ps1 listen`. If BUILD FAILED, read C:\Users\ivanm\AppData\Local\Temp\buildall3.log.
- Restarted today after Ivan's go: Host (twice, last with 02's 8cc1987), Multi (last with 03's size options), Spotify module (channel playlist + YouTube links commits 33348b3, 2c1d20b). Stream was offline.
- Ivan's pending answers: !speak (name, price 100 pts, go-ahead, play into OBS?); per-symbol slot values (slots now 🍒 🐟 ⭐ ⚽ 🐧, 💎 omitted, ask if he wants it back); firsts apply ({"apply":true} on POST /api/firsts/rebuild, backs up first); Spotify site key (SPOTIFY_API_KEY on Railway + Key vault, Ivan pastes); TikTok @handle + OK to install TikTokLive; YouTube/Kick tokens; Seal-InstallKey.bat step; Twitch re-sign-in for new scopes; Discord setup.

## Ivan's decisions this segment (all routed)
- Firsts: 1st=5, 2nd/3rd=3, 4th/5th=1. Real-person-message sounds only (not bots/Ivan); returning and first-time chatter sounds; chat sound gap can be 0.
- PinguinoB0t = utility; Chatty = gambling/games/personality (does not argue, may defend itself). !games, !shop (Guess the Chatter, "Get a sub" item).
- Slots: real emoji. Player-to-player loans; Activity ledger (running balance, Won/Lost wording) replaces History; site "gifted" tag (white underlined, shows gifter) replaces "(paid)"; Prime shown as a crown icon only (05 drew a simple crown, exact logo SVG welcome); view others' points pages; Give section above Loans.
- Give limit: 10% of the giver's CURRENT balance per STREAM (resets every stream, counter not reduced if balance drops, can show 30000/3000). Settings giveDailyPct/min/max.
- Depreciation: marginal bands 100-250k 1%, 250-500k 2%, 500k-1M 4%, 1M+ 6%; DRY RUN stays ON; each person sees only their own projected loss on the site, band table hidden; tiers extensible.
- Strike check-in: temporary strikes drop 1/day if the player watched 15 min; settings only, no public mention.
- Bot replies use Twitch's native reply (reply_parent_message_id), no name text in body. Clips: featured clips from last 2 weeks, never repeat the last 3 sent (shared list across bots).
- Shoutouts: replace Teklynk tool: clip of the target (featured first, then most viewed), clip only, 10 s delay, mods only, 60 s cooldown, auto on raids of 3+, progress bar, all-time range; plays in the 800x600 alerts source.
- Alerts for EVERYTHING as editable types (03 added 15+); central queue with merge/priority/delay; watch-streak alert; viewer-submitted introductions (mod-approved, play on first/returning chat).
- Full-screen overlays: per-game layouts (horizontal 1920x1080 and vertical 1080x1920) via scene.html; alerts stay standalone; 023 owns it.
- Wheel: slower longer ease-out; team box clears to one pulsing ??? when spinning for the next player; box double width; vertical layout.
- Mod side: Mod view (/mod/view) with activity feed; mod audit log of every mod action (owner-only by default); mod music controls: no scrub, no like, "Add to stream playlist" button, channel playlist chosen in Suite; Mod commands card with All commands + Mod commands orange buttons; Supporters card gets a real Reconnect Twitch button.
- Spotify: YouTube links accepted only to read title/artist, then match on Spotify, else "song not found". Approval setting explained (needs "Approve requests first" ON; stream-safe forces approval). Songify blocklist was imported (91 track ids, shown as raw ids; offered to resolve names).
- Depreciation/give/loans backend by 02 (commit 8cc1987). Many later 02 items still queued.

## Queues per engine (as of now)
- 02 (queued, nothing built yet unless it reports): reply threading, clip rules (2 weeks featured, no repeat 3), shoutout clip pick + events to Multi (/api/alerts/fire), give limit per stream, strike check-in, wheel ease-out/team box/vertical, mod activity feed push (POST /api/bot/activity incl raid_out, hype, redemption), gifted-sub tags, "Get a sub" item, intro storage + GET /api/intro (Origin 127.0.0.1:8766 + Bearer), watch-streak event to Multi /api/alerts/fire, shoutout rules (!so, mods only, cooldown 60, raid auto >=3, delay 10), chat commands for loans later, TTS (!speak) after Ivan approves, !rank source (tracker.gg blocked by Cloudflare).
- 05: site pages for loans/activity/give done and pushed; intro submit form; Prime exact logo if given; mod pages; waits for 02 pushes; wording "this stream" committed locally (rides next batch).
- 03: all above restarted; intro playback built (needs 02 endpoint); w/h/scale query for /obs/alerts done; goal/hype bars, dashboard default, Twitch 4007 reconnect fix unapplied, audit rounds 2/3.
- 023: scenes phase 1 committed (4b7720a), phase 2 editor next; needs ?part= agreed with 02; per-game tagging requested.
- 01: Listen UI + Report a problem box + module reset fix (in the rebuild), Suite panel for scenes later.
- Music: restarted; first manual test of channel playlist add + YouTube link pending; blocklist name lookup offered to Ivan.
- 04 Link: restart Link to pick up commits; Lite start/stop not built.
- 013 Master View, 012 Lite, 021 Helper, 022 Chatty: idle/done on their halves.

## Verify after the Host restart (live checks, all with stream OFFLINE then Ivan)
!gamble !slots !duel/!accept !give !games !shop each give exactly one line (real emoji reels); first-time/returning chatter sounds in Multi; channel playlist + YouTube link in Spotify; scene.html?profile=h&preview=1; /api/economy/depreciation (dry run, tiers); site /points, /mod/view (403 when not signed in), loans.

## What to keep doing
Route every Ivan message to the owning session (cc dependents), restart only what changed, tell Ivan in short plain language what happened and what he must answer. He reads the closing message, not tool output.
