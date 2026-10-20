# Practice mode (matchmaking + tournament wheel rehearsal)

Mods type `!practice on [N]` (default 8, max 40 fake players in total), `!practice add [N]`, `!practice off`, `!practice` (status).
Fake players are `practice01`, `practice02`, ... with spread-out MMR (450-1550, source "manual", so no Tracker lookups).

* They join the real queue (matchmaking, `!next`, `!reroll`, teams, overlays all work) and, while tournament sign-ups are open, the wheel sign-ups too (run `!practice add` again after `!wheel open` if the wheel was opened later).
* **Memory only.** Never written to `players.json`, `queue.json`, `matches.json`, `current_match.json` or `wheel_session.json`; a practice game changes nobody's wins, losses, points or King of the Hill wins (even the real players in it); nothing from practice goes into the standings or match history pushed to the website. A restart or `!practice off` removes everything. While practice entrants are in the wheel, an open sign-up list is still saved WITHOUT them (so real sign-ups survive a restart), and a practice draw is not saved; `!practice off` reloads the real wheel session from disk.

## Fields the website sees (POST /api/bot/state and /api/bot/wheel)

| where | field |
|---|---|
| state | `practice` (bool: any practice player exists) |
| state | `queue[].practice` |
| state | `currentMatch.practice`, `currentMatch.blue[].Practice`, `currentMatch.orange[].Practice` (also in `liveMatch`) |
| wheel | `practice` (bool), `entrants[].practice` |

The site (PinguinoSite worker `wheelClean`) already keeps a practice wheel in memory only. For state: treat anyone flagged `practice` as a non-member (no profile, no stats, nothing stored).
`/api/bot/standings` and `/api/bot/matches` never contain practice players or practice games.

## MMR is not in public wheel data
The bot pushes `entrants[].mmr` and `teams[].avg` to `/api/bot/wheel` (needed for the staff page and the balanced mode label); the public view built by the site (`wheelPublic`) drops them. The site must keep dropping them.
