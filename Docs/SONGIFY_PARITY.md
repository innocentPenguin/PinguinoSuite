# Songify → PinguinoMusic parity

Songify (C:\Users\ivanm\Documents\Songify) was reverse-read for its config, commands and widgets. PinguinoMusic is the Suite's Spotify module (`Suite/modules/spotify`, port 8771). Status: **done** = implemented + fixture-tested, **partial**, **planned**, **blocked**, **skip** (deliberately not copied).

| Feature (Songify) | PinguinoMusic before | Gap | Plan / status |
|---|---|---|---|
| Redeem-only requests ("Song Request" reward) | `!sr` open to chat, rules + fair queue | no way to require the reward | **done** `chat_requests` off = chat `!sr` refused (`reward_only`), redeems + mods still work |
| Refund points on rejected request | none | rejection never told Twitch | **done** engine/API return `refund:true` for redeems rejected for a code in `refund_on` (too_long, full, lookup, offline, limit, blocked, none). **blocked** actual Twitch refund needs `channel:manage:redemptions` in HostAccount.cs ScopeInfo + Automations spotify-redeem acting on `refund` (00/02) |
| Skip Song reward | `!skip` vote/staff | no paid skip | **done** skip from a redeem force-skips (refund flag if nothing playing) |
| Global cooldown (1 s) | per-user cooldown only | no all-viewers gap | **done** `global_cooldown_s`, staff bypass |
| Max pending / per-role caps / max length | per-user, per-role, length limits | – | already had (kept) |
| Add requested song to a playlist (`addSrToPlaylist`) | none | – | **done** `playlist_add` (id/URL); scopes playlist-modify-* added |
| Clear queue when offline (`autoClearQueue`) | none | – | **done** `clear_on_offline` (on live stop) |
| Blocklist (91 IDs) + import | block by track/artist/link | no import, no bare IDs | **done** `POST /api/blocklist/import`; Songify's 91 IDs in `Docs/imports/songify-blocklist.txt`; link/URI entries now match too |
| `!song` | `!song` | – | already had |
| `!songqueue` | `!queue` | – | already had (alias) |
| `!songpos` | none | – | **done** `!songpos` / `!pos` |
| `!songnext` | none | – | **done** `!songnext` / `!next` |
| `!wrongsong` | `!wrongsong` | – | already had |
| `!songban` | `!blocksong` | alias | **done** alias |
| `!voteskip` | vote skip | – | already had |
| `!vol` | `!vol` (staff) | – | already had |
| `!songlike` | none | – | **done** staff `!songlike` saves the playing track (needs user-library-modify; re-auth) |
| `!togglesr` | `!sr open/close` | alias | **done** staff `!togglesr` |
| `!songcommands` | `!help` | alias | **done** alias |
| Per-command permission levels | fixed roles | – | **done** `cmd_roles` ("command=role,role"); broadcaster always allowed |
| OBS now-playing widget | `/overlay` (themes, art, next, alerts) | – | already had, richer than Songify |
| OBS queue widget | none | – | **done** `/overlay/queue` (theme/accent/count/width/size/eta/now query) |
| Public queue page | none | – | **partial** `/queue` serves the same widget as a page; public exposure (site proxy, 05 via 00) **planned**; JSON at `/api/queue.json` has no track IDs |
| OBS lyrics widget | none | – | **planned** LRCLIB synced lyrics cached by URI, `/overlay/lyrics` |
| Websocket 22345 feed | polling JSON | – | **skip** `/api/overlay.json` + `/api/queue.json` replace it |
| Pear Desktop / YT Music source | none | – | **skip** Spotify only |
| Spotify Canvas, album-art file for OBS text sources | art URL in overlay | – | **skip/planned** art already in overlay JSON |
| Sub-tier / follower request caps | roles broadcaster/mod/vip/sub | no tiers | **planned** needs tier in the chat role payload from the Host |
| Pay with currency instead of channel points | none | – | **planned** pengs economy hook (spend on request) once the economy store lands (02) |
| Stats (most requested etc.) | log only | – | **planned** surface from lore/boards |
| Teach/lore layer | – | – | **planned** feed requests to the lore log |

## What Ivan must do (nothing here is live yet)
1. Spotify Client ID, then sign in again so the new scopes (playlist-modify, user-library-modify) are granted.
2. Create/map "Song Request" and "Skip Song" rewards, enable the `spotify-redeem` automation action, set `chat_requests` off if reward-only is wanted.
3. Import the blocklist: POST `Docs/imports/songify-blocklist.txt` body to `/api/blocklist/import`.
4. For real refunds: add `channel:manage:redemptions` to the Host scopes and re-sign in (00/02).

Tests: `python -m unittest discover -s tests` in the module (101 pass), new file `tests/test_songify.py`. Needs `Update-Module spotify` from 00 to go live.
