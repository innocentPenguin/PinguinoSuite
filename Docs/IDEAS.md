# Combined ideas and questions (kept by 00)

Source tags: Ivan, 01 Suite/app, 012 Lite, 013 Master View, 02 Host/bots, 021 Helper, 022 Chatty, 023 Overlays, 03 Multi, 05 Site, Music.
Status: open / building / done / asked-Ivan.

## Open questions for Ivan
- ActivityBonus (chat-line points on top of the 5-min rates): keep on or off? (02)
- Customs match_start lines: add emojis too? (02)
- Fortnite activity defaults (sizes)? (02)
- Where does the "Tipped" profile option show total vs badge only? (00)
- Railway still not deploying site pushes; retry task at 12:35 (05)

## Ideas
| # | Idea | From | Status |
|---|------|------|--------|
| 1 | Tip intake from a real source (StreamElements/Streamlabs webhook); !tipped is interim | 02 | open |
| 2 | Tune UI fields for the points knobs plus a points-preview panel | 02 | open |
| 3 | Match awards/loans/depreciation into the per-stream ledger | 02 | open |
| 4 | Lore/people-graph into timeout lines | 02 | open |
| 5 | Held 3x audit + 4-tier docs (only when Ivan says) | 02, 01 | held |
| 6 | !alert command + intro fold-in; import Host alert sounds into a profile; retire Host popups | 03 | building |
| 7 | Alert sound/media upload from the editor (no typed URLs) | 03 | open |
| 8 | Kick connector | 03 | open |
| 9 | Dashboard as default Multi window with left nav | 03 | open |
| 10 | Alert scenes that switch profile with the OBS scene via Link | 03 | open |
| 11 | Goal/hype-train progress bar overlay in the alert engine | 03 | open |
| 12 | Real end-to-end release dry run (Build-Release, install --local, update, rollback) | 01 | open |
| 13 | Economy page and Timers tab in the Suite | 01 | open |
| 14 | Shorter Listen subtitle segments (split at sentence boundaries) | 01 | open |
| 15 | Signed releases (Ed25519, manifest.sig) | 01 | open |
| 16 | Lyrics widget in the overlay | Music | open |
| 17 | Site /queue exposure + song log page | Music | open |
| 18 | Per-tier caps / queue time limits | Music | open |
| 19 | Now-playing chat announce per tier | Music | open |
| 20 | Mod commands for song queue (!srremove, !srmove/top, !srpause/play, !srmute/fade) agreed with 05 | Music | open |
| 21 | Artist-exact ban by Spotify artist id | Music | open |
| 22 | Request history / leaderboard | Music | open |
| 23 | Automatic fallback playlist when queue is empty | Music | open |
| 24 | OBS per-source monitoring guide for the 2nd Spotify output | Music | open |
| 25 | Tippers leaderboard card (needs tip totals) | 023, 00 | open |

## Added 2026-10-22 (check-in round)
| # | Idea | From | Status |
|---|------|------|--------|
| 26 | Alert profile export/import to file (back up/share looks) | 03 | open |
| 27 | Lite: real Install/Verify/Eject/Install-again of a small module on a scratch copy | 012 | open |
| 28 | Typo-tolerant commands ("Did you mean !join?") checked against commands.json | 021 | open (also Plan 7 C) |
| 29 | Helper "unanswered" list feeds the pack builder as drafts for a mod to approve | 021 | open |
| 30 | More natural-language intents (points, strike rules, opt-out); follow-up context beyond Minecraft | 021 | open |
| 31 | Spanish/Portuguese pass for common joins/questions (if chat uses them) | 021 | asked-Ivan |
| 32 | Mod command to show/reload the Helper pack | 021 | open |
| 33 | Host: !pm still prints a stored password (HostBots.cs 68-70): fix; push lobby name to site | 021 -> 02 | open, needs 02 |
| 34 | Chatty event reactions (wheel winners, customs finish, raids, hype train) with cooldown | 022 | open |
| 35 | Friendly refusal/failure lines for mod actions and timeouts | 022 | open |
| 36 | Lore-based "welcome back" lines (private, respects opt-outs) | 022 | open |
| 37 | !chatbot status line says why it is quiet | 022 | open |
| 38 | End-of-stream recap line (mod-approved wording) | 022 | open |
| 39 | Canned-command editor page in the Suite for canned_commands.json | 022 | open |
| 40 | First-time-today greeting variety; birthday/follow anniversary lines | 022 | open |
| 41 | 05: confirm `tipped:{total,count,last}` field names with 02 | 05 -> 02 | asked 02 |
| 42 | Suite UI page for overlay options (sliders + guides preview) | 023 | open |
| 43 | Subs! card spotlight for resub anniversaries this week | 023 | open |
| 44 | Per-overlay safe-area presets (1080p/1440p/vertical) | 023 | open |
| 45 | Pre-stream health check that overlay-options.js loads | 023 | open |
| 46 | Q for Ivan: show gifted subs in T2/T3 on the Subs! card (default yes)? | 023 | asked-Ivan |

## Ivan's decisions 2026-10-22 09:56
- ActivityBonus: KEEP ON but minor; gifts + watch time must stay ahead (02 to check the numbers).
- Gifted subs in T2/T3 on Subs! card: YES. Languages: English + Mexican Spanish only.
- Alert profile export/import: yes. Profile follows OBS scene: do it. Goal + hype-train bar: yes. Dashboard default window: yes.
- Multistream again: Kick, YouTube, TikTok; import TikTok Live data (chat/gifts/follows) into Multi. (03, research first)
- Tip source: not important. Points settings page with preview: yes.
- Match awards: play in a match = 7 min of viewer watch rate x2; win = 7 min viewer rate x3 (02 to confirm exact numbers back).
- Typo commands: !join-type (affects others) asks "did you mean?" and waits for confirmation; info commands just run.
- Chatty reactions to raids + hype trains yes; wheel reactions later (when giveaway exists). Welcome-back lines from lore (e.g. had an event yesterday / big bits day).
- End-of-stream recap: yes, toggleable. BUG: raid "prepare your emotes" line fires when raid is pressed; must fire when raid is SCHEDULED.
- Canned-command editor: explained to Ivan (fixed prewritten replies), pending his OK.
- Music: lyrics widget (toggle in Spotify master section), mod queue commands, request leaderboard ONLY on song pages, fallback playlist, site queue page: all yes.
- 01/012/023 list: all yes (release dry run, signed releases, Economy+Timers tabs, shorter Listen clips, real Lite Install/Eject test, overlay-options sliders page, resub-anniversary spotlight pending explanation).

## Ivan's answers 2026-10-22 10:04
- match_start emoji lines were for TOURNEYS only; customs keep our set colours. Master View: change customs team name + colour, with colour presets.
- Fortnite: playing-with-viewers sizes 1/2/3 + free text box for more; customs keep 2v2/3v3/4v4; bring KOTH to Fortnite. Master View needs a game/activity selector.
- Stream title + description + tags editable from Master View across platforms (Twitch, YouTube incl. scheduling live broadcasts; TikTok stays manual).
- Canned-command editor: YES (022 + 01).
- Resub anniversary spotlight: keep built, but sub streak + months subscribed must show on the viewer profile (05 + 02).
- BACK-PAY: everyone who ever cheered/gave bits since the start of the logs gets 40% of what the current system would have paid (02).
