# Firsts rebuild - DRY RUN (nothing applied)

Run: sim Host from a temp build copy, `POST /api/firsts/rebuild {"apply":false}`, on a copy of host_globals.json and chat_logs. Live data untouched. Applying stays the coordinator's action (`apply:true`).

## Counts
| | |
|---|---|
| Chat days read | 251 |
| Messages | 672,759 |
| Streams detected | 256 (markers: 245 live / 256 offline) |
| People with any place | 189 |
| People whose stored numbers would change | 191 (includes the ones that would drop to 0) |
| Streams with under 5 chatters | 2 |

How stream starts were found: 232 by marker, 19 by off-marker only (start = first message), 5 inferred from chat (no markers).

## Scoring
Places 1st..5th = 5 / 3 / 3 / 1 / 1 points (vars firstPlaceStats..fifthPlaceStats, shown as 1st/2nd/3rd/4th/5th counts).

## Top 10 (score; 1st/2nd/3rd/4th/5th)
| # | Login | Score | Places |
|---|---|---|---|
| 1 | yoohoo15 | 468 | 62/28/15/17/12 |
| 2 | cups0ftea | 461 | 51/36/26/10/10 |
| 3 | wyatt104987 | 178 | 13/14/16/17/6 |
| 4 | Miri__0_0 | 106 | 12/10/4/2/2 |
| 5 | fIayir | 93 | 4/9/10/6/10 |
| 6 | blizzyfvv | 90 | 7/3/13/5/2 |
| 7 | LvLMarshmello | 90 | 6/6/7/11/10 |
| 8 | FLAYIR_ | 74 | 3/11/6/1/7 |
| 9 | sn0wmanny_ | 67 | 4/6/5/8/6 |
| 10 | bosskid274 | 64 | 3/5/8/3/7 |

Score check (yoohoo15): 62*5 + 28*3 + 15*3 + 17 + 12 = 468.

## Anomalies / things to look at before applying
1. Almost everyone changes: stored values are nearly all zero today, so the rebuild is effectively the first real fill. Examples: cups0ftea 1/0/0/0/0 -> 51/36/26/10/10; ash_wagawaga 0/0/0/1/0 -> 1/8/2/7/6.
2. `chattypinguino` (the bot) has 0/0/1/0/1 stored and would go to 0/0/0/0/0, so the rebuild excludes bots. Intended, just confirm.
3. Two lookalike accounts, `fIayir` (capital I) and `flayir_`, both rank in the top 10. Possibly the same person; the rebuild treats them as separate people. No merge is done.
4. 19 streams use the first message as start, and 2 streams have under 5 chatters: those places are less reliable (small boards).
5. The top two are far ahead (468 / 461 vs 178 for third); expected for the earliest regulars, but worth a glance before the numbers go public.
6. 40 sample changes are in the API reply (`sample_changes`); the full list is not stored.
