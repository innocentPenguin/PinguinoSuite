# proposals_for_bots.md: [APPLY] status (2026-10-23, worker 14)

Checked by searching the code for each item. Present in code is not the same as live-verified: the Host has not been restarted since, so nothing here was tested live.
Items belong to the bot sessions (Host, B0t, Helper, Chatty). Lore data (`channel_lore.json`, howBotsUse, never recount) is mine and is applied.

| Section | Item | Status |
|--|--|--|
| PinguinoBot | 1 no banter | code has the ask-a-mod / short-status path (PinguinoBotCore.cs); not live-verified |
| PinguinoBot | 2 queue join only on explicit !join | not checked by me, owner 10/B0t |
| PinguinoBot | 3 one private-match source | present (HostBots.cs, HostFeatureCommands.cs, HostLobbyPush.cs, Helper LobbyName) |
| PinguinoBot | 4 exact !pos / !next / !lobby | present (commands.json, BotCore, Helper) |
| Helper | 1, 2, 6 genuine-help only, short answers, review log | not checked by me, owner 11 |
| Helper | 3 wrong-context = negative feedback | present (PinguinoHelper.cs) |
| Helper | 4 "it's peng3" correction | present (PinguinoHelper.cs:732) |
| Helper | 5 quick answers | partly (links via $(link:key), 8c55fb0); not checked in full |
| Chatty | 1 quick-info layer | present in build-channel-lore.py / notes.mjs |
| Chatty | 2 lore memory + never recount | **applied** (notes.mjs LORE, build.mjs botRules, channel_lore.json live) |
| Chatty | 3 refuse timeouts, ask a mod | present (HostBots.cs, Helper, BotCore) |
| Chatty | 4 per-user repeat guard | present in BotCore/Host; not checked for Chatty itself |
| Chatty | 5 no mod/VIP/rumour comments | **applied** as lore rules (build.mjs / channel_lore) |
| Chatty | 6 clanker one dry line | **applied** (lore entry, howBotsUse) |
| Cross | isBot for bot accounts | present (KnownBots in HostBoards.cs, HostChannel.cs) |
| Cross | merged aliases as one person | applied in lore mining and memory; `rocketleaugelover221 -> synther22` is in aliases.json (2 hits), so Ivan's confirm was apparently given |

Held, need Ivan: ace/ziu/peng and `ssl` entries, squishy, joe bart, hayahrl, nicknames (DISCUSS), tournament pairings (DISCUSS).
