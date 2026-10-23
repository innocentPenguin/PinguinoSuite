# Multi soak test (2026-10-23, worker 42)

Script: `Suite/modules/multi/tests/soak.py [seconds] [rate]` (throwaway server on a free port starting at 8797, temp data dir, `MULTI_NO_KEYRING`, dead core URL, never touches real chat or OBS).
Load: ~45 messages/s for 240 s (10.3k injected through `/api/dev/inject` = the real pipeline: dedupe, score, SQLite, cards, hub broadcast) from 4 threads, a websocket client draining the hub, and every 10 s a sample of `/api/cards`, `/api/messages?limit=200`, `/api/search?q=hello` plus server RSS/CPU (read from the process that listens on the port).
Mix: 60% plain chat (3,000 distinct users), 8% emote messages, 5% 500-char text, 5% unicode (CJK, Arabic, RTL override, zalgo, emoji), 6% spam from 5 users, 6% questions / @mentions, 3% empty / blank / 2,000-char text, 7% stream events (follow, sub, resub, gift, cheer, raid), 30% of the non-plain ones tagged youtube/kick/tiktok.

## Result: no leak, no dropped messages, no errors; two hot spots found and fixed

| | Before fixes (run 1) | After fixes (run 2) |
|---|---|---|
| Injected / processed | 10,451 / 9,830 chat (events are not counted in "in") | 10,318 / 9,702 |
| Dropped by the Inbox, queue length | 0, 0-1 | 0, 0-1 |
| HTTP/send errors | 0 | 0 |
| Console warn/error lines | 3 (needs_auth for the unconfigured platforms) | 4 (same + one scene_follow 401 because the throwaway data dir has no Link token) |
| Missed cards returned by `/api/cards` | grew without bound: 65 -> 1,333 | capped at 200 (`missed_total` has the real count) |
| `/api/cards` latency | 40 ms -> 690 ms peak, trending up with the card count | 24-222 ms, flat |
| RSS | not measured (sampled the launcher stub) | 97-179 MB, sawtooth around ~125 MB, no upward trend over 4 min |
| CPU (one core = 100%) | not measured | 17-32%, mean ~26% |
| SQLite after 4 min | 9.4 MB | 9.2 MB (~2.3 KB per message; ~140 MB/hour at this extreme rate, pruned after `retention_days`) |

Latency numbers include the load generator and sampler sharing the machine, so treat them as upper bounds.

## What was fixed
1. **Cards never left memory**: dismissed and faded-answered cards stayed in `CardManager.cards` for the whole run, and `/api/cards` returned every missed card. `view()` now returns the newest 200 missed (`missed_total` = real count; recap still lists everything), and `tick()` evicts dismissed cards after 10 min and faded answered cards after 1 h (they stay in SQLite). Open, snoozed and missed cards are never evicted. Test: `tests/test_cards_fuzz.py::test_view_caps_missed_and_tick_evicts_finished_cards`.
2. Earlier in the day (not from the soak, same area): snapshot iteration of cards, bounded Inbox under question floods, events table pruning.

## Remaining observations (not fixed)
- `/api/search` is a `LIKE '%term%'` full scan: 20-280 ms at 10k rows, so expect ~1-3 s at 100k+ rows (a 10-hour stream at full tilt). Chat rates on a normal channel are 100x lower. If it matters: SQLite FTS5 on `messages.text`.
- `/api/messages?limit=200` 30-480 ms under load; it JSON-decodes every row. Fine for the UI, could cache the last page.
- Connector status events and `hub.emit` broadcast every message to every websocket client; only one client was connected here. With 5-6 open Multi windows expect proportionally more CPU.
- Static UI cost (DOM growth in long sessions) was not measured: tell 41 if a browser soak is wanted.
