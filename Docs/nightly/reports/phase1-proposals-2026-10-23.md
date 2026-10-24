# Phase 1 lore proposals - stream night of 2026-10-23 (CDT 17:14-22:02; logs are UTC: 10-23 tail + 10-24, 2300 human messages, ~46 chatters)

Status: **PROPOSALS ONLY, nothing applied to live lore.** Source: `nightly-phase1.mjs` on 2026-10-23 and 2026-10-24 (private output in `Data/lore-work/phase1-2026-10-2[34].md`), terms read in context. Same rules as the 10-22 file: no who/when, no quotes, no counts, never explain the joke, drop for opted-out users.

## Already proposed, now stronger
- `ace / ziu / peng`: `peng` is now by far the top candidate term (13 people in one night, used as a plain address to the streamer and between regulars). Strongly supports the entry in `phase1-proposals-2026-10-22.md`. Same for `marsh`, `mello`, `piney`, `blizzy`, `rose`, `yoohoo` as short names for regulars: could be one entry "short names" (marsh/mello = LvLMarshmello, piney = pineyapplie, rose = snowyroses_, blizzy = blizzyfvv, yoohoo). Fine for Chatty to use naturally; never list who.
- `ssl`: no new evidence tonight; unchanged.

## New, safe-ish
```json
[
  { "term": "fnaf / fortnite (game talk)", "since": "2026-10-23",
    "meaning": "Game topics that flood chat when the streamer asks what to play next or when the gamers pick a side-game: FNAF (and Poppy Playtime as the other horror pick) and Fortnite. Chat jokes about who is better at Fortnite and reacts loudly to the word FNAF.",
    "users": ["snowyroses_", "pineyapplie", "yoohoo15", "shadowrlttv", "dachillman36"],
    "howBotsUse": "Know the names so they do not look like noise. Light jokes are fine, do not pick a side, do not claim anyone plays or does not play." }
]
```
(Moderately weak: it is topic vocabulary more than lore. Skip if you want only recurring jokes.)

## Not proposed on purpose
- `blake` = a person (overtakeblake) in a tournament context, no card yet; not lore. Candidate for a card only when the logs reach the 150-message threshold.
- Profanity and filler words that top the list (`fuck`, `shit`, `ass`, `bruh`, `ngl`, `btw`, `holy`) are not lore.
- `song`: topic of an evening, not recurring.

## People and edges (information only)
- No card or graph node yet (5+ messages tonight): `thoridien_rl`, `innocentpenguin_` (the channel itself), `speary_1`, `spywobbles` (31 msgs on 10-24), `daspacechicken`, `gojo1016`. Cards need 150 messages, so none yet.
- Pairs with no graph edge yet: `pineyapplie + spywobbles` (18 pings, the strongest new pair), `ash_wagawaga + overtakeblake` (5), `cups0ftea + innocentpenguin_`, `blizzyfvv + t1cklem0n3ter324`, `snowyroses_ + t1cklem0n3ter324` (3 each). Edges appear on their own at 30+ exchanges; nothing to do.

## Dry-run result for the 10-22 proposals (applied only in a COPY)
`Data/lore-work/lm-copy` (copy of Tools/lore-mining with the two safe entries added: ace/ziu/peng + ssl) built against a fresh dry run (`Data/lore-work/dry2`, includes tonight's logs). Base build vs new build: cards 196 / edges 217 / groups 6 in both; **0 person cards changed (private and public), edges identical except the random `example` excerpt sample, `channel_lore.json` gains exactly the two entries.** So the only live effect would be two new lines in `channel_lore.json`; no Chatty restart needed (re-read on file change). To apply for real: add the two entries to `LORE` in `Tools/lore-mining/notes.mjs`, back up `Data/lore`, run `build.mjs`, run `verify-apply.mjs`.
