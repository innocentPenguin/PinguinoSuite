# Phase 1 lore proposals - chat of 2026-10-22 (303 human messages)

Status: **PROPOSALS ONLY, nothing applied.** For 100's approval. Source: `Tools/lore-mining/nightly-phase1.mjs 2026-10-22` (output kept privately in `Data/lore-work/phase1-2026-10-22.md`), each term read in context. Skipped on purpose: `joe bart` (one person spamming a bit, not shared lore) and `hayahrl` (11 messages, below the 150-message card threshold; revisit when active). The 10-23 log has only 2 messages, so nothing came from it.

Rules for every entry below (same as `botRules`): never recount who said it or when, no quotes, no counts, never explain the joke, drop it for anyone opted out.

## Data (ready to paste into `notes.mjs` LORE; `users` are main logins)
```json
[
  { "term": "ace / ziu / peng (short names)", "since": "2026-10-22",
    "meaning": "Chat shortens names: 'ace' for aceislosst, 'ziu' for ziubat, 'peng' for the streamer. Regulars use them in banter and when pinging each other.",
    "users": ["aceislosst", "ziubat", "yoohoo15", "pineyapplie"],
    "howBotsUse": "Bots may use the short names naturally when talking to or about those people ('ace' ok). Never explain it, never list who uses which." },
  { "term": "ssl / ssl rumble (Rocket League rank talk)", "since": "2026-10-22",
    "meaning": "Rank chatter about Supersonic Legend (SSL) that comes up whenever skill levels are compared; it is also a joke measuring stick ('SSL level', 'retired ssl').",
    "users": ["yoohoo15", "aceislosst", "blizzyfvv", "ziubat"],
    "howBotsUse": "Fine to know what SSL means when it comes up and to joke lightly about skill levels. Do not claim anyone's rank and do not take sides in a skill argument." },
  { "term": "squishy", "since": "2026-10-22",
    "meaning": "Another streamer the channel talks about and raids ('time to raid squishy', ban jokes, 'knows us'). Treated as a friendly neighbour channel.",
    "users": ["aceislosst", "ziubat", "snowyroses_", "yoohoo15"],
    "howBotsUse": "Only react if chat mentions it first; keep it friendly. Do not say anything about bans or arguments involving that channel and do not recount who said what." }
]
```
(`squishy` is the weakest: confirm with Ivan who this is and whether the bots should mention the channel at all. Without a yes it stays out. `ssl` is common game vocabulary and mostly helps bots not to misread it.)

## Edges / cards (information only)
- Pairs that talk to each other but have no graph edge yet (edges need 30+ exchanges, so they appear on their own later): blizzyfvv + scoobyfy_ (4 pings in a day), aceislosst + blizzyfvv (3). Nothing to do.
- Possible alias question seen in the card scan, not in this log: `krispy721` and `krispychicken721` share the nickname "krispy" (see `lore-health.md`).

## To apply (if approved)
Add the entries to `LORE` in `Tools/lore-mining/notes.mjs`, then `build.mjs` (the same step as the graph rebuild; see `graph-apply-runbook.md`). PinguinoChat re-reads `channel_lore.json` when the file changes, so no restart is needed.
