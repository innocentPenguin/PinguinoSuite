# Ivan's to-do list (compiled 2026-10-21 08:15)

Everything the sessions need from you, with how to do each. Nothing is blocking tonight. Order: quick wins first.

## A. Quick clicks (a few minutes each)

1. **Release the site batch.** Open 05's chat (session "05 - PinguinoSite") and type: `push the rest`.
   - Releases fc491f2, cab2c51, 1cc0ac6, ff8e1c9 (simulator names endpoint, SEO round 2, members avatars).
   - Do it when you are NOT streaming (each push redeploys innocentpenguin.com, about 20 min).
   - 052's two commits (27a10e2, b43792a) and 051's branch e-mobile (b7f5fa6) are waiting for 05 to merge; 00 will ask 05 to confirm the exact list first.
2. **Sign the streamer account in again** (adds the moderator:read:chatters permission so points go to the real chatter list).
   - Open http://127.0.0.1:8770/setup in a browser.
   - On the Streamer card press Sign in, then approve Twitch's consent page (it lists the new permission).
3. **Reconnect Spotify + test the built-in player.**
   - Open the Spotify module in the Suite app and press Connect once (new streaming permission). Spotify app settings need the redirect http://127.0.0.1:8771/callback and your Client ID entered in the module.
   - Then keep http://127.0.0.1:8771/player open (a window is fine) and play something with a Premium account. Tell Music what happens.
4. **Look at the new screens in the Suite app** (rebuilt 02:05). Tell the owning session what looks wrong:
   - Commands page: role chips, "+ add", bulk bar (01).
   - Master View in the sidebar and its pop-out (013). Try one scene click so the token write is tested.
   - Settings > Pop-out windows > Open website: check icon, own taskbar button, login persists, Sign out (055).
   - Simulator panel on Wheel & Games (01/02).

## B. Decisions (answer in chat to 00 and I route them)

| # | Question | My lean |
|---|---|---|
| 1 | Should a message that is only "PINGUINO" count as calling the bot? | your call |
| 2 | Duplicate-account merges (mirihater/miri__0_0, iq_zens/iqzens, ...)? | yes/no per pair |
| 3 | Keep the 7 held edgy jokes (gay, grindr, goon, weiner, feetfinder, onlyfans, trapaccount) off? | keep off |
| 4 | Welcome bonus for new chatters: yes/no, how much? | decide |
| 5 | Marsh as head mod, and tell him he is counted (he opted out of public log sites)? | decide |
| 6 | Raid wording: you say or type the name, then confirm? | as described |
| 7 | Twitch refund permission for song requests: yes/no | decide |
| 8 | Index the member directory in search? | no, keep noindex |
| 9 | Saturday/Sunday stream times (Helper and the site wait for these) | give times |
| 10 | Lite update source: GitHub repo (owner/name) + read-only token, or local-only for now? | local-only until you pick |
| 11 | OK for the first PinguinoLite dev launch and push (012)? | ok when you are around |
| 12 | May OBS port 4455 be restricted to this PC only? | yes |

## C. Credentials and setup (you type them, nobody else)

1. **OBS password**: Integrations > Key vault in the Suite app, set OBS_WS_PASSWORD (Set/Save, then Test).
2. **Link settings**: on the Link page, confirm this PC's role is hub; give the real OBS scene and input names for the macros (defaults BRB, Main, Mic/Aux are guesses).
3. **Tailscale**: open the Tailscale tray app and turn it on.
4. **StreamElements token**: paste it yourself in the Suite if you have not.
5. **GitHub updates (only if you pick that in B10)**: store a read-only token in the vault as GITHUB_UPDATES_TOKEN and tell 04 the repo.
6. **Spotify rewards**: map "Song Request" and "Skip Song" rewards in the Spotify module if you want them, and run the blocklist import (Songify session).

## D. Things to turn off or remove

- Nightbot's !pm command: turn it off in Nightbot.
- Nightbot commands that Chatty now answers (87 fun commands): disable the matching ones in Nightbot once you see Chatty answering them once each.
- RocketRankBot: remove it from the channel.

## E. Optional site extras (05)

- 1200x630 orange/dark share image (put the file in D:\PinguinoSuite\PinguinoSite and tell 05).
- /tourney start date (for search Event data).
- Google Search Console and/or Bing verification code (they give you a short code or meta tag; send it to 05).

## F. Disk cleanup (only if you want space; all optional)

- Runner 1: delete the disposable Downloads list in Docs\DOWNLOADS_REVIEW.md and the 31 verified originals; archive-move D:\PinguinoBackup, D:\tmp, D:\tmp_wt_05data; remove empty D:\tmp_wt_05 and D:\.DS_Store.
- Already moved (not deleted): D:\Archive\Downloads-to-delete (85 items). You can delete that folder yourself once you are happy.
- Runner 2: delete duplicate listen VODs in Suite\modules\listen\data\sources (about 17.5 GB, evidence in Docs\LISTEN_INGEST_BUG_R2.md) and move Deploy\ to D:\Archive\drive-cleanup-2026-10-21\. Tell 00 "yes" and 00 checks with the Voice session first.
- Recycle Bin (26 GB): empty it yourself in Windows.

## G. Live checks for the next stream (nobody can test these offline)

- Each of the 87 canned Chatty commands answers exactly once.
- !rank dropshot / heatseeker / hoops (playlist ids unverified).
- A real hype train and goal announcement.
- !addpoints / !editpoints, and the Firsts game payout.
- Wheel spin (do not spin the real wheel with real viewers unless you want to).
- The simulator stops by itself when the stream goes live.

## H. Held until you say "done"

- The end-of-night 3x code audit and the 4-tier docs run (02/00). Say "done" when you want it.

## What 00 does without you

Host restarts, module restarts, app rebuilds, APP_LOG entries, relaying answers. Pending now: Host restart for c4520f0 (rate-limited lobby warning), not urgent.
