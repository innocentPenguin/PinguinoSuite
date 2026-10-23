# Lore health - 2026-10-23 (worker 14)

Checked `Data/lore` (private, git-ignored): `channel_lore.json` (22 items), `people_graph.json` (199 nodes, 215 edges, 7 groups), 199 person cards, `LORE_REPORT.md`, `proposals_for_bots.md`. Read-only check; nothing was changed. No names or quotes from the data are in this report beyond login handles needed to fix things.

## Clean
- No duplicate lore terms, no item without a meaning, no duplicate or self edges, no dangling edges (every edge endpoint is a node).
- Every node has a card and every card has a node (199/199). No node with 0 messages. No bot accounts in the graph.
- Opt-outs: 0 people with Privacy anon/forget in chat_memory.json right now, so nothing to purge. Re-check after the next `!optmeout`.
- All 22 lore items carry the `howBotsUse` suffix and `botRules` is present (a82bf19 work).

## Stale / needs a rebuild
1. **Graph is 3 days old** (built 2026-10-20 11:07Z). The 10-21 (158 KB), 10-22 and 10-23 logs are not in it. Rebuild: `parse.mjs` -> `merge-aliases.mjs` -> `graph/feat/cluster` -> `build.mjs` (needs the work dir; run when 100 says).
2. **Five alias accounts are still separate graph nodes with their own card**, although `aliases.json` (edited 10-21 14:56Z, after the build) merges them: `rocketleaugelover221` (-> synther_rl), `ixsamux` and `mirihater` (-> ixsamuu), `iq_zens` (-> iqzens), `unninocence` (-> kskycs2). Effect: their ties are split between two nodes, and `PeopleGraph.Closeness/Standing` looks up the MAIN login, so a main account loses the edges recorded under the alias (e.g. ixsamuu has 8 edges, plus 2+2 under his aliases). Two are also members of groups. The rebuild fixes all of it (merge-aliases runs before the graph step).
3. **`kskycs2` (target of `unninocence`) has no node at all** - the merged account never shows in the graph; the rebuild creates it.
4. **Lore items point at accounts that are not nodes** (they are aliases or merged names): `spongefredcircleshorts` (ego), `penguindads` (gamble all, TTS voices, Pinguinoraid), `synther22` (repo/peak), `fiayir` (!penguin edit war), a combined `sn0wmanny_/snowyroses_` (buns), `i_go_by_baty` (clanker), `innocentpenguin_` (Ivan's own channel, expected). Fix in `notes.mjs`: use the main login in `users` so the item links to a card.
5. Items' `since` dates are all <= 2026-09-16 (newest: `ads` 09-16, `goodnight sign-off` 10-14). Nothing from the last week is in the glossary yet; the Phase 1 candidate terms (`Docs/nightly/lore-phase1-2026-10-22.md`) are the starting point, still unreviewed.

## Privacy notes
- 72 of 215 edges carry an `example` field (a short real chat excerpt). The Host code never reads it (`PeopleGraph` uses only `mutual` and group membership, tested by the SECRET leak check), but the file itself holds verbatim chat. Keep `Data/lore` out of any export/zip/push; consider dropping `example` from the file the Host loads (build.mjs could write a second, example-free `people_graph.public.json`).
- Opted-out people are filtered at read time (`Boards.IsAnon`) and `build.mjs` already skips Privacy anon/forget (it matches on `v.Login`/`Aliases` of the id-keyed chat_memory.json, correct). Between rebuilds an opt-out stays on disk (node, card, edges) but is never used by the Host. Note: `Tools/nightly-review.py` matches opt-outs on the dict KEY, but chat_memory.json is keyed by Twitch id, so it would not match anyone; it should compare `Login` instead (not my file, 0 opt-outs today so no leak yet).

## Suggested order
1. Rebuild after merging the logs (fixes 1-3). 2. Edit `notes.mjs` users (4). 3. Optionally write an example-free `people_graph.public.json` from `build.mjs`, and fix the opt-out key match in `Tools/nightly-review.py`.
