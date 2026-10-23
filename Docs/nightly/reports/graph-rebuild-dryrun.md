# People-graph rebuild - DRY RUN (worker 14, 2026-10-23)

Nothing live was touched. Work dir `Data/lore-work/dry/` (git-ignored, ~117 MB on D:), output `Data/lore-work/dry/out/`. Command (reproducible): `parse.mjs` -> `merge-aliases.mjs` -> `graph.mjs` -> `feat.mjs` -> `cluster.mjs` -> `LORE_OUT=<dir>/out node build.mjs <dir>` (all in `Tools/lore-mining`). Input: all logs `Data/chat_logs/2026/**` (now 671,039 messages vs 666,891 at the last build, so +4,148 incl. 10-21..10-23), 1,779 users, aliases.json (25 aliases) merged.

## Result in numbers
| | live (10-20 build) | dry run |
|---|---|---|
| nodes / person cards | 199 | 196 |
| edges | 215 | 217 (9 added, 7 removed) |
| groups | 7 | 6 (sizes 87,10,4,3,3,3,3 -> 90,10,4,3,3,3) |
| `channel_lore.json` | - | identical content (the hand edits and botRules are reproduced by build.mjs) |
| verbatim excerpts in public graph | 72 (original) | 0 in `people_graph.public.json` (67 scrubbed from the original, 196 card evidence blocks) |

## Nodes
- **Removed (merged into their main account):** rocketleaugelover221 -> synther_rl, ixsamux and mirihater -> ixsamuu, iq_zens -> iqzens, unninocence -> kskycs2.
- **Added:** `kskycs2` (2,651 msgs, 2026-08..10, no group) - the merge target that was missing - and `iamplyrb` (crossed the 150-message threshold with the new logs).
- **Message totals:** ixsamuu 3,745 -> 7,356 (absorbs 2 aliases), synther_rl 6,911 -> 9,899 (absorbs rocketleaugelover221); other growth is just the 3 new days (yoohoo15 +448, snowyroses_ +384, blizzyfvv +385, pineyapplie +400).

## Edges (people-timeout and welcome-back closeness is derived from these)
- **Added (9):** blizzyfvv+kskycs2, ixsamuu+ytabdul, ilovemyfruit+synther_rl, dachillman36+pineyapplie, cups0ftea+ixsamuu, ixsamuu+synther_rl, freshchair+ixsamuu, shadowrlttv+synther_rl, pineyapplie+t1cklem0n3ter324. Seven of them are alias merges re-attaching old ties to the main login; dachillman36+pineyapplie and pineyapplie+t1cklem0n3ter324 are genuinely new from recent chat.
- **Removed (7):** all alias-node edges (blizzyfvv+unninocence, mashka_rl+mirihater, ixsamux+lvlmarshmello, ilovemyfruit+rocketleaugelover221, ixsamux+shadowrlttv, mirihater+ytabdul, lvlmarshmello+rocketleaugelover221) - they now live on the main login.
- **Closeness level changes (acquainted -> buddies), 5:** ixsamuu with mashka_rl, lvlmarshmello, yoohoo15, shadowrlttv (alias merge adds their mutual counts), and pineyapplie+yoohoo15 (21 -> 35). No pair changed to or from "duo" and no friendship was demoted, so existing timeout/welcome lines for current pairs behave the same; ixsamuu simply gets friendlier lines with 4 regulars.
- Groups: 3 group members in the live graph were not nodes (alias leftovers, all fixed); the dry-run group 1 grows 87 -> 90 and one small 3-group dissolved.

## Findings the rebuild does NOT fix (hand work in `notes.mjs`)
- Lore items still reference alias/merged names in `users` (spongefredcircleshorts, penguindads, synther22, fiayir, `sn0wmanny_/snowyroses_`, i_go_by_baty) - use main logins. See `lore-health.md`.
- No new glossary terms are added by a rebuild; Phase 1 candidates (`Docs/nightly/lore-phase1-2026-10-22.md`) are unreviewed.
- Fixed in build.mjs while preparing this: the `source` field was a hard-coded stale string, it now reports the real message/login counts and date range.

## To apply (needs 100's OK; ~2 min, then a Host restart is NOT needed - the Host reloads people_graph when the file's timestamp changes)
```
cd Tools/lore-mining
node build.mjs D:/PinguinoSuite/Data/lore-work/dry      # writes Data/lore (+ people_graph.public.json and person_cards_public/)
```
After the build, delete the 5 stale alias cards (`person_cards/` and `person_cards_public/` for rocketleaugelover221, ixsamux, mirihater, iq_zens, unninocence); build.mjs only writes cards, it does not remove old ones.
(The work dir's msgs/feat/pairs/clusters are already built, so only build.mjs is needed. Before applying I would copy the current `Data/lore` to `Data/lore-work/backup-2026-10-23/` so it can be rolled back.) After applying: delete `Data/lore-work/dry` (117 MB) or keep for the next incremental run. Opt-outs: build.mjs excludes Privacy anon/forget users; none exist today.
