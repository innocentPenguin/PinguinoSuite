# Runbook: apply the people-graph rebuild (needs 100's OK)

Preconditions: the dry run exists at `Data/lore-work/dry/` (see `graph-rebuild-dryrun.md`). If it is older than a day, redo step 0 first so it includes the newest logs. Takes about 3 minutes. No Host restart is needed for the graph (the Host reloads `people_graph*.json` when the file timestamp changes); the code from ec539eb / ee0fad9 needs the normal Host build. Run from `D:\PinguinoSuite` in Git Bash. Nothing here is committed or pushed (`Data/*` is git-ignored).

## 0. (only if the dry run is stale) refresh it
```
cd Tools/lore-mining; W=D:/PinguinoSuite/Data/lore-work/dry
node parse.mjs $W && node merge-aliases.mjs $W && node graph.mjs $W && node feat.mjs $W && node cluster.mjs $W && LORE_OUT=$W/out node build.mjs $W
```
`merge-aliases.mjs` keeps the raw copy as `msgs.raw.jsonl`; parse starts from the logs again. Compare `$W/out` with live before step 2 (the numbers in the dry-run report).

## 1. Backup (rollback point)
```
B=D:/PinguinoSuite/Data/lore-work/backup-$(date +%Y-%m-%d-%H%M); mkdir -p $B && cp -r Data/lore/. $B/ && ls $B
```
The backup must hold `people_graph.json`, `people_graph.public.json`, `channel_lore.json`, `person_cards/` (199), `person_cards_public/`, `LORE_REPORT.md`, `proposals_for_bots.md` (about 10 MB, on D:).

## 2. Apply
```
cd Tools/lore-mining && node build.mjs D:/PinguinoSuite/Data/lore-work/dry
```
It writes `Data/lore/` in place: `people_graph.json` (private, with excerpts), `people_graph.public.json` and `person_cards_public/` (the scrubbed copies the Host and bots read), `person_cards/`, `channel_lore.json`. It prints `scrubbed N edge examples ...` and `cards 196 edges 217 groups 6` (numbers change with newer logs).

## 3. Delete the 5 stale alias cards (build.mjs only writes cards, it never removes old ones)
```
cd D:/PinguinoSuite/Data/lore
for a in rocketleaugelover221 ixsamux mirihater iq_zens unninocence; do rm -f person_cards/$a.json person_cards_public/$a.json; done
ls person_cards | wc -l; ls person_cards_public | wc -l
```
Both counts must equal the node count (196). These are the aliases merged into synther_rl, ixsamuu, iqzens and kskycs2. Delete only those five names; the private files are covered by the step 1 backup.

## 4. Verify (every line must start with OK)
```
cd D:/PinguinoSuite && node Tools/lore-mining/verify-apply.mjs
```
(`Tools/lore-mining/verify-apply.mjs` checks: no alias account is still a node, no dangling edges, cards == nodes, public cards == nodes, no excerpts in the public graph, no `evidence` in public cards, `kskycs2` is a node, and prints node/edge/group counts.)
Then run the repo tests that use the graph code (they use temp graphs, so they prove the code, not the data): `python Tools/test-host-timeoutgraph.py` and `python Tools/test-welcomeback.py`. In the live Host the next timeout between two known regulars logs `people-graph closeness buddies|duo` without a restart.

## 5. Rollback (wrong counts, or Host log errors mentioning `people_graph.json`)
```
B=<the backup folder from step 1>; cd D:/PinguinoSuite/Data && mv lore lore.bad && mkdir lore && cp -r $B/. lore/ && ls lore
```
`lore.bad` keeps the bad build for inspection; delete it later. The Host picks up the old files by itself. If only the public copies are suspect, delete just `people_graph.public.json`: the Host falls back to `people_graph.json` when it is missing.

## 6. Cleanup after a day with no problems
`rm -rf Data/lore-work/dry` (about 117 MB) and any `backup-*` folders you no longer need. Keep one backup.

Opt-outs: `build.mjs` excludes Privacy anon/forget people (by Login and Aliases). Re-run the rebuild after a `!optmeout` / `!forgetme` to purge the person from graph and cards; until then the Host itself ignores anon and forget people for every graph line (ee0fad9).
