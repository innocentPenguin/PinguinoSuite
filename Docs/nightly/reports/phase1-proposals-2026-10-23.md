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

## Addendum: whole stream (CDT 17:14-22:02 = UTC 22:14 to 03:02, 2795 rows, 44 chatters, spam accounts filtered out)
- **Top speakers:** snowyroses_ 609, pineyapplie 359, shadowrlttv 290, blizzyfvv 233, yoohoo15 139, t1cklem0n3ter324 135, mashka_rl 86, dachillman36 67, timothyokongo 57, stefan77777777f 35. All have a graph node. No one in the stream sources is opted out (anon/forget list is empty), so nothing needed purging.
- **Raid / hype:** just before the end chat asked "who we raiding" and suggested three channels (Eddy twice, cix_rll, psynic). The Host ran the raid automations (raid_start 03:03:13, raid_out 03:03:20 UTC); the target channel is not written in any log I can read, so I cannot confirm which one was hit. Not lore: raid targets rotate. No new lore term from it.
- **Eventsub:** `channel.raid` subscription is refused all evening (HTTP 409, check token scopes), so incoming raids are not seen by the Host (separate from the outgoing raid above). Owner 15.
- **New regulars:** `dachillman36` (first seen this month, 67 msgs tonight, only one weak tie so far), `t1cklem0n3ter324` (135 msgs, since August, one weak tie), `stefan77777777f` (35, no ties yet). `spywobbles` is the loudest person without a node (31) and talked mostly with pineyapplie. No new cards until 150 messages.
- **Spam:** the viewbot accounts of the night were filtered by `spam.mjs` and are in none of the numbers above.
- **Graph check for timeout / welcome lines:** the public graph has no excerpts (verify-apply OK). The top five speakers are core or regular in the graph (strong duo and buddy ties), so a timeout between two of them would get a friendly "chat friends" line, and the welcome-back line for them is the warm pool; none states a number or says how the bot knows. dachillman36 and t1cklem0n3ter324 only have one tie of about a dozen exchanges, so they get at most the neutral lines ("known" at best). All safe.
