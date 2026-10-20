<!-- INDEX-BEGIN -->
INDEX: Name history. Builder `Tools\build-namehistory.py` | test `Tools\test-namehistory.py` | Helix fetch `Tools\fetch-helix-ids.py` | data `Data\namehistory\names.json`, `lookups.json` | sections: Method, Counts, Limits, CERTAIN groups, LIKELY, POSSIBLE, unresolved statements.
<!-- INDEX-END -->

# NAMEHISTORY - who was who, over time

Built by `Tools\build-namehistory.py` (rerunnable, offline). Output: `Data\namehistory\names.json` (+ `lookups.json`). Test: `python Tools\test-namehistory.py` (fixtures only). Read-only against the Host, nothing pushed, no secrets, no network.

Purpose: a future `!namehistory <user>` answers "Was X, then Y since 2026-03". Lookup = find the chatter whose `names[].login` equals the user, then print the names in `firstSeen` order.

## Method
Sources used:
- Day logs `Data\chat_logs\2026\*` (first/last time and message counts per login, who they @mention).
- Chatty live jsonl `Data\chat_logs\live` (has Twitch ids), Streamer.bot `users.dat` in `Archive\streamerbot-2026-10-19\raw-data` (id + login, 2286 ids total), `Data\runtime\multi\multi.db` (twitch user_id).
- `Data\boards\aliases.json` (Ivan's merges; read only, never written).
- Not usable: `twitch_data.db` and the 2.4 GB Streamer.bot `.log` files carry no id-to-login pairs (the db is not readable as sqlite; the logs list the bot only). SE import names are logins only, no ids, so they add nothing beyond what the day logs have.
- NOT done: the three public log sites and potat.app lookups (this script never touches the network; those need the Host/fetch tools). Opt-outs (`hidden_sources.json`: lvlmarshmello) are copied into `lookups.json` as `skipOptedOut` and their ids are left out of the id list, so a later fetch cannot go around Marsh.

Tiers:
- CERTAIN = same Twitch id under different logins, or an explicit alias in aliases.json. Only these are merged into one chatter.
- LIKELY = chat statement naming a login we saw, or very similar names with a hand-over in time plus overlap in who they talk to.
- POSSIBLE = similar names, clean hand-over within 45 days. Nothing below CERTAIN is ever merged; these are in `pairs` for Ivan's review.

## Counts
- 2370 chatters (logins grouped), 2261 with a Twitch id (2287 ids known). Build with `--helix-ids Data\namehistory\helix_ids.json` (fetched 2026-10-20 08:12).
- 171 chatters with more than one name (CERTAIN), 354 names in those groups: 10 from `aliases.json`, 161 from Helix by id (old login in our data, Helix returns the current one; the current login often has no dates, `firstSeen` null).
- 0 LIKELY (the 4 earlier pairs are now covered by aliases.json or banned) and 15 POSSIBLE candidate pairs; 1 banned impersonator (`spongefredcircleshorts1`) flagged, never paired.

## Limits (read this before trusting it)
- Old counts below (CERTAIN groups list, LIKELY table) predate the Helix merge; `names.json` is the source of truth. Aliases may also be alt accounts, not renames.
- Day logs have no ids, so an old login with no id cannot be proven. Helix by id only returns the current login for an id, so a rename is proven only when we hold the id under the old login. Helix was run once; rerun `Tools\fetch-helix-ids.py` (needs `TWITCH_CLIENT_ID` and `TWITCH_APP_TOKEN` in env) to refresh.
- Names are lower-case logins; display-case differences are not tracked.

## CERTAIN groups (for 00/02: all are already in aliases.json except the last)

- **blizzyfvv** (id 1330579035): blizyfvv (2026-04-21..2026-06-02) -> spongefredcircleshorts (2026-06-02..2026-08-01) -> blizzyfvv (2026-08-02..2026-10-20)
- **cyfirl** (id 552617667): sg_cyfi (2026-06-01..2026-06-03) -> sg_yen (2026-06-27..2026-08-10) -> cyfirl (2026-08-13..2026-10-18)
- **ixsamuu** (id 1324116543): mirihater (2026-06-20..2026-08-30) -> ixsamuu (2026-08-30..2026-10-19)
- **kskycs2** (id 1351994814): unninocence (2026-08-16..2026-10-14) -> kskycs2 (2026-10-19..2026-10-19)  <- NEW, from ids, not in aliases.json
- **mashka_rl** (id 996145471): miri__0_0 (2026-03-03..2026-08-03) -> mashka_rl (2026-08-03..2026-10-20)
- **notflayir** (id 555643785): fiayir (2026-02-21..2026-05-22) -> bosskid274 (2026-05-24..2026-07-21) -> flayir_ (2026-07-21..2026-10-11) -> notflayir (2026-10-11..2026-10-17)
- **snowyroses_** (id 1301283416): roseflakes_ (2026-03-31..2026-05-31) -> rosefiakes_ (2026-05-07..2026-05-19) -> sn0wmanny_ (2026-05-31..2026-09-16) -> roseflakess_ (2026-07-11..2026-07-11) -> snowyroses_ (2026-09-16..2026-10-20)
- **synther_rl** (id 1435315327): rocketleaugelover221 (2026-03-12..2026-05-12) -> synther22 (2026-05-13..2026-07-14) -> penguinhater5 (2026-07-14..2026-09-13) -> synther_rl (2026-09-13..2026-10-20)
- **ytabdul** (id 1459994661): penguindads (2026-05-20..2026-07-22) -> penguinslittlebro (2026-07-22..2026-09-20) -> ytabdul (2026-09-20..2026-10-20)

Hand-off pair NOT yet in aliases.json: `unninocence -> kskycs2` (CERTAIN, same id). Note `blizyfvv` (one z, 2026-04-21..06-02) and `blizzyfvv` (two z, 08-02..) are different logins in the same alias group.

## LIKELY pairs (Ivan to confirm)

| old | new | name sim | shared @mentions | gap days | old last | new first |
|---|---|---|---|---|---|---|
| iamplyrb | iaplyrb | 0.93 | 0.0 | 0.8 | 2026-04-08 | 2026-04-09 |
| iamplyrb | iamplayry | 0.82 | 0.0 | 0.7 | 2026-04-08 | 2026-04-08 |
| skurxxwiel___ | skurxxwiel___swag | 0.83 | 0.0 | 0.3 | 2026-03-28 | 2026-03-28 |
| spongefredcircleshorts | spongefredcircleshorts1 | 0.98 | 0.0 | 1.1 | 2026-08-01 | 2026-08-03 |

## POSSIBLE pairs (weak: similar name and a hand-over only)

| old | new | name sim | shared @mentions | gap days | msgs old/new |
|---|---|---|---|---|---|
| addayc7 | adday_rl | 0.71 | 0.0 | 0.9 | 140/2108 |
| blizy_jr | blizzyhater | 0.67 | 0.0 | 11.0 | 14/6 |
| flex_xrl | firefoxxrl | 0.71 | 0.0 | 16.2 | 22/40 |
| jahsehonfroy1240 | jahsehonfroy1240grapefam | 0.8 | 0.0 | 18.1 | 48/8 |
| krispychicken721 | krispy721 | 0.72 | 0.0 | 0.0 | 3244/1902 |
| leakzfl | leakzpkz | 0.67 | 0.12 | 12.9 | 364/898 |
| mayshon188 | mayshonrl | 0.74 | 0.0 | 33.0 | 28/94 |
| mgillette_ | zlette_ | 0.67 | 0.0 | 10.7 | 18/8 |
| penguineater46 | penguinhater5 | 0.81 | 0.0 | 23.0 | 24/5126 |
| primal__rl_ | reprisalrl | 0.78 | 0.0 | 11.0 | 40/122 |
| projectsark | projectnsjedi | 0.67 | 0.0 | 12.1 | 10/46 |
| skelly_undiez8 | skellynz | 0.76 | 0.05 | 8.9 | 158/294 |
| synther111 | synther_rl | 0.74 | 0.04 | 13.0 | 26/2586 |
| xtian420martin1 | xtian92420martin | 0.9 | 0.0 | 17.0 | 206/142 |
| zylorocketleague | shortfishrocketleague | 0.7 | 0.0 | 43.0 | 24960/6 |

## Chat statements about renames/new accounts (need Ivan, none resolved)
Speaker, date, text; the named target was not a login in our logs, so these are leads, not pairs. Full list (78) in `names.json` under `unresolvedStatements`.

- 2026-03-26 **lolro_535**: its not really my name i got hacked and sm1 changed my name to this
- 2026-03-26 **lolro_535**: its not really my name i got hacked and sm1 changed my name to this
- 2026-03-29 **carteriscool898**: i changed my name to hollychud
- 2026-03-29 **carteriscool898**: i changed my name to hollychud
- 2026-04-12 **jams1509**: its my old account that has it
- 2026-04-12 **jams1509**: its my old account that has it
- 2026-04-27 **mostafa_sr**: i changed my name to PlayingPenguin
- 2026-04-27 **mostafa_sr**: i changed my name to PlayingPenguin
- 2026-05-07 **iq_zens**: this is my old acc
- 2026-05-07 **iq_zens**: this is my old acc
- 2026-05-10 **fiayir**: ADD MY NEW ACC PLS GUYS I TYPED IN GENERAL
- 2026-05-10 **fiayir**: ADD MY NEW ACC PLS GUYS I TYPED IN GENERAL
- 2026-05-12 **fiayir**: im zen bc i changed my name to zen
- 2026-05-12 **fiayir**: im zen bc i changed my name to zen
- 2026-05-17 **tbhidklol798**: I just joined discord cause my old acc got banned
- 2026-05-17 **tbhidklol798**: I just joined discord cause my old acc got banned
- 2026-05-24 **phil_flock**: so flayir. is that your new name and I gotta change your emote?
- 2026-05-24 **phil_flock**: so flayir. is that your new name and I gotta change your emote?
- 2026-06-19 **shadowrlttv**: @xWaghu new name who dis
- 2026-06-19 **shadowrlttv**: @xWaghu new name who dis
- 2026-06-29 **sn0wmanny_**: what was my old acc name
- 2026-06-29 **sn0wmanny_**: what was my old acc name
- 2026-07-07 **shadowrlttv**: new name who did
- 2026-07-07 **shadowrlttv**: new name who did
- 2026-07-14 **mocha_please**: my new account finally let's me chat hellooo penguin
- 2026-07-14 **mocha_please**: my new account finally let's me chat hellooo penguin
- 2026-07-15 **bosskid274**: penguin do you like my cats new name its called gabe itch
- 2026-07-15 **bosskid274**: penguin do you like my cats new name its called gabe itch
- 2026-07-24 **jeebus_24**: So my old name was Jeebus. Got sick of seeing it. So darkmoonneon was something that sounded cool to me.
- 2026-07-24 **jeebus_24**: So my old name was Jeebus. Got sick of seeing it. So darkmoonneon was something that sounded cool to me.
- 2026-08-26 **nxghtmare_rl_**: my new username is long aswel:)
- 2026-08-26 **nxghtmare_rl_**: my new username is long aswel:)
- 2026-08-30 **gonkilluagg**: Hey look at my new username inside the game
- 2026-08-30 **gonkilluagg**: Hey look at my new username inside the game
- 2026-09-09 **wyatt104987**: when we play Fortnite, my new name is Wyatt macro
- 2026-09-09 **wyatt104987**: when we play Fortnite, my new name is Wyatt macro
- 2026-09-13 **penguinhater5**: new username tmrw
- 2026-09-13 **penguinhater5**: new username tmrw.
- 2026-09-13 **penguinhater5**: new username tmrw
- 2026-09-13 **penguinhater5**: new username tmrw.
- 2026-09-14 **mashka_rl**: @yoohoo15 yup dat was my old name
- 2026-09-14 **mashka_rl**: @yoohoo15 yup dat was my old name
- 2026-09-16 **flayir_**: my old acc isnt hacked
- 2026-09-16 **flayir_**: my old acc isnt hacked
- 2026-09-17 **leolikesrocks**: Peng since my mc account got hacked my new account is cheata smth
- 2026-09-17 **leolikesrocks**: Peng since my mc account got hacked my new account is cheata smth
- 2026-09-26 **steezy2134**: i just got banned on my old main, so i am working on getting my new account ranked ready, but my peak in val is like plat, diamond
- 2026-09-26 **steezy2134**: i just got banned on my old main, so i am working on getting my new account ranked ready, but my peak in val is like plat, diamond
