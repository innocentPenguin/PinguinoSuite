# Lore / stats mining (00 - Pinguino, 2026-10-20)

Private tooling; outputs go to Data\lore\ and Data\chat_logs\sidecar\ (both git-ignored). Run order (all take the work dir as argv[2], the scripts read/write msgs.jsonl etc. there):

1. `parse.mjs <work>` reads Datachat_logs6**.txt -> msgs.jsonl, notices.jsonl; then `merge-aliases.mjs <work>` folds aliases (raw copy kept as msgs.raw.jsonl)
2. `graph.mjs`, `feat.mjs`, `cluster.mjs`  -> pairs.json, feat.json, clusters.json
3. `build.mjs`  (+ `notes.mjs` hand-written notes and lore glossary) -> Data\lore\{people_graph.json, channel_lore.json, person_cards\}
4. `sb.mjs` extracts per-message counts from Archive\streamerbot-2026-10-19\logs.zip -> sb_msgs.tsv; `daily.mjs` -> Data\chat_logs\sidecar\{streamerbot_daily_counts.json, message_totals_merged.json} (per user per UTC day = max(site logs, Streamer.bot))
5. `cal.mjs` compares Streamer.bot vs the public logs per user (validation: median ratio 0.983)
6. `alias.mjs` finds possible duplicate accounts (vocabulary + zero overlap), `ctx.mjs`/`pair.mjs`/`sample.mjs` read context for a term/pair/user, `bots.mjs` command and bot-address stats.

Guardrails: facts from chat only; no age/family/health/private-life inferences; skip anyone with Privacy anon/forget in chat_memory.json.
